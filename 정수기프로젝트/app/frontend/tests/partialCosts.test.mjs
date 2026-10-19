import test from 'node:test';import assert from 'node:assert/strict';
import {monthlyComparison,missingCostGroups} from '../src/api/monthlyComparison.js';
test('설치비 미확인이어도 확인된 소계 월평균을 표시하되 총액은 채우지 않는다',()=>{
 const o={estimated_total:null,confirmed_subtotal:1074400,missing_fields:['drilling_needed','pump_needed']};
 const p=monthlyComparison(o,36);assert.equal(p.amount,29845);assert.equal(p.basis,'confirmed');assert.equal(o.estimated_total,null);assert.equal(p.groups[0].label,'추가 설치비 별도');
});
test('공식 수집 요금 가정·초기비 누락·카드·완전 누락을 구분한다',()=>{
 assert.equal(monthlyComparison({confirmed_subtotal:70000,scenario_total:1566400,estimated_total:null},36).basis,'snapshot');
 assert.equal(monthlyComparison({estimated_total:null,confirmed_subtotal:0},36).amount,0);
 assert.equal(monthlyComparison({},36).amount,null);
 assert.equal(monthlyComparison({confirmed_subtotal:70000},0).amount,null);
 assert.deepEqual(missingCostGroups(['future_price','registration_fee','outlet_needed','registration_fee']).map(g=>g.id),['installation','pricing','initial']);
 const r=monthlyComparison({confirmed_subtotal:100000,selected_card_scenario_total:80000,selected_card_benefit:{card_id:'kb',eligibility:'base'}},12);assert.equal(r.amount,6667);assert.equal(r.basis,'card');
});
