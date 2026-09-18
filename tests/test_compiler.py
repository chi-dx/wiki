import asyncio
from dataclasses import replace
import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import Document
from app.providers import read_fixture
from app.store import Store
from app.sync import sync_once


def setup(tmp_path):
    settings = Settings(data_dir=tmp_path)
    store = Store(tmp_path)
    store.initialize()
    return settings, store


def test_vault_files_links_and_idempotence(tmp_path):
    settings, store = setup(tmp_path)
    asyncio.run(sync_once(settings, store))
    first = store.state()["compilation"]
    assert first["pages"] == 13  # Eight sources and five topic pages.
    root = tmp_path / "vault" / "generations" / first["generation"]
    assert (root / "schema.md").is_file()
    assert (root / "wiki" / "log.md").is_file()
    assert len(list((root / "raw").glob("*.md"))) == 8
    for path in (root / "wiki").rglob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            assert (path.parent / target).is_file(), (path, target)
    asyncio.run(sync_once(settings, store))
    assert store.state()["compilation"]["generation"] == first["generation"]
    assert store.state()["sync"]["updated"] == 0


def test_changed_and_deleted_sources_rebuild_only_dependents(tmp_path, monkeypatch):
    settings, store = setup(tmp_path)
    asyncio.run(sync_once(settings, store))
    before = {page["id"]: page for page in store.wiki_pages()}
    docs = [Document.model_validate(doc) for doc in read_fixture("wiki.json") if doc["id"] != "sandbox-startup"]
    docs = [doc.model_copy(update={"body": doc.body + "\n新版检查项：独特测试标识XYZ", "version": "3"})
            if doc.id == "sve-json" else doc for doc in docs]
    async def source(_):
        return docs
    monkeypatch.setattr("app.sync.wiki_snapshot", source)
    asyncio.run(sync_once(settings, store))
    after = {page["id"]: page for page in store.wiki_pages()}
    assert "sources/sandbox-startup" not in after
    assert after["sources/sve-json"]["fingerprint"] != before["sources/sve-json"]["fingerprint"]
    assert after["sources/perf-runbook"]["fingerprint"] == before["sources/perf-runbook"]["fingerprint"]
    assert all("sandbox-startup" not in page["source_ids"] for page in after.values())


def test_llm_compile_is_cached_and_failure_keeps_published_generation(tmp_path, monkeypatch):
    settings, store = setup(tmp_path)
    settings = replace(settings, compile_mode="llm", model_url="https://model.example/chat/completions", model_name="test")
    original = httpx.AsyncClient
    calls = []
    def handler(request):
        payload = json.loads(request.content)
        prompt = json.loads(payload["messages"][1]["content"])
        calls.append(prompt)
        citation = prompt["sources"][0]["id"]
        output = {"summary": "测试模型编译摘要", "content": f"测试结论 [source:{citation}]"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(output)}}]})
    monkeypatch.setattr("app.compiler.httpx.AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    asyncio.run(sync_once(settings, store))
    assert len(calls) == 13
    assert all(page["mode"] == "llm" for page in store.wiki_pages())
    first = store.state()["compilation"]
    asyncio.run(sync_once(settings, store))
    assert len(calls) == 13
    async def broken(*args):
        raise ValueError("Invalid generated citation")
    monkeypatch.setattr("app.compiler.model_page", broken)
    with pytest.raises(ValueError):
        asyncio.run(sync_once(replace(settings, model_name="new-model"), store))
    assert store.state()["compilation"] == first
    assert len(store.documents()) == 8


def test_unknown_compiler_citation_rejected(tmp_path, monkeypatch):
    from app.compiler import model_page
    settings, _ = setup(tmp_path)
    settings = replace(settings, model_url="https://model.example/chat/completions")
    original = httpx.AsyncClient
    def handler(_):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"summary": "错误", "content": "[source:unknown]"})}}]})
    monkeypatch.setattr("app.compiler.httpx.AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    doc = Document.model_validate(read_fixture("wiki.json")[0])
    with pytest.raises(ValueError, match="source references"):
        asyncio.run(model_page(settings, "test", "source", [doc], {}))


def test_compiled_navigation_and_citations(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        assert client.get("/wiki").status_code == 200
        catalog = client.get("/api/wiki").json()
        assert len(catalog["pages"]) == 13
        for page in catalog["pages"]:
            assert client.get("/wiki/" + page["id"]).status_code == 200
        result = client.post("/api/ask", json={"question": "SVE 向量化", "include_external": False}).json()
        assert result["evidence"]
        assert all(item["wiki_page"] and item["url"].startswith("/documents/") for item in result["evidence"])
