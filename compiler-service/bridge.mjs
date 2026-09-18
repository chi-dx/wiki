import { createWiki } from 'llm-wiki-compiler';
import { mkdir, readFile, writeFile, rename } from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';

const fingerprint = (input) => createHash('sha256').update(JSON.stringify(input)).digest('hex');
const safeId = /^[A-Za-z0-9_-]{1,100}$/;
export const safePage = /^(concepts|queries)\/[^/\\.][^/\\]*$/u;

export function createBridge(config) {
  const wiki = createWiki({root: config.root});
  let busy = false;
  async function exclusive(action) {
    if (busy) throw Object.assign(new Error('Compiler is busy'), {code:'busy'});
    busy = true;
    try { return await action(); } finally { busy = false; }
  }
  const requireModel = () => {
    if (!config.configured) throw Object.assign(new Error('Set DEEPSEEK_API_KEY in .env'), {code:'model_not_configured'});
  };
  async function page(id) {
    if (!safePage.test(id)) throw Object.assign(new Error('Invalid page ID'), {code:'invalid_input'});
    const [pageDirectory, slug] = id.split('/');
    return wiki.getPage({pageDirectory, slug});
  }
  return {
    wiki,
    health: () => ({status:'ok', engine:'llm-wiki-compiler', version:'1.3.0',
                    configured:config.configured, model:config.model, busy,
                    compiled:existsSync(path.join(config.root, 'wiki', 'index.md'))}),
    async catalog() {
      const pages = []; let cursor;
      do {
        const result = await wiki.listPages({limit:100, cursor, includeBody:false});
        pages.push(...result.pages); cursor = result.cursor;
      } while (cursor);
      return {pages};
    },
    page,
    async query(question) {
      requireModel();
      return exclusive(async () => {
        // Real upstream SDK call. No local lexical fallback masquerading as query.
        const result = await wiki.query(question, {save:false, debug:false});
        const references = [];
        for (const ref of result.refs || []) {
          if (!safePage.test(ref.pageId)) continue;
          const record = await page(ref.pageId);
          if (record) references.push({page_id:ref.pageId, title:record.title,
                                     text:record.body || record.summary,
                                     url:`/compiler/pages/${ref.pageId.split('/').map(encodeURIComponent).join('/')}`});
        }
        // Keep native wikilinks in the answer; don't invent numeric citations.
        return {answer:result.answer, references, page_ids:result.pageIds,
                warnings:result.warnings || [], engine:'llm-wiki-compiler', model:config.model};
      });
    },
    async sync(documents, compile=true) {
      if (compile) requireModel();
      if (!Array.isArray(documents) || documents.length > 1000 || documents.some(doc =>
          !safeId.test(doc.id) || typeof doc.title !== 'string' || typeof doc.body !== 'string' ||
          doc.body.length > 200000)) {
        throw Object.assign(new Error('Invalid document snapshot'), {code:'invalid_input'});
      }
      if (new Set(documents.map(doc=>doc.id)).size !== documents.length) throw Object.assign(new Error('Duplicate IDs'), {code:'invalid_input'});
      return exclusive(async () => {
        await mkdir(config.root, {recursive:true});
        const manifestPath = path.join(config.root, 'portal-sources.json');
        let previous = {};
        try { previous = JSON.parse(await readFile(manifestPath, 'utf8')); }
        catch (error) { if (error.code !== 'ENOENT') throw error; }
        const next = {};
        let changed = 0;
        for (const doc of documents) {
          const hash = fingerprint(doc);
          const sourceIdentity = `portal:${doc.id}`;
          if (previous[doc.id]?.hash === hash && previous[doc.id]?.sourceIdentity === sourceIdentity && await wiki.getSource(previous[doc.id].filename)) { next[doc.id] = previous[doc.id]; continue; }
          const text = `# ${doc.title}\n\n原文ID：${doc.id}\n原文地址：${doc.url || `/documents/${doc.id}`}\n版本：${doc.version || '未提供'}\n${doc.fictional ? '重要：这是虚构演示资料，不代表真实实验结果。' : ''}\n\n${doc.body}`;
          const result = await wiki.ingestText({title:doc.id, text, source:sourceIdentity});
          if (result.truncated) throw new Error('Upstream truncated source; refusing compile');
          if (previous[doc.id]?.filename && previous[doc.id].filename !== result.filename) await wiki.deleteSource(previous[doc.id].filename);
          next[doc.id] = {hash, sourceIdentity, filename:result.filename, fictional:Boolean(doc.fictional)};
          changed++;
        }
        let removed = 0;
        for (const [id, old] of Object.entries(previous)) {
          if (!next[id]) { await wiki.deleteSource(old.filename); removed++; }
        }
        // Retry is idempotent even when compilation fails. Source changes persist
        // upstream; compilation itself owns its journal. This is not an atomic vault swap.
        const temp = `${manifestPath}.tmp`;
        await writeFile(temp, JSON.stringify(next, null, 2), 'utf8');
        await rename(temp, manifestPath);
        const result = compile ? await wiki.compile({embeddings:false,
          systemPolicy:'请使用中文。保留原文出处、适用条件和限制。虚构演示资料必须明确标注，不能当作真实测量。'}) : null;
        if (result?.errors?.length) throw Object.assign(new Error('Upstream compilation returned errors'), {code:'compile_incomplete'});
        return {ingested:changed, removed, total:documents.length, compiled:compile, result};
      });
    },
  };
}
