import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export function configure() {
  // Deliberately do not reuse unrelated OpenAI credentials from the machine.
  process.env.LLMWIKI_PROVIDER = 'openai';
  process.env.OPENAI_BASE_URL = process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com';
  process.env.OPENAI_API_KEY = process.env.DEEPSEEK_API_KEY || '';
  process.env.LLMWIKI_MODEL = process.env.DEEPSEEK_MODEL || 'deepseek-v4-flash';
  process.env.LLMWIKI_OUTPUT_LANG = 'zh';
  process.env.LLMWIKI_OPENAI_EXTRA_BODY = JSON.stringify({thinking: {type: 'disabled'}});
  process.env.LLMWIKI_REQUEST_TIMEOUT_MS = process.env.COMPILER_MODEL_TIMEOUT_MS || '90000';
  return {
    root: path.resolve(repo, process.env.COMPILER_ROOT || 'data/upstream-compiler'),
    host: process.env.COMPILER_HOST || '127.0.0.1',
    port: Number(process.env.COMPILER_PORT || '8010'),
    configured: Boolean(process.env.DEEPSEEK_API_KEY?.trim()),
    model: process.env.LLMWIKI_MODEL,
  };
}
