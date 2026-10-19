import test from 'node:test';
import assert from 'node:assert/strict';
import {groupColorOffers}from './productGroups.js';
const offer=(id,family,color,features={온수:true},care='방문관리')=>({offer_id:id,model_id:id,source_kind:'official',contract_months:72,care_details:care,product:{family_id:family,color_name:color,features}});
test('검수된 같은 제품군·같은 기능 색상만 한 카드로 묶는다',()=>{
 const groups=groupColorOffers([offer('H','WD721R','화이트'),offer('E','WD721R','베이지'),offer('X','WD722R','화이트')]);
 assert.deepEqual(groups.map(g=>g.map(o=>o.model_id)),[['H','E'],['X']]);
});
test('제품군 ID가 같아도 기능·관리 조건이 다르면 별도 카드다',()=>{
 const rows=[offer('A','WD721R','화이트'),offer('B','WD721R','블랙',{온수:false}),offer('C','WD721R','베이지',{온수:true},'자가관리')];
 assert.equal(groupColorOffers(rows).length,3);
});
test('검수된 제품군 정보가 없으면 비슷한 모델명도 합치지 않는다',()=>{
 assert.equal(groupColorOffers([offer('WD520VCT',null,'화이트'),offer('WD520VHT',null,'화이트')]).length,2);
});
