import React from 'react';
import CustomerProductPicker from '../account/CustomerProductPicker.jsx';
const formatDate=value=>value?value.replaceAll('-','.'):'';
export default function ContractInquiry({authenticated,selectedContract,onChangeContract,onAskQuestion}){
 const subscription=selectedContract?.serviceType==='subscription';
 return <article className="agent-message"><div className="agent-avatar" aria-hidden="true">▣</div><div className="agent-content contract-inquiry"><div className="agent-name">정수기 상담 가이드<span>계약 문의</span></div>
 {!authenticated||!selectedContract?<CustomerProductPicker/>:<section className="contract-selected-panel"><div className="contract-current-card"><div className="contract-current-heading"><strong>현재 상담 중인 제품</strong><button type="button" onClick={onChangeContract}>조회 범위 변경</button></div><h2>{selectedContract.productName}</h2><dl className="demo-contract-details">{subscription?[['계약 시작',selectedContract.contractStart],['의무사용 종료',selectedContract.mandatoryUseEnd],['전체 계약 종료',selectedContract.contractEnd],['월 구독료',selectedContract.monthlyFee!=null?`${selectedContract.monthlyFee.toLocaleString()}원`:null]].filter(([,v])=>v).map(([label,value])=><div key={label}><dt>{label}</dt><dd>{label.includes('종료')||label==='계약 시작'?formatDate(value):value}</dd></div>):<p>일반 구매 고객은 구독 계약이 없습니다.</p>}</dl></div><h2>무엇이 궁금하신가요?</h2><div className="contract-question-list">{(subscription?['내 계약기간 알려줘','해지 예상 비용을 알고 싶어','두 날짜의 추가 부담을 비교하고 싶어']:['구독 계약이 있는지 확인해줘','제품 관리에 관해 질문하고 싶어']).map(q=><button type="button" key={q} onClick={()=>onAskQuestion(q)}>{q}</button>)}</div></section>}
 </div></article>;
}
