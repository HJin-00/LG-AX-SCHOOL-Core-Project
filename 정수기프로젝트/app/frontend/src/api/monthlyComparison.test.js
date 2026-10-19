import test from 'node:test';import assert from 'node:assert/strict';import{monthlyComparison}from './monthlyComparison.js';
test('일회성 비용을 포함한 전체 비교 비용을 동일 개월 수로 나눈다',()=>{
 assert.equal(monthlyComparison({estimated_total:360000},36).amount,10000);
 assert.equal(monthlyComparison({estimated_total:null,scenario_total:1496400},36).amount,41567);
});
test('확인 소계는 월평균 참고값으로만 표시한다',()=>{
 const r=monthlyComparison({estimated_total:null,confirmed_subtotal:70000},36);
 assert.equal(r.amount,1945);assert.equal(r.basis,'confirmed');assert.match(r.label,/확인된 비용/);
 assert.equal(monthlyComparison({estimated_total:0},0).amount,null);
});
