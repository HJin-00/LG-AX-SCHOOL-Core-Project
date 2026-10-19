import {test, before, after} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {once} from 'node:events';
import {readdir} from 'node:fs/promises';
import {createWebServer} from './server.mjs';
let upstream,server,base;
before(async()=>{
 upstream=http.createServer(async(req,res)=>{
  if(req.url.startsWith('/briefs/')){res.writeHead(200,{'content-type':'text/markdown','content-disposition':'attachment; filename="brief.md"'});res.end('# 준비서\n합성 데이터');return;}
  let body='';for await(const chunk of req)body+=chunk;
  res.writeHead(req.url==='/chat'?403:200,{'content-type':'application/json',...(req.url==='/auth/login'?{'set-cookie':'water_login=test-token; Path=/; HttpOnly; SameSite=Strict'}:{})});
  res.end(JSON.stringify({route:req.url,method:req.method,body:body?JSON.parse(body):null,key:req.headers['x-demo-session-key'],token:req.headers['x-tool-access-token'],cookie:req.headers.cookie}));
 });upstream.listen(0,'127.0.0.1');await once(upstream,'listening');
 server=createWebServer(new URL(`http://127.0.0.1:${upstream.address().port}`));server.listen(0,'127.0.0.1');await once(server,'listening');base=`http://127.0.0.1:${server.address().port}`;
});
after(async()=>{await Promise.all([new Promise(r=>server.close(r)),new Promise(r=>upstream.close(r))]);});
test('팀원 디자인의 JPEG 사진을 올바른 이미지 형식으로 제공한다',async()=>{
 const files=await readdir(new URL('../frontend/dist/assets/',import.meta.url));
 const name=files.find(n=>n.endsWith('.jpg'));
 assert(name,'새 홈페이지 제품 사진이 빌드에 포함되어야 한다');
 const response=await fetch(base+'/assets/'+name);
 assert.equal(response.status,200);assert.equal(response.headers.get('content-type'),'image/jpeg');
 const bytes=new Uint8Array(await response.arrayBuffer());assert.equal(bytes[0],255);assert.equal(bytes[1],216);
});
test('등록된 요청 경로만 허용하고 외부 Origin을 거절한다',async()=>{
 assert.equal((await fetch(base+'/api/admin')).status,404);
 const badHost=await new Promise((resolve,reject)=>{const req=http.get(base+'/api/health',{headers:{host:'external.example'}},r=>{r.resume();resolve(r.statusCode);});req.on('error',reject);});
 assert.equal(badHost,403);
 assert.equal((await fetch(base+'/api/health?target=elsewhere')).status,404);
 assert.equal((await fetch(base+'/api/health',{headers:{Origin:'https://untrusted.example'}})).status,403);
});
test('서버 상태를 동일 출처 API로 전달한다',async()=>{
 const r=await fetch(base+'/api/health');assert.equal(r.status,200);assert.equal((await r.json()).route,'/health');assert.equal(r.headers.get('cache-control'),'no-store');
});
test('상담 JSON·권한 헤더를 전달하며 upstream 403을 그대로 보존한다',async()=>{
 const r=await fetch(base+'/api/chat',{method:'POST',headers:{'content-type':'application/json','x-demo-session-key':'demo-key','x-tool-access-token':'demo-token','cookie':'must-not-forward'},body:JSON.stringify({session_id:'demo-session',message:'계약 확인'})});
 assert.equal(r.status,403);const d=await r.json();assert.equal(d.key,'demo-key');assert.equal(d.token,'demo-token');assert.equal(d.cookie,undefined);assert.equal(d.body.message,'계약 확인');
});
test('잘못된 Content-Type과 큰 요청을 제한한다',async()=>{
 assert.equal((await fetch(base+'/api/chat',{method:'POST',body:'plain'})).status,415);
 assert.equal((await fetch(base+'/api/chat',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({message:'x'.repeat(40000)})})).status,413);
});
test('준비서 원문과 다운로드 헤더를 그대로 전달한다',async()=>{
 const r=await fetch(base+'/api/briefs/12345678',{headers:{'x-session-id':'session-id'}});assert.equal(r.status,200);assert.match(r.headers.get('content-disposition'),/brief.md/);assert.equal(await r.text(),'# 준비서\n합성 데이터');
});

test('빌드 화면과 자산을 제공하고 없는 자산은 404로 처리한다',async()=>{
 const r=await fetch(base+'/');assert.equal(r.status,200);assert.match(await r.text(),/\/assets\//);assert.match(r.headers.get('content-type'),/text\/html/);
 assert.equal((await fetch(base+'/assets/missing.js')).status,404);
});
test('새 React의 고객 목록과 승인된 계약 경로를 중계한다',async()=>{
 for(const route of ['/demo-profiles','/contracts/current']){
  const r=await fetch(base+'/api'+route,{headers:{'x-session-id':'demo-session','x-demo-session-key':'demo-key','x-tool-access-token':'demo-token'}});
  assert.equal(r.status,200);assert.equal((await r.json()).route,route);
 }
});

test('본인확인 경로만 허용하고 종료한 설치 API는 차단한다',async()=>{
 for(const route of ['/demo-sessions/demo-session-123/identity']){
  const r=await fetch(base+'/api'+route,{method:'POST',headers:{'content-type':'application/json','x-demo-session-key':'demo-key'},body:JSON.stringify({outcome:'success'})});
  assert.equal(r.status,200);const d=await r.json();assert.equal(d.route,route);assert.equal(d.key,'demo-key');
 }
 assert.equal((await fetch(base+'/api/demo-sessions/demo-session-123/identity',{method:'GET'})).status,404);
 assert.equal((await fetch(base+'/api/installation-estimates',{method:'POST',headers:{'content-type':'application/json'},body:'{}'})).status,404);
});

test('로그인 쿠키만 전달하고 인증 응답 쿠키를 보존한다',async()=>{
 const r=await fetch(base+'/api/auth/login',{method:'POST',headers:{'content-type':'application/json','cookie':'other=private; water_login=demo-session-token'},body:JSON.stringify({username:'test',password:'fixture-only'})});
 const d=await r.json();assert.equal(d.cookie,'water_login=demo-session-token');assert.match(r.headers.get('set-cookie'),/HttpOnly/);
 const me=await fetch(base+'/api/auth/me');assert.equal(me.status,200);
});

test('상담 복원·초기화 경로와 큰 상담 스냅샷을 권한 헤더와 함께 중계한다',async()=>{
 const headers={'content-type':'application/json','x-session-id':'demo-session','x-demo-session-key':'demo-key','x-tool-access-token':'demo-token'};
 const current=await fetch(base+'/api/conversation/current',{headers});assert.equal(current.status,200);assert.equal((await current.json()).token,'demo-token');
 for(const route of ['/conversation/state','/conversation/reset']){
  const body=route.endsWith('state')?{state:{messages:[{text:'x'.repeat(40000)}]}}:{};
  const r=await fetch(base+'/api'+route,{method:'POST',headers,body:JSON.stringify(body)});assert.equal(r.status,200);assert.equal((await r.json()).route,route);
 }
 assert.equal((await fetch(base+'/api/conversation/current',{method:'POST',headers,body:'{}'})).status,404);
});
