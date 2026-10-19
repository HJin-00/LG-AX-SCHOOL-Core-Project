import {availableAnswerActions} from '../../api/answerActions.js';
import {submittedCardSelection} from '../../api/renewalSelection.js';
import {costGapExplanation} from '../../api/costGapExplanation.js';
import CardSelection,{defaultCardSelection,localToday} from '../products/CardSelection.jsx';
import InlineConsent from '../account/InlineConsent.jsx';
import ProductCarousel from '../products/ProductCarousel.jsx';
import ColorChoices from '../products/ColorChoices.jsx';
import{groupColorOffers}from '../../api/productGroups.js';
import{monthlyComparison,missingCostGroups}from '../../api/monthlyComparison.js';
import React,{useState,useRef} from 'react';
import SourceBox from './SourceBox.jsx';
import {cardDiscount} from '../products/cardBenefit.js';

function DisplayLabel({text}){return <>{String(text||'').replaceAll('시연용 ','').replace(/\((합성 규칙|가상 청구 내역|가상 입력)\)/g,'').trim()}</>;}
function DataBasis(){return <details className="answer-details data-basis"><summary>자료 기준</summary><p>제품 기능은 공식 자료를 바탕으로 안내합니다. 현재 계약·구독 요금과 관리 일정은 가상 데이터이며 실제 LG 조회·견적·접수가 아닙니다.</p></details>;}

function ContractCard({ data,onUseTiming,disabled }) {
  const [reviewDate,setReviewDate]=useState(data.period_summary?.exit_date||'');
  const periods = data.period_summary || {};
  const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul'}).format(new Date());
  const periodLabels = [
    ['의무사용 종료', periods.mandatory_end],
    ['전체 계약 종료', periods.contract_end],
    ['해지 검토일', periods.exit_date],
  ];

  return (
    <div className="contract-card">
      {periods.exit_date&&<div className="exit-cost-summary"><span>{data.estimated_total==null?'확인된 비용 소계':'총 예상 해지 비용'}</span><strong>{(data.estimated_total??data.confirmed_subtotal).toLocaleString('ko-KR')}<small>원</small></strong><p>{periods.exit_date===today?`해지 검토일은 오늘(${periods.exit_date})로 계산했어요.`:`해지 검토일 ${periods.exit_date} 기준으로 계산했어요.`}</p>{data.estimated_total==null&&<p>미확인 비용이 있어 전체 금액은 아직 확정할 수 없어요.</p>}</div>}
      <strong>항목별 비용·계약 정보</strong>
      <dl>
        {periodLabels.map(([label, value]) =>
          value ? (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ) : null,
        )}
        {(data.cost_items || []).map((item) => (
          <div key={item.name}>
            <dt><DisplayLabel text={item.name}/></dt>
            <dd>
              {item.status === 'unverified'
                ? '미확인'
                : `${(item.amount ?? 0).toLocaleString('ko-KR')}원`}
            </dd>
          </div>
        ))}
        <div>
          <dt>확인된 금액 소계</dt>
          <dd>{data.confirmed_subtotal!=null?`${data.confirmed_subtotal.toLocaleString('ko-KR')}원`:'미확인'}</dd>
        </div>
        {data.estimated_total != null && (
          <div>
            <dt>예상 합계</dt>
            <dd>{data.estimated_total.toLocaleString('ko-KR')}원</dd>
          </div>
        )}
      </dl>
      {periods.exit_date&&<form className="renewal-date-controls" onSubmit={e=>{e.preventDefault();const chosen=new FormData(e.currentTarget).get('exit_date');if(chosen)onUseTiming?.(String(chosen),{requestContextTopic:'cancel'});}}><label>다른 날짜로 확인하기 · 해지 검토일<input name="exit_date" aria-label="해지 검토일" type="date" required value={reviewDate} disabled={disabled} onInput={e=>setReviewDate(e.currentTarget.value)} onChange={e=>setReviewDate(e.target.value)}/></label><button className="ui-button secondary" disabled={disabled}>선택한 날짜로 다시 계산</button></form>}
      {data.limitations && <details className="answer-details"><summary>자료 기준·계산 범위</summary><p>{data.limitations}</p></details>}
    </div>
  );
}

