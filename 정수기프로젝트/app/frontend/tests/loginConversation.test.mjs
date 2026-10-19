import test from 'node:test';import assert from 'node:assert/strict';
import {publicSessionAfterLogin,shouldResetConversation} from '../src/api/connectionState.js';
test('비로그인 공개 상담은 첫 로그인 때 같은 세션을 유지한다',()=>{
 const guest={session_id:'public-chat',expires_at:200,scopes:[]};
 assert.equal(publicSessionAfterLogin(null,guest,100),guest);
 assert.equal(shouldResetConversation(null,'DEMO-U01'),false);
});
test('계정 변경·개인 계약 권한·만료된 세션은 로그인에 넘기지 않는다',()=>{
 const guest={session_id:'public-chat',expires_at:200};
 assert.equal(publicSessionAfterLogin({demo_customer_id:'DEMO-U01'},guest,100),null);
 for(const field of ['session_key','tool_access_token','demo_customer_id'])assert.equal(publicSessionAfterLogin(null,{...guest,[field]:'private'},100),null);
 assert.equal(publicSessionAfterLogin(null,guest,201),null);
 assert.equal(shouldResetConversation('DEMO-U01','DEMO-U02'),true);
 assert.equal(shouldResetConversation('DEMO-U01',null),true);
});
