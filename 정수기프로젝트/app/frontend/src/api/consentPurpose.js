export const consentFields={
 contract_terms:{title:'내 제품·계약기간',description:'보유 모델·사용 유형·계약기간'},
 contract_costs:{title:'요금과 비용 비교',description:'계약 요금·정산 항목·예상 비용'},
 care_info:{title:'관리·필터 일정',description:'관리 방식과 방문·배송 일정'}
};
export function consentPurpose(topic,text=''){
 
 if(['cancel','renewal','timing'].includes(topic)||/비용|위약금|추가 부담|재구독|전환.*비교|월.*(?:요금|구독료)|청구|납부/.test(text))return {title:topic==='timing'?'날짜별 추가 부담 비교':'예상 비용 확인',scopes:['contract_terms','contract_costs']};
 
 return {title:'내 제품·계약기간 확인',scopes:['contract_terms']};
}
export function hasConsent(session,purpose){return !!session?.tool_access_token&&Date.now()<session.expires_at&&purpose.scopes.every(s=>session.scopes?.includes(s));}
