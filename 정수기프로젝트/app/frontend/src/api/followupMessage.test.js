import test from'node:test';import assert from'node:assert/strict';
import{buildFollowupMessage,reasonLabels}from'./followupMessage.js';
test('이유 선택 뒤 목적과 코드가 함께 전달된다',()=>{
 for(const reason of Object.keys(reasonLabels)){
  const value=buildFollowupMessage({exit_reason:reason},'contract');
  assert.equal(JSON.parse(value.slice(value.indexOf('{'))).exit_reason,reason);
  assert.ok(value.includes(reason==='service_dispute'?'이력을':reason==='feature_upgrade'?'기능':'계약'));
 }
});
test('비교 날짜·제품과 제공한 서비스 이력을 유지한다',()=>{
 const request={offer_id:'LG-SNAPSHOT-WD723RH',planned_start_date:'2026-11-15'};
 const value=buildFollowupMessage(request,'renewal');assert.deepEqual(JSON.parse(value.slice(value.indexOf('{'))),request);
 assert.ok(value.includes('유지·재구독'));
 assert.ok(buildFollowupMessage({service_history:'방문 2회 취소'},'contract').includes('다시 요구하지'));
});
