import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import { createWiki } from 'llm-wiki-compiler';
import { createBridge } from '../bridge.mjs';
import { createServer } from '../server.mjs';
import { configure } from '../config.mjs';

test('real SDK ingest, change, delete and no-credential query guard', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'compiler-sdk-'));
  try {
    const bridge = createBridge({root, configured:false, model:'deepseek-v4-flash'});
    const docs = [{id:'sve',title:'SVE实验',body:'虚构资料：检查尾部输入。',fictional:true}];
    assert.equal((await bridge.sync(docs, false)).ingested, 1);
    assert.equal((await bridge.sync(docs, false)).ingested, 0);
    docs[0].body += ' 新增验证步骤。';
    assert.equal((await bridge.sync(docs, false)).ingested, 1);
    assert.equal((await bridge.wiki.listSources()).sources.length, 1);
    await assert.rejects(bridge.query('SVE如何验证'), {code:'model_not_configured'});
    await assert.rejects(bridge.sync(docs, true), {code:'model_not_configured'});
    assert.equal((await bridge.sync([], false)).removed, 1);
    await assert.rejects(bridge.page('../secret'), {code:'invalid_input'});
  } finally { await rm(root, {recursive:true, force:true}); }
});

test('compile errors returned as data must fail the synchronization', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'compiler-errors-'));
  try {
    const bridge = createBridge({root, configured:true, model:'test'});
    bridge.wiki.compile = async () => ({compiled:0, errors:['test provider failure']});
    await assert.rejects(bridge.sync([], true), {code:'compile_incomplete'});
  } finally { await rm(root, {recursive:true, force:true}); }
});

test('real SDK query uses OpenAI-compatible DeepSeek-shaped requests and returns refs', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'compiler-query-'));
  const requests = [];
  const mock = http.createServer(async (req, res) => {
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks)); requests.push({url:req.url,body});
    const selection = body.tools?.some(tool=>tool.function.name === 'select_pages');
    const message = selection ? {role:'assistant',content:null,tool_calls:[{id:'call_1',type:'function',function:{name:'select_pages',arguments:JSON.stringify({pages:['concepts/sve-check'],reasoning:'test fixture'})}}]}
      : {role:'assistant',content:'检查尾部输入并保留标量参照。[[SVE检查]]'};
    res.writeHead(200, {'Content-Type':'application/json'});
    res.end(JSON.stringify({id:'test',object:'chat.completion',created:1,model:'deepseek-v4-flash',choices:[{index:0,message,finish_reason:selection?'tool_calls':'stop'}],usage:{prompt_tokens:10,completion_tokens:10,total_tokens:20}}));
  });
  await new Promise(resolve=>mock.listen(0,'127.0.0.1',resolve));
  const previous = {...process.env};
  try {
    process.env.DEEPSEEK_API_KEY = 'test-only-not-a-real-key';
    process.env.DEEPSEEK_BASE_URL = `http://127.0.0.1:${mock.address().port}/v1`;
    process.env.DEEPSEEK_MODEL = 'deepseek-v4-flash';
    const config = {...configure(), root};
    await mkdir(path.join(root,'wiki','concepts'), {recursive:true});
    await writeFile(path.join(root,'wiki','index.md'), '# Test index\n- [[SVE检查]]\n');
    await writeFile(path.join(root,'wiki','concepts','sve-check.md'), '---\ntitle: SVE检查\nsummary: SVE尾部验证\nsources: []\n---\n这是手工测试夹具，不是LLM编译结果。检查尾部输入并保留标量参照。\n');
    const bridge = createBridge(config);
    const result = await bridge.query('SVE如何验证');
    assert.match(result.answer, /尾部/);
    assert.equal(result.references[0].page_id, 'concepts/sve-check');
    assert.equal(result.engine, 'llm-wiki-compiler');
    assert.ok(requests.length >= 2);
    for (const request of requests) {
      assert.equal(request.body.model, 'deepseek-v4-flash');
      assert.equal(request.body.thinking.type, 'disabled');
      assert.equal(request.url, '/v1/chat/completions');
    }
  } finally {
    for (const key of Object.keys(process.env)) if (!(key in previous)) delete process.env[key];
    Object.assign(process.env, previous);
    await new Promise(resolve=>mock.close(resolve));
    await rm(root, {recursive:true, force:true});
  }
});

test('HTTP bridge distinguishes invalid input and missing credentials', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(),'compiler-http-'));
  const server = createServer(createBridge({root,configured:false,model:'deepseek-v4-flash'}));
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  try {
    const base = `http://127.0.0.1:${server.address().port}`;
    assert.equal((await (await fetch(base+'/health')).json()).configured,false);
    const response = await fetch(base+'/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:'SVE验证'})});
    assert.equal(response.status,503);
    assert.equal((await response.json()).error,'model_not_configured');
    assert.equal((await fetch(base+'/query',{method:'POST',body:'{"question":"a"}'})).status,422);
  } finally { await new Promise(resolve=>server.close(resolve)); await rm(root,{recursive:true,force:true}); }
});
