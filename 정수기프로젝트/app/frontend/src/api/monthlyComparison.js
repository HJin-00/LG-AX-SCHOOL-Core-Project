export const installationFields=new Set(['surface_material','drilling_needed','pump_needed','breaker_needed','outlet_needed','external_outlet_drilling','external_water_drilling','thick_sink','drilling_target']);
export function missingCostGroups(fields=[]){
 const unique=[...new Set(fields)];
 return [
  {id:'installation',label:'추가 설치비 별도',description:'타공·배관·전원 등 설치 환경에 따라 달라지는 비용이에요.',fields:unique.filter(k=>installationFields.has(k))},
  {id:'pricing',label:'신규 요금·가입 조건 확인',description:'표시한 요금의 적용 시점과 약정·관리 조건을 가입 전에 확인해요.',fields:unique.filter(k=>['future_price','new_subscription_terms'].includes(k))},
  {id:'initial',label:'초기 비용 확인',description:'등록비·기본 설치비·기타 초기비 중 아직 확인되지 않은 항목이에요.',fields:unique.filter(k=>['registration_fee','installation_fee','other_initial_fee'].includes(k))},
  {id:'other',label:'그 밖의 비용 확인',description:'아래 비용은 표시 금액에 아직 포함되지 않았어요.',fields:unique.filter(k=>!installationFields.has(k)&&!['future_price','new_subscription_terms','registration_fee','installation_fee','other_initial_fee'].includes(k))},
 ].filter(g=>g.fields.length);
}
export function monthlyComparison(option,months){
 if(!Number.isInteger(months)||months<1)return {amount:null,label:'월평균 계산 불가'};
 const selected=option.selected_card_benefit?.card_id&&option.selected_card_benefit.card_id!=='none'&&option.selected_card_benefit.eligibility!=='unconfirmed';
 const selectedTotal=selected?option.selected_card_scenario_total:null;
 const total=selectedTotal??option.estimated_total??option.scenario_total??option.confirmed_subtotal;
 const basis=selectedTotal!=null?'card':option.estimated_total!=null?'estimate':option.scenario_total!=null?'snapshot':'confirmed';
 return {amount:Number.isFinite(total)?Math.ceil(total/months):null,total,basis,label:basis==='card'?'선택 카드 조건을 가정한 월평균':basis==='estimate'?'비교 기간 월평균 부담':basis==='snapshot'?'공식 수집 요금 기준 월평균 참고 부담':'확인된 비용 기준 월평균',groups:missingCostGroups(option.missing_fields)};
}
