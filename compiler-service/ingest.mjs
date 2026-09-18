import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { configure } from './config.mjs';
const config = configure();
const documents = JSON.parse(await readFile(fileURLToPath(new URL('../fixtures/wiki.json', import.meta.url)), 'utf8'));
const compile = !process.argv.includes('--no-compile');
const response = await fetch(`http://127.0.0.1:${config.port}/sync`, {
  method:'POST', headers:{'Content-Type':'application/json'},
  body:JSON.stringify({documents, compile}), signal:AbortSignal.timeout(900000),
});
const result = await response.json();
if (!response.ok) { console.error(result.error); process.exitCode = 1; }
else console.log(JSON.stringify({ingested:result.ingested, removed:result.removed, total:result.total, compiled:result.compiled}));
