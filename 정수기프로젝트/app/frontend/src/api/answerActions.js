// 서버가 반환한 허용 행동만 표시한다. 답변 문장에서 키워드를 추출하지 않는다.
export const answerActions={
 official_support:{label:'공식 문제 해결 상담',question:'새 제품 추천 대신 사용 중인 불편을 상담할 LG 공식 AI Chat 연결을 안내해줘.'},
 compare_new:{label:'새 정수기와 비교하기'},
 exit_cost:{label:'지금 해지 비용 확인하기',question:'오늘 기준으로 내 계약의 예상 해지 정산 비용을 확인해줘.'},
 contract_fees:{label:'현재 계약 요금 알아보기',question:'내 계약의 연차별 월요금과 의무사용기간 이후 적용 요금을 설명해줘.'},
 contract_terms:{label:'계약 종료일과 조건 확인하기',question:'내 계약의 의무사용 종료일과 전체 계약 종료일, 두 날짜의 차이를 설명해줘.'},
};
export function availableAnswerActions(message){
 if(message.status!=='answered'||message.missing_fields?.length)return [];
 return [...new Set(message.next_actions||[])].filter(id=>answerActions[id]).map(id=>({id,...answerActions[id]}));
}