function ComparisonCard({data}) {
  return <div className="comparison-card"><div className="comparison-heading"><strong>해지 날짜별 추가 부담</strong><span>기준일 {data.comparison_date}</span></div><div className="comparison-options">{data.options.map((option,index)=><section className="comparison-option" key={option.exit_date+index}><div className="comparison-date"><span>선택 {index+1}</span><strong>{option.exit_date}</strong></div><div className="comparison-total">{option.additional_total.toLocaleString('ko-KR')}<small>원</small></div><dl><div><dt>추가 구독료</dt><dd>{option.additional_subscription_fee.toLocaleString('ko-KR')}원</dd></div><div><dt>해지 비용</dt><dd>{option.exit_cost_total.toLocaleString('ko-KR')}원</dd></div></dl></section>)}</div><div className="comparison-difference"><span>두 날짜의 부담 차이</span><strong>{data.difference.toLocaleString('ko-KR')}원</strong></div><details className="answer-details"><summary>계산 범위·주의사항</summary><p>{data.limitations}</p></details></div>;
}
const renewalFieldLabels={maintenance_monthly_fee:'종료 후 관리·소모품 비용',installation_fee:'기본 설치비',registration_fee:'등록비',other_initial_fee:'기타 초기비',drilling_needed:'타공 필요 여부',surface_material:'상판 재질',pump_needed:'펌프 필요 여부',breaker_needed:'차단기 필요 여부',outlet_needed:'콘센트 신설',external_outlet_drilling:'외부 콘센트 타공',external_water_drilling:'외부 원수 타공',thick_sink:'싱크볼 두께',drilling_target:'타공 대상',new_subscription_terms:'신규 의무기간·가입·요금 조건',future_price:'전환 시점 실제 적용 요금',additional_installation_fee:'추가 설치 작업 견적'};
function RenewalFeatures({product}){
 if(!product)return <p className="product-price-note">모델별 검수 기능을 확인하지 못했어요.</p>;
 return <div className="renewal-feature-tags">{Object.entries(product.features||{}).map(([key,value])=><span className={value===false?'not-supported':''} key={key}>{key} · {value==null?'미확인':value===true?'지원':value===false?'미지원':value}</span>)}</div>;
}
function ProductChoice({card,...props}){
 const variants=card.data.variants?.length?card.data.variants:[card.data];
 const[index,setIndex]=useState(()=>Math.max(0,variants.findIndex(v=>v.model_id===card.data.model_id)));const selected=variants[Math.min(index,variants.length-1)];
 return <ResponseCard {...props} colorChoices={<ColorChoices variants={variants} selected={index} onSelect={setIndex} disabled={props.disabled}/>} card={{...card,data:selected}}/>;
}
function RenewalOfferChoice({offers,onSelect,disabled}){
 const [index,setIndex]=useState(()=>Math.max(0,offers.findIndex(v=>v.model_id.endsWith('RH'))));
 const o=offers[Math.min(index,offers.length-1)];
 return <section className="renewal-product-row" key={o.offer_id}>{o.product?.image_url&&<img src={o.product.image_url} alt={o.model_id} referrerPolicy="no-referrer"/>}<div className="renewal-product-description"><h4>{o.product?.display_name||o.model_id}</h4><small>{o.model_id} · <DisplayLabel text={o.care_details}/></small><ColorChoices variants={offers.map(v=>({...v.product,model_id:v.model_id}))} selected={index} onSelect={setIndex} disabled={disabled}/><RenewalFeatures product={o.product}/><p className="renewal-rate"><strong>{o.monthly_fee==null?'구독 요금 확인 필요':`월 ${o.monthly_fee.toLocaleString()}원부터`}</strong><span>{o.rate_note}</span></p>{o.product?.card_benefits?.length>0&&o.monthly_fee!=null&&<ProductCardBenefits data={{card_benefits:o.product.card_benefits,subscription_monthly_from:o.monthly_fee}}/>}<p className="product-price-note">{o.selection_reason}</p>{o.product?.card_benefits?.length>0&&o.monthly_fee!=null&&<p className="product-price-note">카드 최고 실적 충족 시 월 부담 최저 {Math.max(0,o.monthly_fee-Math.max(...o.product.card_benefits.flatMap(c=>c.tiers.map(t=>t.base+t.promotion)))).toLocaleString()}원부터 · 조건부, 포인트/연회비 별도</p>}<p>계약 {o.contract_months==null?'확인 필요':`${o.contract_months}개월`} · 의무기간 {o.mandatory_months==null?'계약 조건 확인 필요':`${o.mandatory_months}개월`}</p><button className="ui-button primary" disabled={disabled} onClick={()=>onSelect?.(o)}>{o.source_kind==='official'?'이 제품으로 참고 요금 비교':'이 제품으로 유지·재구독 비교'}</button></div></section>;
}
function RenewalCatalog({data,onSelect,disabled}){
 const catalogRef=useRef(null);
 const [query,setQuery]=useState('');const [type,setType]=useState('any');const [water,setWater]=useState([]);const [page,setPage]=useState(1);
 const matches=data.offers.filter(o=>(!query||`${o.model_id} ${o.product?.display_name||''}`.toLowerCase().includes(query.toLowerCase()))&&(type==='any'||o.product?.features?.['설치 유형']===type)&&water.every(feature=>o.product?.features?.[feature]===true));
 const count=Math.max(1,Math.ceil(matches.length/6));const current=Math.min(page,count);const offers=matches.slice((current-1)*6,current*6);
 return <section className="renewal-catalog" ref={catalogRef}><div className="renewal-card-heading"><span>전환할 제품 선택</span><h3>{data.sort_by==='monthly_fee'?'시작 월요금이 낮은 후보부터 확인해 보세요':'기능과 관리 방식부터 비교해 보세요'}</h3><p>{data.sort_by==='monthly_fee'?'낮은 시작 월요금 순입니다. 할인 종료 후 요금과 기존 계약 정산을 포함한 최종 부담은 제품 선택 후 비교해요.':'모델별 기능과 구독 조건을 확인하고 선택하세요.'}</p></div><div className="renewal-catalog-filters"><label>모델 검색<input aria-label="재구독 모델 검색" value={query} onChange={e=>{setQuery(e.target.value);setPage(1);}} placeholder="모델명 또는 제품명"/></label><label>설치 유형<select aria-label="재구독 설치 유형" value={type} onChange={e=>{setType(e.target.value);setPage(1);}}>{['any','데스크형','언더싱크형','스탠드형'].map(v=><option key={v} value={v}>{v==='any'?'전체 설치 유형':v}</option>)}</select></label><fieldset className="renewal-water-filter"><legend>필요한 물 기능</legend>{["냉수","정수","온수","얼음"].map(feature=><label key={feature}><input type="checkbox" checked={water.includes(feature)} onChange={e=>{const checked=e.target.checked;setWater(previous=>checked?[...previous,feature]:previous.filter(value=>value!==feature));setPage(1);}}/>{feature}</label>)}</fieldset></div><p className="renewal-list-count">{groupColorOffers(matches).length}개 제품군 · 색상은 카드 안에서 선택</p><ProductCarousel label="비교할 제품">{groupColorOffers(matches).map(group=><RenewalOfferChoice key={group[0].offer_id} offers={group} onSelect={offer=>onSelect?.({...offer,selection_preferences:{required_features:water,installation_type:({'데스크형':'desk','언더싱크형':'built_in','스탠드형':'stand'})[type]||'any'}})} disabled={disabled}/>)}</ProductCarousel>{!offers.length&&<p>선택한 조건에 맞는 모델이 없어요. 검색 조건을 변경해 주세요.</p>}<details className="answer-details"><summary>자료 기준·요금 적용 조건</summary><p>{data.limitations}</p></details></section>;
}
function RenewalCard({data,onChange,onDownloadBrief,briefId,disabled,onOtherProducts,onPreferences,onPrepare}){
 const [cardSelection,setCardSelection]=useState({...defaultCardSelection(),...Object.fromEntries(Object.entries(data.request).filter(([k])=>k.startsWith("card_")))});
 const [missingBrief,setMissingBrief]=useState(null);
 async function includeMissing(){const result=await onPrepare?.();if(result?.brief_id)setMissingBrief(result.brief_id);}
 const [transition,setTransition]=useState(data.renewal_start);const [months,setMonths]=useState(String(data.request.comparison_months));
 const [conditions,setConditions]=useState(data.request.installation_conditions||{});
 const [maintenance,setMaintenance]=useState(data.request.maintenance_monthly_fee==null?'':String(data.request.maintenance_monthly_fee));
 const installKeys=[...new Set(data.options.flatMap(o=>o.missing_fields))].filter(k=>['surface_material','drilling_needed','pump_needed','breaker_needed','outlet_needed','external_outlet_drilling','external_water_drilling','thick_sink'].includes(k));
 const money=value=>value==null?'미확인':`${value.toLocaleString()}원`;
 const cardData=data.options.find(o=>o.choice==='renew')?.product?.card_benefits||[];
 return <div className="renewal-card"><div className="renewal-card-heading"><span>기존 계약 정산 비용까지 포함</span><h3>현재 제품 유지 vs 선택 제품으로 전환</h3><p>{data.comparison_start} — {data.comparison_end}</p><small>청구 자료 기준일 {data.request.comparison_date}</small></div><form className="renewal-date-controls" onSubmit={e=>{e.preventDefault();const values=new FormData(e.currentTarget);onChange?.({...data.request,planned_start_date:String(values.get('planned_start_date')||transition),comparison_months:Number(values.get('comparison_months')||months),installation_conditions:conditions,maintenance_monthly_fee:maintenance===''?null:Number(maintenance),...cardSelection});}}><label>제품 전환 예정일<input name="planned_start_date" aria-label="제품 전환 예정일" type="date" min={data.comparison_start} required value={transition} onInput={e=>setTransition(e.currentTarget.value)} onChange={e=>setTransition(e.target.value)} disabled={disabled}/></label><label>비교 기간<select name="comparison_months" aria-label="재구독 비교 기간" value={months} onChange={e=>setMonths(e.target.value)} disabled={disabled}>{[12,24,36,60].map(n=><option key={n} value={n}>{n}개월</option>)}</select></label><button className="ui-button secondary" disabled={disabled}>변경한 조건으로 비교</button></form><p className="product-price-note"><strong>{data.renewal_start===localToday()?`전환 검토일은 오늘(${data.renewal_start})로 계산했어요.`:`선택한 전환 검토일 ${data.renewal_start} 기준이에요.`}</strong> 비교 기간은 {data.comparison_start}부터 {data.request.comparison_months}개월이에요. 별도 선택이 없으면 기본 36개월로 비교하며, 날짜와 기간을 바꿔 다시 계산할 수 있어요.</p><div className="renewal-quick-summary" aria-label="비교 핵심 요약">{data.options.map(o=><div key={o.choice}><strong>{o.choice==='keep'?'현재 유지':'선택 제품 전환'} · {o.model_id}</strong><p>{monthlyComparison(o,data.request.comparison_months).amount?.toLocaleString()??'확인 필요'}원 / 월평균</p></div>)}<small>동일 기간의 확인된 비용 기준 · 상세 포함 범위는 아래에서 확인하세요.</small></div><div className="renewal-choice-grid">{data.options.map(o=><section key={o.choice}><span className="renewal-choice-label">{o.choice==='keep'?'현재 제품 유지':'선택 제품으로 재구독'}</span><div className="renewal-average-title">{monthlyComparison(o,data.request.comparison_months).label}</div><div className="renewal-price">{monthlyComparison(o,data.request.comparison_months).amount==null?'확인 필요':monthlyComparison(o,data.request.comparison_months).amount.toLocaleString()}<small>{monthlyComparison(o,data.request.comparison_months).amount!=null?'원 / 월':''}</small></div><span className="renewal-price-note">{o.estimated_total==null?'전체 견적이 아닌, 아래 포함 항목 기준의 월평균이에요.':'일회성 비용까지 비교 기간으로 나눈 월평균이에요.'}</span>{missingCostGroups(o.missing_fields).length>0&&<div className="renewal-cost-tags">{missingCostGroups(o.missing_fields).map(g=><span key={g.id}>{g.label}</span>)}</div>}{o.product?.image_url&&<img className="renewal-option-image" src={o.product.image_url} alt={o.model_id} referrerPolicy="no-referrer"/>}<h4>{o.product?.display_name||o.model_id||'제품 정보 확인 필요'}</h4><small>{o.model_id}{o.care_details&&<> · <DisplayLabel text={o.care_details}/></>}</small><RenewalFeatures product={o.product}/>{o.maximum_card_benefit?.best&&<details className="answer-details"><summary>최대 카드 할인 참고 가정 · 선택 조건과 별도</summary><p>비교기간 월평균 참고 부담 {Math.ceil(o.maximum_card_scenario_total/data.request.comparison_months).toLocaleString()}원</p><p>{o.maximum_card_benefit.best.card_name} · 인정 실적 월 {o.maximum_card_benefit.best.required_spend.toLocaleString()}원 이상 · 연회비 {o.maximum_card_benefit.best.annual_fee.toLocaleString()}원 별도</p><p>구독료 청구할인 합계 {o.maximum_card_benefit.best.card_saving.toLocaleString()}원. 기존 해지 정산/초기비는 포함, 미확인 비용은 제외.</p><details className="answer-details"><summary>10개 카드별 전체 비교</summary>{o.maximum_card_benefit.cards.map(c=><p key={c.card_id}>{c.card_name}: 구독료 합계 {c.subscription_after.toLocaleString()}원 / 실적 {c.required_spend.toLocaleString()}원 / 연회비 {c.annual_fee.toLocaleString()}원 / 최대 {c.benefit_months}개월</p>)}</details><small>{o.maximum_card_benefit.note}</small><details className="answer-details"><summary>재구독·선납·포인트 혜택 전체 확인</summary><p>재구독: 계약 만기 124일 전~만기 후 1년, 6년 상품 최대 5%. 아래 별도 시나리오를 확인하세요.</p><p>선납: 운영 모델의 총 구독료 30% 선납 시 최대 4%. 선납 현금 지출·상품별 중복 적용 기준 확인 후 반영해야 하므로 위 월요금에서 자동 차감하지 않습니다.</p><p>신규 결합 최대 5% / 기존 결합·가전 연계 최대 3%: 품목·계약기간·구매 이력 조건이 다르며 상호 중복 여부를 확인해야 합니다.</p><p>첫 구독·다품목 포인트는 기존 단일 계약 교체에 일괄 적용되지 않습니다. 최대 30만P는 신규/다품목 조건입니다.</p>{['WD723RH','WD721RH','WD721RK','WD721RE','WD523AWB','WD520AWB'].includes(o.model_id)&&<p>교체보상 10만P: 2026.10.1~10.31 대상 모델 청약·폐가전 수거 신청, 12월까지 설치 완료·선착순 1,000명 조건. 월 청구할인과 분리됩니다.</p>}<a href="https://www.lge.co.kr/benefits/exhibitions/detail-PE01006002" target="_blank" rel="noopener noreferrer">정수기 행사 조건 확인 ↗</a></details></details>}{o.renewal_benefit&&<div className="renewal-missing"><strong>재구독 할인 조건</strong><p>대상 기간: {o.renewal_benefit.window_start} ~ {o.renewal_benefit.window_end}</p><p>{o.renewal_benefit.status==='conditional'?'기간 조건 충족 · 상품별 적용 확인':'대상 기간 밖'}</p>{o.maximum_benefit_scenario_total!=null&&<><p>최대 5% 적용 가정: 비교 기간 구독료 약 {money(o.renewal_benefit.maximum_scenario_saving)} 절감</p><p>할인 가정 월평균 참고 부담 {Math.ceil(o.maximum_benefit_scenario_total/data.request.comparison_months).toLocaleString()}원</p></>}<small>{o.renewal_benefit.note}</small></div>}{o.price_note&&<p className="product-price-note">{o.price_note} 공식 자료에 명시된 할인 회차와 이후 기본 요금을 비교 가정에 반영해요.</p>}<p className="product-price-note">표시된 비용을 비교 기간 {data.request.comparison_months}개월로 나눈 월평균입니다. 실제 월 청구액과 다르며, 확인된 일회성 해지·초기비도 포함합니다.</p><details className="answer-details"><summary>비교 기간 총액과 비용 내역</summary><p>{(o.estimated_total??o.scenario_total??o.confirmed_subtotal).toLocaleString()}원 · {o.estimated_total!=null?'예상 총액':o.scenario_total!=null?'수집 조건 참고 총액 · 미확인 비용 제외':'확인된 항목 소계 · 총액 미확정'}</p></details><dl><div><dt>{o.choice==='keep'?'기존 계약 추가 요금':'전환일까지 기존 추가 요금'}</dt><dd>{money(o.existing_subscription_cost)}</dd></div>{o.choice==='keep'?<><div><dt>미납금</dt><dd>{money(o.arrears)}</dd></div><div><dt>계약 종료 후 예상 유지비</dt><dd>{money(o.maintenance_cost)}</dd></div></>:<><div><dt>기존 계약 해지 정산</dt><dd>{money(o.exit_cost_total)}</dd></div><div><dt>비교 기간에 포함된 신규 구독</dt><dd>{o.subscription_months!=null?`${o.subscription_months}개월`:o.charge_items?.length!=null?`${o.charge_items.length}개월`:'확인 필요'}</dd></div><div><dt>{o.subscription_scenario_cost!=null?"신규 구독료 합계 · 공식 수집 요금 기준":"신규 구독료 합계"}</dt><dd>{money(o.subscription_cost??o.subscription_scenario_cost)}</dd></div>{o.rate_segments?.length>0&&<div><dt>회차별 월 구독료</dt><dd>{o.rate_segments.map(rate=><p key={rate.start_month}>{rate.start_month}~{rate.end_month}회차: {money(rate.monthly_fee)} / 월</p>)}</dd></div>}<div><dt>전환 전 종료 후 관리비</dt><dd>{money(o.maintenance_cost)}</dd></div><div><dt>초기비 확인된 소계</dt><dd>{money(o.initial_cost)}</dd></div><div><dt>전환 예정일</dt><dd>{data.renewal_start}</dd></div><div><dt>비교 후 남은 계약 / 의무</dt><dd>{o.remaining_contract_months}개월 / {o.remaining_mandatory_months==null?'확인 필요':`${o.remaining_mandatory_months}개월`}</dd></div></>}</dl>{o.exit_cost_items?.length>0&&<details className="answer-details"><summary>기존 계약 해지 비용 내역</summary>{o.exit_cost_items.map(i=><p key={i.name}><DisplayLabel text={i.name}/>: {money(i.amount)}</p>)}</details>}{o.missing_fields.length>0&&<div className="renewal-missing"><strong>표시 금액 외에 확인할 항목</strong>{missingCostGroups(o.missing_fields).map(group=><details className="answer-details" key={group.id} open={group.id==='installation'}><summary>{group.label}</summary><p>{group.description}</p><ul>{group.fields.map(k=><li key={k}>{renewalFieldLabels[k]||k}</li>)}</ul></details>)}<p>확인된 비용은 위 금액에 반영했어요. 아직 확인되지 않은 항목은 0원으로 확정하지 않았으며, 최종 견적에 추가되거나 조건에 따라 달라질 수 있어요.</p></div>}</section>)}</div><div className="renewal-outcome">{['keep','renew'].includes(data.decision?.lower_cost_choice)?`${data.decision.lower_cost_choice==='keep'?'현재 제품 유지':'선택 제품으로 재구독'}가 포함된 비용 기준 월평균 약 ${Math.floor(data.decision.minimum_saving/data.request.comparison_months).toLocaleString()}원 낮아요. (비교 기간 합계 ${data.decision.minimum_saving.toLocaleString()}원 차이)`:data.decision?.lower_cost_choice==='equal'?'포함된 비용은 같아요. 기능과 관리 조건을 함께 비교하세요.':'표시한 금액은 확인된 항목 또는 수집 요금 기준 비교예요. 별도 비용이 있어 최종 총액의 우열은 아직 확정하지 않았어요.'}</div><p className="card-data-note">위 금액은 일회성 정산·초기비를 비교기간으로 나눈 월평균이에요. 실제 매월 청구되는 구독료는 회차별 요금에서 확인하세요.</p><details className="answer-details"><summary>내 카드·실적 조건 선택</summary><form onSubmit={e=>{e.preventDefault();onChange?.({...data.request,...submittedCardSelection(new FormData(e.currentTarget),cardSelection)});}}><CardSelection cards={cardData} value={cardSelection} onChange={setCardSelection} disabled={disabled}/><button className="ui-button primary" type="submit" disabled={disabled}>이 카드 조건으로 다시 비교</button></form><p className="product-price-note">선택 조건은 다시 비교한 뒤 준비서에 반영됩니다. 재구독 최대 할인 가정과 자동 합산하지 않아요.</p></details><div className="renewal-next-actions"><button className="ui-button secondary" disabled={disabled} onClick={()=>onOtherProducts?.(data.request)}>다른 제품 고르기</button><button className="ui-button secondary" disabled={disabled} onClick={()=>onPreferences?.(data.request)}>희망 조건 바꾸기</button></div>{data.assumptions?.length>0&&<details className="answer-details"><summary>관리·설치·요금 가정</summary>{data.assumptions.map((a,i)=><p key={i}><DisplayLabel text={a}/></p>)}</details>}{data.options.some(o=>o.missing_fields?.length>0)&&<section className="renewal-missing-actions"><h4>별도 비용과 적용 조건</h4>{missingCostGroups(data.options.flatMap(o=>o.missing_fields||[])).map(group=><details className="answer-details" key={group.id}><summary>{group.label}</summary><p>{group.description}</p>{group.fields.map(key=>{const [label,reason]=costGapExplanation(key);return <p key={key}><strong>{renewalFieldLabels[key]||label}</strong>: {reason}</p>;})}</details>)}<p>위에 표시한 별도 항목만 추가 확인이 필요해요. 확인된 요금·비용은 이미 반영했으며, 확인되지 않은 항목은 0원으로 가정하지 않았어요.</p><button className="ui-button secondary" disabled={disabled} onClick={includeMissing}>이 확인 질문을 상담 준비서에 포함하기</button>{missingBrief&&<button className="ui-button primary" disabled={disabled} onClick={()=>onDownloadBrief?.(missingBrief)}>상담 준비서 PDF 다운로드</button>}</section>}<details className="answer-details"><summary>자료 기준·계산 범위</summary><p>{data.limitations}</p></details></div>;
}
function RenewalTimingCard({data,onUseTiming,disabled}){
 return <section className="renewal-timing-card"><span className="picker-eyebrow">내 계약 기준 일정 제안</span><h3>계약 기준 검토 후보</h3><strong className="timing-date">{data.suggested_date}</strong><p>의무사용 종료일: {data.mandatory_end||'계약 확인 필요'}</p><p>전체 계약 종료일: {data.contract_end}</p><p>{data.reason}</p><button className="ui-button primary" disabled={disabled} onClick={()=>onUseTiming?.(data.suggested_date)}>이 날짜로 계속하기</button><small>제안 날짜는 일정 후보이며 설치 예약은 별도로 확인해야 합니다.</small><details className="answer-details"><summary>제안 근거·확인할 조건</summary><p>{data.limitations}</p></details></section>;
}
function PurchaseBenefits({benefits:b}){
 const [card,setCard]=useState('');
 const installment=b.installment_cards.find(c=>c.name===card);
 const payment=b.payment_cards.find(c=>c.name===card);
 return <section className="purchase-benefits"><div className="purchase-benefits-heading"><span>일시불 구매 혜택</span><strong>최대혜택가 {b.max_benefit_price.toLocaleString()}원</strong><small>조건 충족 시 체감가 · 실제 결제금액과 달라요</small></div>{b.coupon_name?<div className="purchase-coupon-highlight"><span className="coupon-channel">{b.coupon_name.includes("앱전용")?"앱전용 쿠폰":"구매 쿠폰"}</span><strong>{b.coupon_discount.toLocaleString()}원 할인</strong><p>{b.coupon_name}</p><small>쿠폰 다운로드·적용 자격 확인 후 결제금액 {b.coupon_price.toLocaleString()}원. 앱전용 쿠폰은 LGE.COM 앱 적용 조건을 확인하세요.</small></div>:<div className="purchase-coupon-unconfirmed"><p>현재 미로그인 공개 페이지에는 쿠폰 적용 금액이 노출되지 않았어요. 로그인·앱 적용 조건은 공식 주문서에서 확인하세요.</p>{b.historical_coupon&&<p><strong>이전 확인 기록 ({b.historical_coupon.checked_at})</strong><br/>{b.historical_coupon.coupon_name} · {b.historical_coupon.coupon_discount.toLocaleString()}원 할인<br/><small>현재 적용 여부 미확인 · 위 가격에 자동 반영하지 않습니다.</small></p>}</div>}<dl className="purchase-price-steps"><div><dt>회원할인가</dt><dd>{b.member_price.toLocaleString()}원</dd></div>{b.coupon_price!=null&&<><div><dt>{b.coupon_name?.includes("앱전용")?"앱전용 쿠폰 할인":"쿠폰 할인"}</dt><dd>−{b.coupon_discount.toLocaleString()}원</dd></div><div><dt>쿠폰 적용 후 결제금액</dt><dd>{b.coupon_price.toLocaleString()}원</dd></div></>}<div><dt>{b.payment_cards.length?'조건 충족 시 결제일 할인':'추가 혜택 차이(조건 확인 필요)'}</dt><dd>−{b.settlement_discount.toLocaleString()}원</dd></div></dl><p className="product-price-note">{b.notice} 확인일 {b.checked_at}</p><details className="answer-details"><summary>카드사별 결제일 할인·무이자 할부</summary><label>결제 카드사<select disabled={!b.installment_cards.length} value={card} onChange={e=>setCard(e.target.value)}><option value="">{b.installment_cards.length?'카드사를 선택하세요':'카드별 상세조건은 공식 구매 혜택에서 확인'}</option>{b.installment_cards.map(c=><option key={c.name} value={c.name}>{c.name}</option>)}</select></label>{card&&<><p><strong>결제일 할인</strong><br/>{payment?`${payment.benefit} · ${payment.condition}`:'이 카드의 결제일 할인은 해당 상세 목록에서 확인되지 않았어요.'}</p>{payment&&<p>상품에 표시된 쿠폰·카드 조건을 모두 충족할 경우 체감가: <strong>{b.max_benefit_price.toLocaleString()}원</strong><br/>쿠폰 적용·월 누적 할인 한도 등을 실제 주문서에서 확인하세요.</p>}<strong>무이자 할부 조건</strong>{installment?.periods.map((p,i)=><p key={i}>{p.period} · {p.condition}</p>)}</>}<small>{b.installment_notice}</small></details><details className="answer-details"><summary>간편결제 적립·추가 혜택</summary>{b.simple_payment.map(p=><div key={p.name}><h4>{p.name} · {p.benefit}</h4><p className="product-price-note">{p.conditions}</p></div>)}{b.additional.map((p,i)=><p key={i}><a href={p.url} target="_blank" rel="noopener noreferrer">{p.title} · {p.description} ↗</a></p>)}<small>포인트·캐시백·결합 혜택은 조건 확인 전 최대혜택가에서 추가 차감하지 않아요.</small></details><a href={b.source_url} target="_blank" rel="noopener noreferrer">공식 구매 혜택 전체 확인 ↗</a></section>;
}
function FeatureComparison({cards}){
 const products=cards.filter(c=>c.type==='product').map(c=>c.data);
 const fields=[...new Set(products.flatMap(p=>Object.keys(p.features||{})))];
 const display=v=>v==null?'미확인':v===true?'지원':v===false?'미지원':String(v);
 return <section className="feature-comparison"><h3>제품 기능 한눈에 비교</h3><p>추천 순위가 아니라 모델별 기능 차이를 비교해요.</p><div className="feature-table-scroll"><table><thead><tr><th>비교 항목</th>{products.map(p=><th key={p.model_id}>{p.image_url&&<img src={p.image_url} alt={p.model_id} referrerPolicy="no-referrer"/>}{p.model_id}</th>)}</tr></thead><tbody>{fields.map(f=>{const different=new Set(products.map(p=>display(p.features[f]))).size>1;return <tr key={f} className={different?'feature-difference':''}><th>{f}{different&&<small>차이</small>}</th>{products.map(p=><td key={p.model_id}>{display(p.features[f])}</td>)}</tr>;})}</tbody></table></div><small>모델별 관리 조건과 가격 혜택은 제품 추천 카드 또는 공식 안내에서 별도로 확인하세요.</small></section>;
}
function ProductCardBenefits({data}){
 const[selection,setSelection]=useState(defaultCardSelection);const card=data.card_benefits?.find(c=>c.id===selection.card_id);const today=localToday();
 const discount=cardDiscount({card,monthlyFee:data.subscription_monthly_from,spend:selection.card_spend,eligibility:selection.card_eligibility,applicationDate:selection.card_application_date,today});
 return <details className="subscription-card-panel"><summary><span><small>SUBSCRIPTION</small><strong>구독 카드 할인</strong></span><span className="subscription-summary-tag">내 카드·실적 조건으로 확인</span></summary><div className="subscription-card-body"><p className="subscription-description">기본값은 할인 전 금액이에요. 카드와 인정실적·적용 자격을 선택하면 해당 조건의 월 부담을 확인해요.</p><CardSelection cards={data.card_benefits} value={selection} onChange={setSelection}/><div className="subscription-estimate"><span>선택 조건의 시작 월요금 예시</span><strong>{(data.subscription_monthly_from-discount).toLocaleString()}<small>원 / 월</small></strong><p>할인 전 {data.subscription_monthly_from.toLocaleString()}원 · 청구할인 {discount.toLocaleString()}원. 오늘 청구한다고 가정한 금액이며 추가 할인 시작일 이전에는 기본 할인만 반영해요.</p></div><p className="subscription-disclaimer">조건을 충족하는 참고 가정입니다. 할인 회차 이후 요금·연회비·포인트는 별도로 확인하세요.</p>{card&&<a className="ui-button secondary" href={card.source_url} target="_blank" rel="noopener noreferrer">공식 카드 조건 확인 ↗</a>}</div></details>;
}

