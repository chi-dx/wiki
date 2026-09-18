import http from 'node:http';
import { pathToFileURL } from 'node:url';
import { configure } from './config.mjs';
import { createBridge } from './bridge.mjs';

export function createServer(bridge) {
  return http.createServer(async (req, res) => {
    const send = (status, data) => { res.writeHead(status, {'Content-Type':'application/json; charset=utf-8'}); res.end(JSON.stringify(data)); };
    try {
      const url = new URL(req.url, 'http://localhost');
      if (req.method === 'GET' && url.pathname === '/health') return send(200, bridge.health());
      if (req.method === 'GET' && url.pathname === '/pages') return send(200, await bridge.catalog());
      if (req.method === 'GET' && url.pathname.startsWith('/pages/')) {
        const page = await bridge.page(decodeURIComponent(url.pathname.slice(7)));
        return send(page ? 200 : 404, page || {error:'not_found'});
      }
      if (req.method !== 'POST' || !['/query','/sync'].includes(url.pathname)) return send(404, {error:'not_found'});
      let size = 0; const chunks = [];
      for await (const chunk of req) {
        size += chunk.length;
        if (size > 8_000_000) return send(413, {error:'snapshot_too_large'});
        chunks.push(chunk);
      }
      const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if (!body || typeof body !== 'object' || Array.isArray(body)) return send(422, {error:'invalid_input'});
      if (url.pathname === '/query') {
        if (typeof body.question !== 'string' || body.question.trim().length < 2 || body.question.length > 1000) return send(422, {error:'invalid_question'});
        return send(200, await bridge.query(body.question));
      }
      // This private service is not published to the LAN by Compose.
      return send(200, await bridge.sync(body.documents, body.compile !== false));
    } catch (error) {
      const code = error.code || (error.name === 'ProviderUnavailableError' ? 'model_not_configured' : 'upstream_error');
      const status = code === 'model_not_configured' ? 503 : code === 'busy' ? 409 : code === 'invalid_input' || error instanceof SyntaxError ? 422 : 502;
      // Provider errors may embed credentials/request text. Never echo them.
      console.error(JSON.stringify({event:'compiler_request_failed', code, type:error.name}));
      send(status, {error:code});
    }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const config = configure();
  const server = createServer(createBridge(config));
  server.listen(config.port, config.host, () => console.log(`Compiler bridge http://${config.host}:${config.port} model=${config.model} configured=${config.configured}`));
}
