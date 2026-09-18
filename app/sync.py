import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging

from app.config import Settings
from app.compiler import compile_pages, export_vault
from app.providers import wiki_snapshot
from app.retrieval import split_document
from app.store import Store
from app.upstream import compiler_sync

logger = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


def publish(store, documents, pages=None, compilation=None):
    # Parse the complete snapshot before starting an atomic DB transaction.
    prepared = []
    for doc in documents:
        payload = doc.model_dump_json()
        fingerprint = hashlib.sha256(payload.encode()).hexdigest()
        prepared.append((doc, payload, fingerprint, split_document(doc)))
    changed = 0
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        previous = dict(db.execute("SELECT id,fingerprint FROM documents"))
        for doc, payload, fingerprint, chunks in prepared:
            if previous.get(doc.id) == fingerprint:
                continue
            db.execute("INSERT INTO documents VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET "
                       "payload=excluded.payload,fingerprint=excluded.fingerprint", (doc.id, payload, fingerprint))
            db.execute("DELETE FROM chunks WHERE document_id=?", (doc.id,))
            db.executemany("INSERT INTO chunks VALUES (?,?,?,?)",
                           [(f"internal:{doc.id}:{i}", doc.id, heading, text) for i, (heading, text) in enumerate(chunks)])
            changed += 1
        removed = set(previous) - {doc.id for doc in documents}
        db.executemany("DELETE FROM documents WHERE id=?", [(doc_id,) for doc_id in removed])
        db.execute("DELETE FROM wiki_pages")
        if pages is not None:
            db.executemany("INSERT INTO wiki_pages VALUES (?,?)", [(page.id, page.model_dump_json()) for page in pages])
        if compilation is not None:
            db.execute("INSERT OR REPLACE INTO state VALUES ('compilation',?)", (json.dumps(compilation),))
        else:
            db.execute("DELETE FROM state WHERE key='compilation'")
        result = {"at": now(), "total": len(documents), "updated": changed, "removed": len(removed)}
        db.execute("INSERT OR REPLACE INTO state VALUES ('sync',?)", (json.dumps(result),))
        db.execute("DELETE FROM state WHERE key='sync_error'")
    return result


async def sync_once(settings, store):
    try:
        docs = await wiki_snapshot(settings)
        docs.sort(key=lambda doc: doc.id)
        if settings.knowledge_backend == "compiler":
            result = await compiler_sync(settings, docs)
            published = await asyncio.to_thread(publish, store, docs)
            store.set_state("upstream_compiler", {"at": now(), "result": result})
            return published
        previous = {page["id"]: page for page in store.wiki_pages()}
        pages = await compile_pages(settings, docs, previous)
        compilation = await asyncio.to_thread(export_vault, settings, docs, pages, store.state().get("compilation", {}))
        return await asyncio.to_thread(publish, store, docs, pages, compilation)
    except Exception as exc:
        store.set_state("sync_error", {"at": now(), "type": type(exc).__name__})
        raise


async def run(once):
    settings = Settings.from_env()
    store = Store(settings.data_dir)
    store.initialize()
    while True:
        try:
            logger.info("sync_complete %s", await sync_once(settings, store))
        except Exception:
            logger.error("sync_failed; previous snapshot retained", exc_info=False)
            if once:
                raise
        if once:
            return
        await asyncio.sleep(settings.sync_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(parser.parse_args().once))
