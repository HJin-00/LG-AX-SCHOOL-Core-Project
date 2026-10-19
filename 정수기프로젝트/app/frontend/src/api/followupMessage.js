export const reasonLabels={personal:'개인 사정·비용 부담',feature_upgrade:'필요한 기능·설치 공간',service_dispute:'관리 미이행·수리 지연·반복 고장'};
export function buildFollowupMessage(input,requestTopic){
 const reason=input.exit_reason;
 let purpose=requestTopic==='renewal'?'유지·재구독 비교를 계속해줘. 기존 계약 해지·정산과 신규 구독 비용을 구분해줘.':'앞선 상담을 다음 단계로 이어가줘.';
 if(reason==='service_dispute')purpose='변경을 고민하는 이유는 관리 미이행·수리 지연·반복 고장입니다. 약정과 요청·방문·수리 이력을 가장 필요한 질문 하나로 확인하고 상담 준비를 도와줘. 일반 해지 비용으로 단정하지 마.';
 if(reason==='feature_upgrade')purpose='변경을 고민하는 이유는 필요한 기능·설치 공간 때문입니다. 앞선 교체 고민을 이어서 원하는 기능을 질문하고 제품 후보 선택을 도와줘. 날짜가 미정이면 계약 조회 후 후보 시점을 제안할 수 있게 안내해줘.';
 if(reason==='personal')purpose='변경을 고민하는 이유는 개인 사정·비용 부담입니다. 앞선 교체 고민을 이어서 기존 계약 유지와 전환의 확인 항목을 안내해줘. 날짜를 모르면 필요한 동의 후 계약기간과 시점 후보를 확인하도록 도와줘.';
 if(input.symptom)purpose='고객이 입력한 현재 질문이나 증상을 기준으로 상담을 이어가줘. 이전 주제와 달라졌다면 새 요청에 맞는 도구를 선택해줘.';
 if(input.required_features)purpose='선택한 기능 조건으로 공식 제품 후보를 확인해줘. 관리 방식과 가격의 적용 조건은 별도로 안내해줘.';
 if(input.service_history)purpose='앞선 관리·수리 문제에 대한 이력을 입력했어요. 이미 제공한 내용을 다시 요구하지 말고 필요한 증빙과 다음 상담에서 확인할 항목을 정리해줘. 책임·위약금 면제는 확정하지 마.';
 return purpose+'\n'+JSON.stringify(input);
}
