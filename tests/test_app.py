import asyncio
import json
from dataclasses import replace

from fastapi.testclient import TestClient
import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.models import Document
from app.providers import read_fixture
from app.store import Store
from app.sync import publish, sync_once


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def ask(client, question="SVE 向量化如何验证？", external=True):
    response = client.post("/api/ask", json={"question": question, "include_external": external})
    assert response.status_code == 200
    return response.json()


def test_home_navigation_and_links(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/health/ready").status_code == 200
    documents = client.get("/api/navigation").json()["documents"]
    assert len(documents) == 8
    assert all(doc["fictional"] for doc in documents)
    for doc in documents:
        assert client.get(f"/documents/{doc['id']}").status_code == 200


def test_two_sources_citations_and_feedback(client):
    result = ask(client)
    assert result["mode"] == "extractive"
    assert result["sources"] == {"internal": "ok", "external": "ok"}
    assert result["fictional"] is True
    assert any("SVE" in item["title"] for item in result["evidence"])
    for i, evidence in enumerate(result["evidence"], 1):
        assert evidence["citation"] == i
        assert f"[{i}]" in result["answer"]
        assert client.get(evidence["url"]).status_code == 200
    payload = {"request_id": result["request_id"], "solved": False, "reason": "需要真实案例"}
    assert client.post("/api/feedback", json=payload).status_code == 200
    payload["solved"] = True
    assert client.post("/api/feedback", json=payload).status_code == 200
    with client.app.state.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0] == 1
        assert db.execute("SELECT solved FROM feedback").fetchone()[0] == 1
        stored = json.loads(db.execute("SELECT payload FROM requests").fetchone()[0])
        assert stored["evidence"] == result["evidence"]


def test_internal_only_and_no_results(client):
    result = ask(client, external=False)
    assert result["sources"]["external"] == "disabled"
    assert all(item["source_type"] == "internal" for item in result["evidence"])
    assert result["keyword_results"]
    assert all(set(item) == {"title", "url", "snippet", "snippet_html", "updated_at", "fictional"} for item in result["keyword_results"])
    assert all("text_html" in item for item in result["evidence"])
    result = ask(client, question="火星移民签证价格")
    assert result["mode"] == "no_results"
    assert result["evidence"] == []
    assert result["keyword_results"] == []


def test_validation(client):
    for question in ("  ", "a" * 1001):
        assert client.post("/api/ask", json={"question": question}).status_code == 422
    assert client.post("/api/feedback", json={"request_id": "missing", "solved": True}).status_code == 404


def test_incremental_update_and_delete(settings):
    store = Store(settings.data_dir)
    store.initialize()
    docs = [Document.model_validate(doc) for doc in read_fixture("wiki.json")]
    assert publish(store, docs)["updated"] == 8
    assert publish(store, docs)["updated"] == 0
    docs[0] = docs[0].model_copy(update={"body": "## 新版\nUPDATED_UNIQUE_BODY", "version": "2"})
    result = publish(store, docs[:-1])
    assert result["updated"] == 1 and result["removed"] == 1
    with store.connection() as db:
        text = " ".join(row[0] for row in db.execute("SELECT text FROM chunks WHERE document_id=?", (docs[0].id,)))
        assert "UPDATED_UNIQUE_BODY" in text and "波动" not in text
        assert db.execute("SELECT COUNT(*) FROM chunks WHERE document_id=?", (docs[-1].id,)).fetchone()[0] == 0


def test_sync_failure_retains_previous_snapshot(settings, monkeypatch):
    store = Store(settings.data_dir)
    store.initialize()
    asyncio.run(sync_once(settings, store))
    async def broken(_):
        raise ValueError("Incomplete source")
    monkeypatch.setattr("app.sync.wiki_snapshot", broken)
    with pytest.raises(ValueError):
        asyncio.run(sync_once(settings, store))
    assert len(store.documents()) == 8
    assert "sync_error" in store.state()


def test_external_failure_keeps_internal(client, monkeypatch):
    async def broken(*_):
        raise httpx.ReadTimeout("timeout")
    monkeypatch.setattr("app.main.external_search", broken)
    result = ask(client)
    assert result["sources"] == {"internal": "ok", "external": "timeout"}
    assert result["evidence"] and result["mode"] == "extractive"


def test_model_failure_returns_evidence(client, monkeypatch):
    async def broken(*_):
        raise ValueError("Invalid citation")
    monkeypatch.setattr("app.main.generate", broken)
    result = ask(client)
    assert result["mode"] == "fallback" and result["evidence"]


def test_both_sources_failed_not_reported_as_empty(client, monkeypatch):
    def broken(*_):
        raise RuntimeError("offline")
    async def async_broken(*_):
        raise RuntimeError("offline")
    monkeypatch.setattr(client.app.state.index, "search", broken)
    monkeypatch.setattr("app.main.external_search", async_broken)
    result = ask(client)
    assert result["mode"] == "unavailable"


def test_document_escapes_html(client):
    store = client.app.state.store
    publish(store, [Document(id="xss", title="<script>alert(1)</script>", category="test", body="<script>alert(2)</script>")])
    page = client.get("/documents/xss").text
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_feedback_survives_restart(settings):
    with TestClient(create_app(settings)) as first:
        result = ask(first)
    with TestClient(create_app(settings)) as second:
        assert second.post("/api/feedback", json={"request_id": result["request_id"], "solved": True}).status_code == 200


def test_invalid_snapshot_cannot_delete(settings, monkeypatch):
    from app import providers
    original = providers.read_fixture
    monkeypatch.setattr(providers, "read_fixture", lambda _: [original("wiki.json")[0]] * 2)
    with pytest.raises(ValueError, match="Duplicate"):
        asyncio.run(providers.wiki_snapshot(settings))


@pytest.mark.parametrize("question", ["SVE 向量化如何验证？", "perf 火焰图如何分析热点？", "性能测试数据波动应该如何排查？"])
def test_suggested_questions_find_both_sources(client, question):
    result = ask(client, question)
    assert result["sources"] == {"internal": "ok", "external": "ok"}


@pytest.mark.parametrize("answer,expected_mode", [("需要覆盖尾部输入并验证正确性。[1]", "generated"), ("错误引用。[99]", "fallback"), ("没有引用", "fallback")])
def test_real_model_adapter_contract(settings, monkeypatch, answer, expected_mode):
    from app import providers
    original = httpx.AsyncClient
    def handler(request):
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert request.headers["authorization"] == "Bearer test-key"
        assert "evidence" in payload["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": answer}}]})
    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    config = replace(settings, model_mode="openai", model_url="https://model.example/chat/completions", model_name="test-model", model_api_key="test-key")
    with TestClient(create_app(config)) as client:
        result = ask(client)
        assert result["mode"] == expected_mode


def test_http_source_contracts(settings, monkeypatch):
    from app import providers
    original = httpx.AsyncClient
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"complete": True, "documents": read_fixture("wiki.json")})
        assert json.loads(request.content)["question"] == "SVE"
        item = read_fixture("external.json")[0]
        return httpx.Response(200, json={"results": [item]})
    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    config = replace(settings, wiki_mode="http", wiki_url="https://wiki.example/snapshot", external_mode="http", external_url="https://external.example/search")
    assert len(asyncio.run(providers.wiki_snapshot(config))) == 8
    assert asyncio.run(providers.external_search(config, "SVE"))[0].source_type == "external"
