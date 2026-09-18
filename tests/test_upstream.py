from dataclasses import replace
import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_compiler_answer_is_returned_without_second_model_call(tmp_path, monkeypatch):
    async def query(settings, question):
        from app.models import Evidence
        return [Evidence(evidence_id="compiler:concepts/sve",source_type="internal",source_name="compiler",
                         title="SVE",url="/compiler/pages/concepts/sve",text="知识页正文")], "ok", {
            "answer":"真实SDK结果占位（测试夹具）[[SVE]]", "engine":"llm-wiki-compiler", "model":"deepseek-v4-flash"}
    async def forbidden(*args):
        raise AssertionError("Must not regenerate an internal-only compiler answer")
    monkeypatch.setattr("app.main.compiler_query", query)
    monkeypatch.setattr("app.main.generate", forbidden)
    with TestClient(create_app(Settings(data_dir=tmp_path,knowledge_backend="compiler"))) as client:
        response = client.post('/api/ask',json={"question":"SVE验证","include_external":False})
        assert response.status_code == 200
        result = response.json()
        assert result['mode'] == 'compiler'
        assert '<a href="/compiler/pages/concepts/sve"' in result['answer_html']
        assert result['compiler']['model'] == 'deepseek-v4-flash'


def test_missing_deepseek_key_is_visible(tmp_path, monkeypatch):
    async def unavailable(*args):
        return [], "not_configured", None
    monkeypatch.setattr("app.main.compiler_query",unavailable)
    with TestClient(create_app(Settings(data_dir=tmp_path,knowledge_backend="compiler"))) as client:
        response = client.post('/api/ask',json={"question":"SVE验证","include_external":False})
        assert response.json()['mode'] == 'unavailable'
        assert 'DEEPSEEK_API_KEY' in response.json()['answer']


def test_http_adapter_uses_query_endpoint(tmp_path, monkeypatch):
    import asyncio
    from app.upstream import compiler_query
    original = httpx.AsyncClient
    def handler(request):
        assert request.url.path == '/query'
        return httpx.Response(503,json={"error":"model_not_configured"})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    assert asyncio.run(compiler_query(Settings(data_dir=tmp_path),'test')) == ([], 'not_configured', None)
