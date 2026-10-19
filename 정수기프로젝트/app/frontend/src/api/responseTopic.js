export const responseLabels={usage:'기능·사용 방법',features:'제품 기능 비교',troubleshoot:'사용 오류',care:'필터·관리 서비스',contract:'내 계약·구독 정보',cancel:'해지 전 비용 확인',renewal:'유지·재구독 비교',timing:'날짜별 부담 비교',knowledge:'계약 조건 질문',recommend:'나에게 맞는 제품',purchase_method:'구매·구독 선택',installation:'설치 조건·예상 비용',product_information:'제품 가격·혜택'};
export function responseTopic(result,fallback,origin){
 if(result.cards?.some(c=>c.type==='renewal_timing')&&origin==='cancel')return 'cancel';
 if(result.resolved_topic)return result.resolved_topic;
 if(result.cards?.some(c=>['renewal_catalog','renewal_comparison','renewal_timing'].includes(c.type)))return 'renewal';
 if(result.topic==='contract')return 'contract';
 if(result.topic==='troubleshoot')return 'troubleshoot';
 if(result.topic==='care_subscription')return fallback==='usage'?'usage':'care';
 return fallback;
}
