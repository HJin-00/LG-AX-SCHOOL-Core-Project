import test from 'node:test';
import assert from 'node:assert/strict';
import{consentPurpose,hasConsent}from './consentPurpose.js';
test('질문 목적에 해당하는 동의만 요청한다',()=>{
 assert.deepEqual(consentPurpose('contract','내 계약기간 알려줘').scopes,['contract_terms']);
 assert.deepEqual(consentPurpose('cancel').scopes,['contract_terms','contract_costs']);
 assert.deepEqual(consentPurpose('renewal').scopes,['contract_terms','contract_costs']);
 assert.deepEqual(consentPurpose('knowledge','의무기간이 뭐야').scopes,['contract_terms']);
});
test('기간 동의만으로 비용 권한이 생기지 않으며 만료도 검사한다',()=>{
 const session={tool_access_token:'test-only',expires_at:Date.now()+10000,scopes:['contract_terms']};
 assert.equal(hasConsent(session,consentPurpose('contract')),true);
 assert.equal(hasConsent(session,consentPurpose('renewal')),false);
 assert.equal(hasConsent({...session,expires_at:0},consentPurpose('contract')),false);
});
