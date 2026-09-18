"""HTTP boundary to the real llm-wiki-compiler Node SDK service."""
import httpx
from app.models import Evidence


async def compiler_query(settings, question):
    try:
        async with httpx.AsyncClient(timeout=settings.compiler_query_timeout) as client:
            response = await client.post(settings.compiler_url + "/query", json={"question": question})
        if response.status_code == 503 and response.json().get("error") == "model_not_configured":
            return [], "not_configured", None
        response.raise_for_status()
        result = response.json()
        evidence = [Evidence(
            evidence_id="compiler:" + item["page_id"], source_type="internal",
            source_name="llm-wiki-compiler 知识页（派生资料）", title=item["title"],
            url=item["url"], text=(item["text"] or "知识页未提供正文")[:20000],
            fictional=settings.wiki_mode == "demo",
        ) for item in result["references"]]
        if evidence:
            evidence[0] = evidence[0].model_copy(update={"wiki_context": result["answer"][:6000]})
        return evidence, "ok" if evidence else "empty", result
    except (httpx.TimeoutException, TimeoutError):
        return [], "timeout", None
    except Exception:
        return [], "error", None


async def compiler_sync(settings, documents):
    async with httpx.AsyncClient(timeout=settings.compiler_sync_timeout) as client:
        response = await client.post(settings.compiler_url + "/sync",
                                     json={"documents": [doc.model_dump() for doc in documents], "compile": True})
        response.raise_for_status()
        return response.json()
