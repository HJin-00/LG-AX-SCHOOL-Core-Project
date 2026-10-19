import test from 'node:test';
import assert from 'node:assert/strict';
import{saveConnection,readConnection}from './connectionStorage.js';
const account={username:'test1',demo_customer_id:'DEMO-U01'};
const session={session_id:'test-session',session_key:'fake-key',tool_access_token:'fake-token',demo_customer_id:'DEMO-U01',expires_at:200,identity_expires_at:150,identity_state:'demo_verified',scopes:['contract_terms'],contract:{monthly_fee:30000}};
function storage(){const entries=new Map();return {getItem:k=>entries.get(k)||null,setItem:(k,v)=>entries.set(k,v),removeItem:k=>entries.delete(k)};}
test('같은 탭·같은 로그인 계정의 유효한 연결만 복원 대상으로 읽는다',()=>{
 const s=storage();saveConnection(s,session,account);
 assert.equal(readConnection(s,account,100).session_id,session.session_id);
 assert.equal(readConnection(s,account,100).contract,undefined);
});
test('다른 로그인과 만료는 저장된 연결을 폐기한다',()=>{
 const s=storage();saveConnection(s,session,account);
 assert.equal(readConnection(s,{...account,username:'test2'},100),null);
 saveConnection(s,session,account);assert.equal(readConnection(s,account,151),null);
});
test('로그아웃·동의 철회는 저장값을 제거한다',()=>{
 const s=storage();saveConnection(s,session,account);saveConnection(s,null,account);
 assert.equal(readConnection(s,account,100),null);
});
