import test from 'node:test';import assert from 'node:assert/strict';import{responseTopic,responseLabels}from './responseTopic.js';
test('오류 버튼에서 시작해도 실제 계약·비용 답변에 맞춰 주제를 바꾼다',()=>{
 assert.equal(responseTopic({resolved_topic:'contract',topic:'contract'},'troubleshoot'),'contract');
 assert.equal(responseTopic({resolved_topic:'cancel',topic:'contract'},'troubleshoot'),'cancel');
 assert.equal(responseLabels.contract,'내 계약·구독 정보');
 assert.equal(responseTopic({resolved_topic:'usage',topic:'purchase'},'cancel'),'usage');
});
test('해지 상담에서 실제 후보일 카드를 받으면 원래 비용 상담 흐름을 유지한다',()=>{
 const result={resolved_topic:'contract',topic:'contract',cards:[{type:'renewal_timing'}]};
 assert.equal(responseTopic(result,'cancel','cancel'),'cancel');
 assert.equal(responseTopic(result,'renewal','renewal'),'contract');
 assert.equal(responseTopic({resolved_topic:'contract',topic:'contract'},'cancel'),'contract');
});
