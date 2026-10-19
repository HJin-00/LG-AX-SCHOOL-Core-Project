import test from 'node:test';import assert from 'node:assert/strict';
import {cardDiscount,cardComponents}from '../src/components/products/cardBenefit.js';
import {candidateRequest}from '../src/api/renewalSelection.js';
import {monthlyComparison}from '../src/api/monthlyComparison.js';
const kb={id:'kb',promotion_start:'2026-10-01',promotion_end:'2026-10-31',promotion_service_start:'2026-11-01',promotion_service_end:'2030-01-31',months:36,tiers:[{spend:300000,base:10000,promotion:5000},{spend:800000,base:15000,promotion:5000}]};
const args={card:kb,monthlyFee:49900,spend:800000,eligibility:'promotion',applicationDate:'2026-10-14',today:'2026-10-14'};
test('KB: 실제 추가 할인 시작·36/37 회차·기본 할인 유지',()=>{assert.equal(cardDiscount({...args,chargeDate:'2026-10-14'}),15000);assert.equal(cardDiscount({...args,chargeDate:'2026-11-14'}),20000);assert.equal(cardDiscount({...args,chargeDate:'2029-10-14',promotionMonth:36}),20000);assert.equal(cardDiscount({...args,chargeDate:'2029-11-14',promotionMonth:37}),15000);});
test('카드 미사용·미확인·실적미달·월요금 한도',()=>{assert.equal(cardDiscount({...args,card:null}),0);assert.equal(cardDiscount({...args,eligibility:'unconfirmed'}),0);assert.equal(cardDiscount({...args,spend:299999}),0);assert.equal(cardDiscount({...args,monthlyFee:10900,chargeDate:'2026-11-14'}),10900);});
test('등록 기간 밖에는 기본 할인만 적용',()=>{const r=cardComponents({...args,applicationDate:'2026-12-01',chargeDate:'2026-12-01'});assert.equal(r.base,15000);assert.equal(r.promotion,0);});
test('다른 제품 요청은 선택 모델만 해제하고 조건·날짜·카드를 유지',()=>{const r=candidateRequest([{requestQuestion:'조건\n{"required_features":["얼음"],"installation_type":"desk","care_mode":"visit"}'}],{offer_id:'OLD',planned_start_date:'2026-12-01',comparison_months:24,card_id:'kb',card_spend:800000,card_eligibility:'base'});assert.equal(r.offer_id,undefined);assert.deepEqual(r.required_features,['얼음']);assert.equal(r.planned_start_date,'2026-12-01');assert.equal(r.comparison_months,24);assert.equal(r.card_id,'kb');});
test('선택 카드 조건의 총액과 월평균 가정 표시',()=>{const r=monthlyComparison({estimated_total:null,scenario_total:120000,selected_card_scenario_total:60000,selected_card_benefit:{card_id:'kb',eligibility:'base'}},12);assert.equal(r.amount,5000);assert.match(r.label,/가정/);});

test('카드 재계산은 제출 순간 날짜·실적 입력을 읽고 미입력을 구분한다',async()=>{
 const {submittedCardSelection}=await import('../src/api/renewalSelection.js');const form=new FormData();form.set('card_id','kb');form.set('card_spend','800000');form.set('card_eligibility','promotion');form.set('card_application_date','2026-10-14');
 const result=submittedCardSelection(form,{card_application_date:'2026-12-01',card_spend:null});assert.equal(result.card_application_date,'2026-10-14');assert.equal(result.card_spend,800000);
 form.set('card_spend','');assert.equal(submittedCardSelection(form,result).card_spend,null);
});
