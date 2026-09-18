import asyncio
from contextlib import asynccontextmanager
import html
import logging
import time
import uuid

import httpx

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT, Settings
from app.models import AskRequest, FeedbackRequest
from app.markdown import render_answer
from app.providers import external_search, generate, read_fixture
from app.retrieval import WikiIndex, prepare_evidence
from app.store import Store
from app.sync import now, sync_once
from app.upstream import compiler_query
from dataclasses import replace

logger = logging.getLogger(__name__)


def create_app(settings=None):
    settings = settings or Settings.from_env()
    store = Store(settings.data_dir)
    index = WikiIndex(store)
    slots = asyncio.Semaphore(settings.max_concurrent_asks)

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        if settings.knowledge_backend == "local" and settings.wiki_mode == "demo" and settings.compile_mode == "extractive" and "compilation" not in store.state():
            await sync_once(settings, store)
        yield

    app = FastAPI(title="团队知识库", lifespan=lifespan)
    app.state.store = store
    app.state.index = index
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.get("/")
    def home():
        return FileResponse(ROOT / "static" / "index.html")

    @app.get("/dashboard")
    def dashboard():
        return FileResponse(ROOT / "static" / "dashboard.html")

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready():
        try:
            if settings.knowledge_backend == "compiler":
                async with httpx.AsyncClient(timeout=5) as client:
                    response = await client.get(settings.compiler_url + "/health")
                    response.raise_for_status()
                    health = response.json()
                if not health.get("configured") or not health.get("compiled"):
                    raise HTTPException(503, "compiler需要模型配置及首次编译")
            state = store.state()
            with store.connection() as db:
                db.execute("SELECT COUNT(*) FROM chunks").fetchone()
            if "sync" not in state:
                raise HTTPException(503, "尚未完成首次同步")
            return {"status": "ok", "sync": state["sync"]}
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "本地存储不可用")

    @app.get("/api/navigation")
    def navigation():
        documents = store.documents()
        return {"documents": [{k: v for k, v in doc.items() if k != "body"} for doc in documents],
                "state": store.state(), "mode": settings.model_mode,
                "wiki_mode": settings.wiki_mode, "external_mode": settings.external_mode,
                "external_default": settings.external_default and settings.external_mode != "off",
                "index_provider": settings.knowledge_backend, "compilation": store.state().get("compilation")}

    async def upstream_catalog():
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(settings.compiler_url + "/pages")
                response.raise_for_status()
            return [{"id": page["pageDirectory"] + "/" + page["slug"], "title": page["title"],
                     "summary": page["summary"]} for page in response.json()["pages"]]
        except Exception:
            raise HTTPException(502, "compiler知识目录暂不可用")

    @app.get("/api/wiki")
    async def wiki_catalog():
        if settings.knowledge_backend == "compiler":
            return {"pages": await upstream_catalog(), "engine": "llm-wiki-compiler"}
        return {"pages": store.wiki_pages(), "compilation": store.state().get("compilation")}

    async def retrieve(source, question):
        try:
            async with asyncio.timeout(settings.upstream_timeout):
                items = (await asyncio.to_thread(index.search, question) if source == "internal"
                         else await external_search(settings, question))
            return items, "ok" if items else "empty"
        except (TimeoutError, httpx.TimeoutException):
            return [], "timeout"
        except Exception as exc:
            logger.warning("retrieval_failed source=%s type=%s", source, type(exc).__name__)
            return [], "error"

    async def keyword_search(question):
        try:
            async with asyncio.timeout(3):
                hits = await asyncio.to_thread(index.search, question, 12)
            results, seen = [], set()
            for item in hits:
                if item.url in seen:
                    continue
                seen.add(item.url)
                snippet = item.text[:320]
                results.append({"title": item.title, "url": item.url, "snippet": snippet,
                                "snippet_html": render_answer(snippet),
                                "updated_at": item.updated_at, "fictional": item.fictional})
                if len(results) == 6:
                    break
            return results
        except Exception as exc:
            logger.warning("keyword_search_failed type=%s", type(exc).__name__)
            return []

    @app.post("/api/ask")
    async def ask(request: AskRequest):
        try:
            await asyncio.wait_for(slots.acquire(), timeout=0.1)
        except TimeoutError:
            raise HTTPException(429, "当前提问较多，请稍后重试")
        started = time.monotonic()
        try:
            request_id = uuid.uuid4().hex
            keyword_task = asyncio.create_task(keyword_search(request.question))
            external_enabled = request.include_external and settings.external_mode != "off"
            compiler_result = None
            if settings.knowledge_backend == "compiler":
                if external_enabled:
                    (internal, internal_status, compiler_result), (external, external_status) = await asyncio.gather(
                        compiler_query(settings, request.question), retrieve("external", request.question))
                else:
                    internal, internal_status, compiler_result = await compiler_query(settings, request.question)
                    external, external_status = [], "disabled"
            elif external_enabled:
                (internal, internal_status), (external, external_status) = await asyncio.gather(
                    retrieve("internal", request.question), retrieve("external", request.question))
            else:
                internal, internal_status = await retrieve("internal", request.question)
                external, external_status = [], "disabled"
            evidence = prepare_evidence(internal, external)
            if compiler_result and compiler_result.get("answer") and not external:
                answer, mode = compiler_result["answer"], "compiler"
            elif compiler_result and compiler_result.get("answer") and settings.model_mode == "extractive":
                supplements = [item for item in evidence if item.source_type == "external"]
                extra, _ = await generate(replace(settings, model_mode="extractive"), request.question, supplements)
                answer, mode = compiler_result["answer"] + "\n\n其他资料补充（原文摘录）\n\n" + extra, "compiler"
            elif evidence:
                try:
                    remaining = settings.request_timeout if settings.knowledge_backend == "compiler" else settings.request_timeout - (time.monotonic() - started)
                    async with asyncio.timeout(max(0.01, remaining)):
                        answer, mode = await generate(settings, request.question, evidence)
                except Exception as exc:
                    logger.warning("generation_failed request_id=%s type=%s", request_id, type(exc).__name__)
                    answer, mode = "回答生成暂时不可用，请查看下方检索到的原文资料。", "fallback"
            else:
                failed = internal_status in {"timeout", "error", "not_configured"} or external_status in {"timeout", "error"}
                answer = "部分资料暂时无法检索，当前没有可用证据，请稍后重试。" if failed else "未找到相关资料。可以换一个术语，或补充应用、工具及场景信息。"
                mode = "unavailable" if failed else "no_results"
                if internal_status == "not_configured":
                    answer = "llm-wiki-compiler 已接入，但尚未配置 DeepSeek API Key。请在本地 .env 填写 DEEPSEEK_API_KEY，重启 compiler 服务并完成首次编译。"
            evidence_payload = []
            for item in evidence:
                serialized = item.model_dump()
                serialized["text_html"] = render_answer(item.text)
                evidence_payload.append(serialized)
            payload = {"request_id": request_id, "question": request.question, "answer": answer,
                       "mode": mode, "evidence": evidence_payload,
                       "keyword_results": await keyword_task,
                       "sources": {"internal": internal_status, "external": external_status},
                       "fictional": any(item.fictional for item in evidence),
                       "created_at": now(), "elapsed_ms": round((time.monotonic() - started) * 1000)}
            payload["engine"] = settings.knowledge_backend
            payload["answer_html"] = render_answer(answer, evidence)
            if compiler_result:
                payload["compiler"] = {key: compiler_result.get(key) for key in ("engine", "model", "warnings", "page_ids")}
            await asyncio.to_thread(store.save_request, payload)
            logger.info("ask_complete request_id=%s mode=%s elapsed_ms=%s", request_id, mode, payload["elapsed_ms"])
            return payload
        finally:
            slots.release()

    @app.post("/api/feedback")
    def feedback(request: FeedbackRequest):
        if not store.feedback(request.request_id, request.solved, request.reason, now()):
            raise HTTPException(404, "找不到对应的问答记录")
        return {"saved": True}

    def document_page(title, body, fictional):
        notice = "虚构演示资料 · 不代表真实团队结论" if fictional else "知识库文档快照"
        return HTMLResponse(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
            <meta name="viewport" content="width=device-width,initial-scale=1">
            <title>{html.escape(title)} · 团队知识库</title><link rel="stylesheet" href="/static/style.css">
            <body class="document-page"><main><a href="/">← 返回知识库</a><p class="notice">{notice}</p>
            <h1>{html.escape(title)}</h1><pre class="document-body">{html.escape(body)}</pre></main></body></html>''')

    @app.get("/compiler/pages/{page_id:path}")
    async def compiler_page(page_id: str):
        import re
        from urllib.parse import quote
        if settings.knowledge_backend != "compiler" or not re.fullmatch(r"(?:concepts|queries)/[^/\\.][^/\\]*", page_id):
            raise HTTPException(404, "知识页不存在")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(settings.compiler_url + "/pages/" + quote(page_id, safe='/'))
        if response.status_code != 200:
            raise HTTPException(502, "compiler知识页暂不可用")
        page = response.json()
        return document_page(page["title"], "llm-wiki-compiler生成的派生知识页，请核对其原文引用。\n\n" + page.get("body", ""), settings.wiki_mode == "demo")

    @app.get("/wiki", response_class=HTMLResponse)
    async def wiki_home():
        pages = await upstream_catalog() if settings.knowledge_backend == "compiler" else store.wiki_pages()
        links = "".join(f'<li><a target="_blank" rel="noopener noreferrer" href="/wiki/{html.escape(page["id"], quote=True)}">{html.escape(page["title"])}</a>'
                        f'<p class="muted">{html.escape(page["summary"])}</p></li>' for page in pages)
        return HTMLResponse('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                            '<meta name="viewport" content="width=device-width,initial-scale=1">'
                            '<title>编译知识目录</title><link rel="stylesheet" href="/static/style.css">'
                            '<body class="document-page"><main><a href="/">← 返回知识库</a>'
                            '<h1>编译知识目录</h1><p>从原始资料整理的知识页，保留来源与页面关联。</p>'
                            f'<ul class="wiki-catalog">{links or "尚未完成知识编译，请先执行同步。"}</ul></main></body></html>')

    @app.get("/wiki/{page_id:path}", response_class=HTMLResponse)
    def wiki_page(page_id: str):
        if settings.knowledge_backend == "compiler":
            from urllib.parse import quote
            return RedirectResponse("/compiler/pages/" + quote(page_id, safe='/'))
        page = next((page for page in store.wiki_pages() if page["id"] == page_id), None)
        if not page:
            raise HTTPException(404, "知识页不存在")
        mode = "模型编译结果，请核对原文" if page["mode"] == "llm" else "原文摘录 / 主题目录，尚未进行模型综合"
        body = f"{mode}\n\n{page['summary']}\n\n{page['content']}"
        response = document_page(page["title"], body, page["fictional"])
        sources = ''.join(f'<li><a href="/documents/{html.escape(source_id, quote=True)}">{html.escape(source_id)}</a></li>' for source_id in page["source_ids"])
        related = ''.join(f'<li><a href="/wiki/{html.escape(other, quote=True)}">{html.escape(other)}</a></li>' for other in page["related"])
        extra = f'<h2>原文来源</h2><ul>{sources}</ul><h2>关联知识页</h2><ul>{related}</ul><a href="/wiki">查看知识目录</a>'
        return HTMLResponse(response.body.decode().replace('</main>', extra + '</main>'))

    @app.get("/documents/{doc_id}")
    def document(doc_id: str):
        doc = next((doc for doc in store.documents() if doc["id"] == doc_id), None)
        if not doc:
            raise HTTPException(404, "文档不存在")
        return document_page(doc["title"], doc["body"], doc["fictional"])

    @app.get("/reference/{ref_id}")
    def reference(ref_id: str):
        if settings.external_mode != "demo":
            raise HTTPException(404)
        ref = next((item for item in read_fixture("external.json") if item["url"] == f"/reference/{ref_id}"), None)
        if not ref:
            raise HTTPException(404)
        return document_page(ref["title"], ref["text"], True)

    return app


app = create_app()