function ResponseCard({ card,colorChoices,supportMode=false,onSelectRenewalOffer,onChangeRenewal,onUseTiming,onRequestBrief,onDownloadBrief,briefId,disabled,onOtherProducts,onPreferences,onPrepare }) {
  const { data } = card;

  if(card.type==='usage_manual')return <section className="usage-manual-card"><span>내 정수기 사용설명서</span><h3>{data.model_id}</h3><p>{data.title}</p>{data.version&&<small>문서 판본 {data.version}</small>}<a className="ui-button primary" href={data.url} target="_blank" rel="noopener noreferrer">공식 사용설명서 열기 ↗</a><p className="product-price-note">출수·온도 선택·버튼 사용은 설명서의 ‘사용하기’ 항목을 확인하세요. 궁금한 부분을 이어서 질문할 수 있어요.</p><details className="answer-details"><summary>문서 확인 범위</summary><p>{data.limitations}</p></details></section>;
  if(card.type==='renewal_catalog')return <RenewalCatalog data={data} onSelect={onSelectRenewalOffer} disabled={disabled}/>;
  if(card.type==='renewal_timing')return <RenewalTimingCard data={data} onUseTiming={onUseTiming} disabled={disabled}/>;
  if(card.type==='renewal_comparison')return <RenewalCard onChange={onChangeRenewal} data={data} onOtherProducts={onOtherProducts} onPreferences={onPreferences} onPrepare={onPrepare} onRequestBrief={onRequestBrief} onDownloadBrief={onDownloadBrief} briefId={briefId} disabled={disabled}/>;
  if (card.type === 'comparison') return <ComparisonCard data={data} />;
  if (card.type === 'contract') return <ContractCard data={data} onUseTiming={onUseTiming} disabled={disabled}/>;
  if(card.type==='purchase_method')return <section className="purchase-method-card"><h3>구매와 구독, 무엇을 확인할까요?</h3><div className="purchase-method-options">{data.options.map(o=><section key={o.name}><h4>{o.name}</h4>{[['payment','비용'],['care','관리'],['period','기간·약정']].map(([key,label])=><div key={key}><strong>{label}</strong><p>{o[key]}</p></div>)}<p className="purchase-method-fit">{o.suitable}</p></section>)}</div><p className="product-price-note">{data.limitations}</p></section>;
  if (card.type === 'product') {
    return (
      <div className="contract-card product-result-card">
        {data.image_url&&<img className="product-result-image" src={data.image_url} alt={data.display_name||data.model_id} loading="lazy" referrerPolicy="no-referrer" onError={e=>{e.currentTarget.hidden=true;}}/>}
        <small>{data.model_id}</small><strong>{data.display_name||data.model_id}</strong>{colorChoices}
        {!supportMode&&<><div className="product-price-grid"><div><span>{data.purchase_benefits?.coupon_price!=null?(data.purchase_benefits.coupon_name?.includes('앱전용')?'구매 · 앱쿠폰 적용가(조건부)':'구매 · 쿠폰 적용가(조건부)'):'구매 · 회원할인가'}</span><b>{data.purchase_benefits?.coupon_price!=null?data.purchase_benefits.coupon_price.toLocaleString()+'원':data.purchase_price!=null?`${data.purchase_price.toLocaleString()}원`:data.purchase_price_status==='unavailable'?"현재 구매 불가":"가격 확인 필요"}</b>{data.purchase_benefits?.coupon_price!=null&&<small className="coupon-base-price">회원가 {data.purchase_price?.toLocaleString()}원 · 쿠폰 자격 확인 필요</small>}</div><div><span>구독 시작 월요금</span><b>{data.subscription_monthly_from!=null?`월 ${data.subscription_monthly_from.toLocaleString()}원~`:"조건 확인 필요"}</b></div></div>
        {data.price_note&&<details className="product-card-details"><summary>가격·요금 적용 조건</summary><p className="product-price-note">{data.price_note}</p></details>}
        {data.purchase_benefits&&<details className="product-card-details"><summary>구매 혜택 · 조건부 최대혜택가 {data.purchase_benefits.max_benefit_price.toLocaleString()}원</summary><PurchaseBenefits benefits={data.purchase_benefits}/></details>}
        {data.card_benefits?.length>0&&data.subscription_monthly_from!=null&&<details className="product-card-details"><summary>제휴카드 조건 확인</summary><ProductCardBenefits data={data}/></details>}
        </>}<div className="product-water-features">{['냉수','정수','온수','얼음'].filter(k=>data.features?.[k]===true).map(k=><span key={k}>{k}</span>)}</div>{data.product_url&&<a className="ui-button secondary" href={data.product_url} target="_blank" rel="noopener noreferrer">{supportMode?'공식 제품 정보 확인 ↗':'공식 제품·가격 확인 ↗'}</a>}
        {!supportMode&&onSelectRenewalOffer&&data.comparison_supported&&<button className="ui-button primary" disabled={disabled} onClick={()=>onSelectRenewalOffer(data)}>이 제품으로 유지·전환 비교</button>}
        {!supportMode&&onSelectRenewalOffer&&!data.comparison_supported&&<p className="product-price-note">이 모델은 비교에 필요한 신규 계약 조건이 아직 준비되지 않았어요.</p>}
        <details className="product-card-details" open={supportMode}><summary>전체 기능·제품 사양</summary>        <dl>
          {Object.entries(data.features || {}).map(([name, value]) => (
            <div key={name}>
              <dt>{name}</dt>
              <dd>{value==null?'정보 없음':value===true?'지원':value===false?'미지원':String(value)}</dd>
            </div>
          ))}
        </dl></details>

        {data.limitations && <details className="answer-details"><summary>자료 기준·계산 범위</summary><p>{data.limitations}</p></details>}
      </div>
    );
  }
  if (card.type === 'troubleshoot') {
    return (
      <div className="contract-card">
        <strong>{data.model_id} · 증상 확인</strong>
        <p>{data.symptom}</p>
        <ol>
          {(data.next_steps || []).map((step, index) => (
            <li key={`${index}-${step}`}>{step}</li>
          ))}
        </ol>
        {data.safety_notice && <p>{data.safety_notice}</p>}
        {data.limitations && <details className="answer-details"><summary>자료 기준·계산 범위</summary><p>{data.limitations}</p></details>}
      </div>
    );
  }
  if (card.type === 'care_subscription') {
    return (
      <div className="contract-card">
        <strong>{data.model_id||'정수기'} · 관리 안내</strong>
        <p>{data.guidance}</p>
        {data.limitations && <details className="answer-details"><summary>자료 기준·계산 범위</summary><p>{data.limitations}</p></details>}
      </div>
    );
  }
  return null;
}

