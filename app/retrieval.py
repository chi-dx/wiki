"""Search compiled wiki pages and resolve citations to original source text."""
import json
import re
from typing import Protocol

from app.models import Document, Evidence


class SearchIndex(Protocol):
    def search(self, question: str, limit: int = 4) -> list[Evidence]: ...


def tokens(text):
    result = re.findall(r"[a-z0-9_]+", text.lower())
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        result.extend(run[i:i + 2] for i in range(len(run) - 1))
    return set(result) - {"如何", "怎么", "什么", "哪些", "一个", "我们", "可以", "进行", "问题", "资料"}


def rank(question, title, text):
    query = tokens(question)
    if not query:
        return 0
    matches = query & tokens(title + " " + text)
    # Avoid returning unrelated documents for generic one-word overlap.
    exact_terms = {term for term in matches if re.fullmatch(r"[a-z0-9_]+", term)}
    if not matches or (len(query) > 4 and len(matches) < 2 and not exact_terms):
        return 0
    return len(matches) / len(query) + 1.5 * len(query & tokens(title)) / len(query)


def split_document(document):
    heading, lines, chunks = document.title, [], []
    for line in document.body.splitlines():
        if line.startswith("## "):
            if lines:
                chunks.append((heading, "\n".join(lines).strip()))
            heading, lines = line[3:].strip(), []
        else:
            lines.append(line)
    if lines:
        chunks.append((heading, "\n".join(lines).strip()))
    # Keep long sections bounded without silently dropping their tail.
    return [(heading, text[start:start + 1800]) for heading, text in chunks
            if text for start in range(0, len(text), 1600)]


class DemoIndex:
    def __init__(self, store):
        self.store = store

    def search(self, question, limit=4):
        with self.store.connection() as db:
            rows = db.execute("SELECT c.*, d.payload FROM chunks c JOIN documents d ON d.id=c.document_id").fetchall()
        hits = []
        for row in rows:
            doc = Document.model_validate_json(row["payload"])
            score = rank(question, doc.title + " " + " ".join(doc.tags) + " " + row["heading"], row["text"])
            if score:
                hits.append((score, doc.id, Evidence(
                    evidence_id=row["id"], source_type="internal", source_name="团队 Wiki",
                    title=f"{doc.title} · {row['heading']}",
                    url=doc.url or f"/documents/{doc.id}", text=row["text"],
                    updated_at=doc.updated_at, fictional=doc.fictional)))
        hits.sort(key=lambda item: item[0], reverse=True)
        counts, results = {}, []
        for _, doc_id, evidence in hits:
            if counts.get(doc_id, 0) >= 2:
                continue
            counts[doc_id] = counts.get(doc_id, 0) + 1
            results.append(evidence)
            if len(results) >= limit:
                break
        return results


class WikiIndex(DemoIndex):
    def search(self, question, limit=4):
        # One read transaction keeps wiki pages and raw evidence on one generation.
        with self.store.connection() as db:
            db.execute("BEGIN")
            pages = [json.loads(row[0]) for row in db.execute("SELECT payload FROM wiki_pages")]
            rows = db.execute("SELECT c.*, d.payload FROM chunks c JOIN documents d ON d.id=c.document_id").fetchall()
        if not pages:
            return super().search(question, limit)
        ranked = sorted(((rank(question, page["title"], page["summary"] + " " + page["content"]), page)
                         for page in pages), key=lambda pair: pair[0], reverse=True)
        selected = {}
        for score, page in ranked:
            if score <= 0:
                continue
            for source_id in page["source_ids"]:
                selected.setdefault(source_id, (score, page))
        hits = []
        for row in rows:
            if row["document_id"] not in selected:
                continue
            doc = Document.model_validate_json(row["payload"])
            page_score, page = selected[doc.id]
            score = rank(question, doc.title + " " + row["heading"], row["text"])
            if score <= 0:
                continue
            hits.append((score + page_score * 0.3, doc.id, Evidence(
                evidence_id=row["id"], source_type="internal", source_name="团队 Wiki",
                title=f"{doc.title} · {row['heading']}", url=doc.url or f"/documents/{doc.id}",
                text=row["text"], updated_at=doc.updated_at, fictional=doc.fictional,
                wiki_page=page["id"], wiki_summary=page["summary"], wiki_context=page["content"][:3000])))
        hits.sort(key=lambda item: item[0], reverse=True)
        counts, result = {}, []
        for _, doc_id, item in hits:
            if counts.get(doc_id, 0) >= 2:
                continue
            counts[doc_id] = counts.get(doc_id, 0) + 1
            result.append(item)
            if len(result) == limit:
                break
        return result


def prepare_evidence(internal, external, budget=12000):
    output, seen, size = [], set(), 0
    # Round-robin preserves each provider's ranking without comparing scores.
    for i in range(max(len(internal), len(external))):
        for source in (internal, external):
            if i >= len(source):
                continue
            item = source[i]
            key = (item.url, item.text.strip())
            if key in seen:
                continue
            seen.add(key)
            remaining = budget - size
            if remaining < 100:
                continue
            text = item.text[:min(1800, remaining)]
            context = (item.wiki_context or "")[:max(0, remaining - len(text))]
            item = item.model_copy(update={"text": text, "wiki_context": context or None, "citation": len(output) + 1})
            size += len(item.text) + len(context)
            output.append(item)
    return output
