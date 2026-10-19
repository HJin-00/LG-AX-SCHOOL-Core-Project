import test from 'node:test';
import assert from 'node:assert/strict';
import {cardDiscount} from './cardBenefit.js';
const card={months:36,promotion_start:'2026-10-01',promotion_end:'2026-10-31',tiers:[{spend:300000,base:10000,promotion:5000,months:36},{spend:800000,base:15000,promotion:5000,months:36}]};
const input={card,monthlyFee:28900,spend:300000,eligible:true,today:'2026-10-07'};
test('실적 경계와 자격·기간 조건',()=>{
 assert.equal(cardDiscount({...input,spend:299999}),0);
 assert.equal(cardDiscount(input),15000);
 assert.equal(cardDiscount({...input,spend:800000}),20000);
 assert.equal(cardDiscount({...input,eligible:false}),0);
 assert.equal(cardDiscount({...input,today:'2026-11-01'}),10000);
 assert.equal(cardDiscount({...input,spend:''}),0);
 assert.equal(cardDiscount({...input,spend:-1}),0);
 assert.equal(cardDiscount({...input,monthlyFee:9000}),9000);
});