function InlineText({text}){
 return text.split(/(\*\*[^*]+\*\*|\d[\d,]*원)/g).map((part,i)=>part.startsWith('**')?<strong key={i}>{part.slice(2,-2)}</strong>:/^\d[\d,]*원$/.test(part)?<strong key={i} className="inline-amount">{part}</strong>:<React.Fragment key={i}>{part}</React.Fragment>);
}
function AnswerContent({answer}){
 const all=[...new Set((answer||'').split(/\n+/).map(s=>s.trim()).filter(Boolean))].filter(line=>!/^\(?출처\s*[:：]/.test(line));
 const provenance=all.filter(s=>/시연용|합성|가상 데이터/.test(s)&&/^(※|주의|이 계산|이 결과|이는|이 정보|본 결과)/.test(s));
 const raw=all.filter(s=>!provenance.includes(s));
 const lines=raw.length===1&&answer.length>650?raw[0].split(/(?<=[.!?])\s+(?=[가-힣A-Za-z])/u):raw;
 const feeSchedule=lines.some(line=>/\d+년차: 월/.test(line));
 const periodExplanation=lines.some(line=>/^\*\*.*의무사용/.test(line))&&lines.some(line=>/^\*\*.*전체 계약/.test(line));
 const long=!feeSchedule&&!periodExplanation&&(lines.length>3||answer?.length>450);
 const lead=long?lines.slice(0,2):lines;
 const notices=long?lines.slice(2).filter(s=>/미확인|미확정|확정할 수|확정하지|미납/.test(s)):[];
 const render=(rows)=>rows.map((line,i)=>/^[-•]/.test(line)?<div className="answer-list-line" key={i}><span aria-hidden="true">•</span><div><InlineText text={line.replace(/^[-•]\s*/,'')}/></div></div>:/^#{1,4}\s/.test(line)?<h4 key={i}><InlineText text={line.replace(/^#{1,4}\s*/,'')}/></h4>:<p key={i}><InlineText text={line}/></p>);
 return <div className="answer-content"><span className="answer-key-label">핵심 안내</span><div className="answer-lead">{render(lead)}</div>{provenance.length>0&&<details className="answer-details"><summary>자료 기준</summary>{render(provenance)}</details>}{notices.length>0&&<div className="answer-notice">{render(notices)}</div>}{long&&<details className="answer-details"><summary>설명 전체 보기</summary>{render(lines.slice(2).filter(line=>!notices.includes(line)))}</details>}</div>;
}
function ConsultationOffer({message,onPrepare,onDownload,disabled}){
 const[state,setState]=useState('closed');const[error,setError]=useState('');const[createdId,setCreatedId]=useState(null);
 async function prepare(){setState('busy');setError('');try{const result=await onPrepare?.(message);if(!result)throw new Error('준비서 요청을 확인하지 못했어요. 다시 시도해 주세요.');if(result.status==='brief_created'&&result.brief_id){setCreatedId(result.brief_id);setState('done');}else{setState('needs_info');}}catch(e){setState('choice');setError(e.message);}}
 if(state==='dismissed')return null;
 if(state==='closed')return <button className="ui-button secondary advisor-button" disabled={disabled} onClick={()=>setState('choice')}>상담사 연결 안내</button>;
 return <section className="consultation-offer"><span>상담 준비</span><h4>상담할 내용을 준비서로 정리할까요?</h4><p>{message.consultation_reason||'확인한 계약 조건과 비교 결과를 정리해 공식 상담에서 활용할 수 있어요. 실제 상담 접수는 진행되지 않습니다.'}</p>{state==='choice'?<div className="consultation-choice"><button className="ui-button primary" disabled={disabled} onClick={prepare}>네, 준비해 주세요</button><button className="ui-button secondary" disabled={disabled} onClick={()=>setState('dismissed')}>괜찮아요</button></div>:<p role="status">{state==='busy'?'확인한 내용을 정리하고 있어요…':state==='done'?'준비서가 완성됐어요. 바로 다운로드하세요.':'먼저 추가 확인이 필요해요. 이어지는 안내를 확인해 주세요.'}</p>}{state==='done'&&createdId&&<button className="ui-button primary" disabled={disabled} onClick={()=>onDownload?.(createdId)}>상담 준비서 PDF 다운로드</button>}{error&&<p role="alert">{error}</p>}</section>;
}
export default function ChatMessage({ message,onConsentResume,onConsentLogin,onSelectRenewalOffer,onChangeRenewal,onRestartRecommendation,onPrepareConsultation,onUseTiming,onRequestBrief,onDownloadBrief,disabled,onOtherProducts,onPreferences,onNextAction,consentResolved=false }) {
 const[consentRegistered,setConsentCompleted]=useState(false);
 const consentCompleted=consentRegistered||consentResolved;
  if (message.role === 'user') {
    return <div className="user-bubble">{message.text}</div>;
  }

  if (message.role === 'error') {
    return (
      <div className="error-message" role="alert">
        <strong>{message.code==='MODEL_CREDIT_EXHAUSTED'?'AI 사용 잔액 확인이 필요해요':message.code==='MODEL_AUTH_FAILED'?'AI 연결 설정을 확인해 주세요':'답변을 가져오지 못했어요.'}</strong>
        <p>{message.text}</p>
      </div>
    );
  }

  if(message.status==='brief_created'&&message.brief_id){
    return <article className="agent-message"><div className="agent-avatar" aria-hidden="true">✦</div><div className="agent-content">{message.requestLabel&&<div className="request-topic-label">{message.requestLabel}</div>}<div className="agent-name">정수기 상담 가이드<span>준비서 생성</span></div><div className="brief-download-ready" role="status"><strong>상담 준비서가 준비됐어요</strong><button type="button" className="ui-button primary" disabled={disabled} onClick={()=>onDownloadBrief?.(message.brief_id)}>상담 준비서 PDF 다운로드</button></div></div></article>;
  }

  return (
    <article className={`agent-message${message.cards?.some(c=>['renewal_catalog','renewal_comparison','renewal_timing'].includes(c.type))?' agent-message--wide':''}`}>
      <div className="agent-avatar" aria-hidden="true">
        ✦
      </div>
      <div className="agent-content">
        {message.requestLabel&&<div className="request-topic-label">{message.requestLabel}</div>}
        {message.requestSummary&&<p className="request-topic-summary">{message.requestSummary}</p>}
        <div className="agent-name">
          정수기 상담 가이드
          <span>{{answered:'안내 완료',needs_info:'추가 확인',brief_created:'준비서 생성'}[message.status]||'상담 안내'}</span>
        </div>
        {!consentCompleted&&(message.cards?.length?<p className="card-intro">{message.status==='brief_created'?'상담 준비서가 준비됐어요. 바로 다운로드할 수 있어요.':message.cards.some(c=>c.type==='renewal_catalog')?'원하는 기능과 관리 방식을 보고 비교할 구독 조건을 선택하세요.':message.cards.some(c=>c.type==='renewal_timing')?'전체 계약 종료일을 기준으로 계약 기준 검토 후보를 확인했어요.':message.cards.some(c=>c.type==='renewal_comparison')?'같은 기간으로 두 선택을 비교했어요. 미확인 항목도 함께 확인해 주세요.':message.cards.some(c=>c.type==='comparison')?'두 날짜의 추가 부담을 비교했어요.':message.cards.some(c=>c.type==='product')?(message.requestTopic==='usage'?'사용 중인 모델의 확인된 기능입니다. 궁금한 조작 방법을 질문해 주세요.':message.requestTopic==='troubleshoot'?'사용 중인 모델 정보를 확인했어요. 현재 증상에 맞는 조치를 확인할게요.':message.requestTopic==='features'?'모델별 기능 차이를 비교했어요. 서로 다른 항목을 강조했어요.':'선택한 조건에 맞는 후보를 확인했어요. 가격은 확인일 기준이며 관리 조건은 별도 확인하세요.'):message.cards.some(c=>c.type==='purchase_method')?'비용·관리·기간 조건을 나누어 확인하세요.':'확인한 내용을 아래에 정리했어요.'}</p>:<AnswerContent answer={message.answer}/>)}

        {message.brief_id&&<div className="brief-download-ready" role="status"><strong>상담 준비서가 준비됐어요</strong><button className="ui-button primary" disabled={disabled} onClick={()=>onDownloadBrief?.(message.brief_id)}>상담 준비서 PDF 다운로드</button></div>}
        {message.requestTopic==='features'&&message.cards?.some(c=>c.type==='product')?<FeatureComparison cards={message.cards}/>:message.cards?.length&&message.cards.every(c=>c.type==='product')?<ProductCarousel>{message.cards.map((card,index)=><ProductChoice key={card.data.family_id||card.data.model_id||index} card={card} supportMode={['usage','troubleshoot','features'].includes(message.requestTopic)} onSelectRenewalOffer={message.allowRenewalSelection?onSelectRenewalOffer:null} onChangeRenewal={onChangeRenewal} onOtherProducts={onOtherProducts} onPreferences={onPreferences} onPrepare={()=>onPrepareConsultation?.(message)} onUseTiming={(date,context)=>onUseTiming?.(date,context||message)} onRequestBrief={onRequestBrief} onDownloadBrief={onDownloadBrief} briefId={message.brief_id} disabled={disabled}/>)}</ProductCarousel>:(message.cards||[]).map((card,index)=><ResponseCard key={card.type+'-'+index} card={card} supportMode={['usage','troubleshoot','features'].includes(message.requestTopic)} onSelectRenewalOffer={message.allowRenewalSelection?onSelectRenewalOffer:null} onChangeRenewal={onChangeRenewal} onOtherProducts={onOtherProducts} onPreferences={onPreferences} onPrepare={()=>onPrepareConsultation?.(message)} onUseTiming={(date,context)=>onUseTiming?.(date,context||message)} onRequestBrief={onRequestBrief} onDownloadBrief={onDownloadBrief} briefId={message.brief_id} disabled={disabled}/>)}
        {message.missing_fields?.includes('consent')&&!consentResolved&&<InlineConsent message={message} onResume={onConsentResume} onLogin={onConsentLogin} onComplete={()=>setConsentCompleted(true)} disabled={disabled}/>}
        {message.benefit_guidance&&<details className="answer-details"><summary>교체 혜택 적용 조건</summary><AnswerContent answer={message.benefit_guidance}/></details>}
        {message.follow_up && (
          <div className="next-question">
            <span>다음 확인 질문</span>
            {message.follow_up}
          </div>
        )}
        {message.requestTopic==='recommend'&&<button className="ui-button secondary" disabled={disabled} onClick={onRestartRecommendation}>추천 조건 다시 선택</button>}
        {message.sources?.filter(source=>source.document_id?.startsWith('LG-OFFICIAL-')&&['https://www.lge.co.kr/ai-commerce/aiAssistant','https://www.lge.co.kr/category/water-purifiers','https://www.lge.co.kr/support'].includes(source.url)).map(source=><a key={source.document_id} className="ui-button secondary official-channel-button" href={source.url} target="_blank" rel="noopener noreferrer">{source.document_id==='LG-OFFICIAL-SUPPORT'?'LG AI Chat에서 상담하기':source.document_id==='LG-OFFICIAL-PRODUCT'?'LG 정수기 제품 알아보기':'LG 공식 상담 안내'} ↗</a>)}
        {availableAnswerActions(message).length>0&&<nav className="answer-next-actions" aria-label="이어서 확인하기"><span>이어서 확인해 보세요</span><div>{availableAnswerActions(message).map(action=><button key={action.id} type="button" className="ui-button secondary" disabled={disabled} onClick={()=>onNextAction?.(action,message)}>{action.label}<span aria-hidden="true"> →</span></button>)}</div></nav>}
        <details className="answer-details"><summary>참고 자료</summary><SourceBox sources={message.sources} /></details>
        {message.topic==='contract'&&message.status==='answered'&&<ConsultationOffer message={message} onPrepare={onPrepareConsultation} onDownload={onDownloadBrief} disabled={disabled}/>}
        
      </div>
    </article>
  );
}