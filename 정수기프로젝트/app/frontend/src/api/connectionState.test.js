import test from 'node:test';
import assert from 'node:assert/strict';
import {isProductConnected,shouldResetConversation} from './connectionState.js';
const session={tool_access_token:'fake',demo_customer_id:'DEMO-U01',identity_state:'demo_verified',expires_at:200,identity_expires_at:200,scopes:['contract_terms']};
const product={demo_customer_id:'DEMO-U01',modelId:'WD520VCT'};
test('연결 표시는 실제 제품과 유효한 조회 권한을 함께 요구한다',()=>{
 assert.equal(isProductConnected(session,product,100),true);
 assert.equal(isProductConnected(session,null,100),false);
 assert.equal(isProductConnected(session,product,201),false);
 assert.equal(isProductConnected({...session,tool_access_token:null},product,100),false);
 assert.equal(isProductConnected({...session,scopes:[]},product,100),false);
 assert.equal(isProductConnected(session,{...product,demo_customer_id:'DEMO-U02'},100),false);
});

test('계약 연결과 같은 고객 재동의는 기존 대화를 유지한다',()=>{
 assert.equal(shouldResetConversation(null,'DEMO-U01'),false);
 assert.equal(shouldResetConversation('DEMO-U01','DEMO-U01'),false);
});
test('다른 고객 변경과 로그아웃은 이전 대화를 지운다',()=>{
 assert.equal(shouldResetConversation('DEMO-U01','DEMO-U02'),true);
 assert.equal(shouldResetConversation('DEMO-U01',null),true);
});
