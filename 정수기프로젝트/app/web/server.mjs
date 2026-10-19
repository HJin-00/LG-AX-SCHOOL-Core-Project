/** React 요청을 FastAPI로 전달하는 로컬 Node 중계 서버. Agent 판단은 하지 않습니다. */
import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(fileURLToPath(new URL('../frontend/dist/', import.meta.url))); 
const api = new URL(process.env.FASTAPI_URL || 'http://127.0.0.1:8000');
if (!['http:', 'https:'].includes(api.protocol) || api.username || api.password || api.search || api.hash) throw new Error('FASTAPI_URL 설정을 확인하세요.');
const port = Number(process.env.WEB_PORT || 3001);
const allowed = (method, route) =>
  (method === 'GET' && (['/health','/demo-profiles','/contracts/current','/connection/current','/auth/me','/conversation/current'].includes(route) || /^\/briefs\/[A-Za-z0-9_-]{8,80}$/.test(route))) ||
  (method === 'POST' && (['/chat', '/demo-sessions', '/auth/login','/auth/logout','/guest-sessions','/conversation/state','/conversation/reset'].includes(route) || /^\/demo-sessions\/[A-Za-z0-9_-]{8,128}\/(consent|identity)$/.test(route)));
const headersToForward = ['content-type', 'x-session-id', 'x-demo-session-key', 'x-tool-access-token'];
const mime = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.ico':'image/x-icon'};
function json(res, status, answer, code) { res.writeHead(status, {'content-type':'application/json; charset=utf-8','cache-control':'no-store'}); res.end(JSON.stringify({answer,code})); }

export function createWebServer(upstream = api) {
  return http.createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'same-origin');
    if (!/^(localhost|127\.0\.0\.1)(:\d+)?$/.test(req.headers.host || '')) return json(res,403,'허용된 로컬 주소로 접속해 주세요.','HOST_DENIED');
    const url = new URL(req.url, 'http://127.0.0.1');
    if (url.pathname.startsWith('/api/')) {
      const route = url.pathname.slice(4);
      if (!allowed(req.method, route) || url.search) return json(res,404,'요청한 기능을 찾을 수 없습니다.','NOT_FOUND');
      const origin = req.headers.origin;
      if (origin && ![`http://${req.headers.host}`, 'http://127.0.0.1:5173', 'http://localhost:5173'].includes(origin)) return json(res,403,'허용된 상담 화면에서 요청해 주세요.','ORIGIN_DENIED');
      if (req.method === 'POST' && !String(req.headers['content-type'] || '').startsWith('application/json')) return json(res,415,'JSON 요청이 필요합니다.','INVALID_CONTENT_TYPE');
      try {
        const chunks=[];let size=0;
        for await (const chunk of req) {
          size+=chunk.length;
          if (size > (route === '/conversation/state' ? 2097152 : 32768)) return json(res,413,'질문이 너무 깁니다. 내용을 줄여 주세요.','INPUT_TOO_LARGE');
          chunks.push(chunk);
        }
        const body=Buffer.concat(chunks).toString('utf8');
        const headers = Object.fromEntries(headersToForward.filter(k => req.headers[k]).map(k => [k, req.headers[k]]));
        const loginCookie=String(req.headers.cookie||'').split(';').map(v=>v.trim()).find(v=>/^water_login=[A-Za-z0-9_-]+$/.test(v));
        if(loginCookie)headers.cookie=loginCookie;
        if(req.headers.origin)headers.origin=req.headers.origin;
        const response = await fetch(new URL(route, upstream), {method:req.method,headers,body:req.method==='POST'?body:undefined,signal:AbortSignal.timeout(95000),redirect:'error'});
        res.statusCode = response.status;
        res.setHeader('Cache-Control','no-store');
        for (const name of ['content-type','content-disposition']) if (response.headers.has(name)) res.setHeader(name,response.headers.get(name));
        if(route==='/auth/login'||route==='/auth/logout'){const cookies=response.headers.getSetCookie();if(cookies.length)res.setHeader('set-cookie',cookies);}
        // 응답을 바꾸거나 재요청하지 않습니다. 키·토큰·질문을 로그에 기록하지 않습니다.
        res.end(Buffer.from(await response.arrayBuffer()));
      } catch (error) {
        const timeout = ['TimeoutError','AbortError'].includes(error.name);
        json(res, timeout?504:502, timeout?'답변 시간이 길어졌습니다. 잠시 후 다시 시도해 주세요.':'상담 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.',timeout?'UPSTREAM_TIMEOUT':'UPSTREAM_UNAVAILABLE');
      }
      return;
    }
    if (req.method !== 'GET' && req.method !== 'HEAD') return json(res,405,'허용되지 않은 요청입니다.','METHOD_NOT_ALLOWED');
    try {
      const decoded = decodeURIComponent(url.pathname);
      let target = path.resolve(root, '.' + decoded);
      if (target !== root && !target.startsWith(root + path.sep)) return json(res,404,'파일을 찾을 수 없습니다.','NOT_FOUND');
      if (target === root || (await stat(target).catch(()=>null))?.isDirectory()) target = path.join(root,'index.html');
      let content;
      try { content = await readFile(target); }
      catch {
        if (path.extname(target)) return json(res,404,'파일을 찾을 수 없습니다.','NOT_FOUND');
        target = path.join(root,'index.html'); content = await readFile(target);
      }
      res.writeHead(200, {'content-type':mime[path.extname(target)] || 'application/octet-stream','cache-control':'no-cache'});
      res.end(req.method==='HEAD'?undefined:content);
    } catch { json(res,503,'화면 빌드가 필요합니다. frontend에서 npm run build를 실행해 주세요.','FRONTEND_NOT_BUILT'); }
  });
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  createWebServer().listen(port,'127.0.0.1',()=>console.log(`정수기 상담 화면: http://127.0.0.1:${port}`));
}
