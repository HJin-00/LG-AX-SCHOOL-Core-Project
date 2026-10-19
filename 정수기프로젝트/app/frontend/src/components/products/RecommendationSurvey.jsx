import React,{useState}from 'react';
export default function RecommendationSurvey({onSubmit,completed}){
 const[features,setFeatures]=useState([]);const[installation,setInstallation]=useState('any');
 const choices=['냉수','정수','온수','얼음'];
 const types=[['desk','데스크형','상판 위에 놓는 형태'],['built_in','빌트인형','싱크대 아래 설치'],['stand','스탠드형','바닥에 세우는 형태']];
 function submit(e){e.preventDefault();if(completed)return;const values=[{value:'필요 기능: '+(features.length?features.join(', '):'아직 정하지 않음')},{value:'설치 유형: '+installation}];onSubmit?.({required_features:features,installation_type:installation,care_mode:'any'},values);}
 return <form className="recommendation-survey" onSubmit={submit}>
  <div className="form-heading"><span>제품 선택</span><h3>{completed?'선택한 조건으로 후보를 확인했어요':'어떤 정수기가 필요하세요?'}</h3></div>
  <fieldset className="recommendation-choice-group"><legend>물 기능</legend><p>필요한 기능을 모두 선택하세요.</p><div className="recommendation-water-choices">{choices.map(f=><label className={features.includes(f)?'is-selected':''} key={f}><input type="checkbox" disabled={completed} checked={features.includes(f)} onChange={e=>setFeatures(v=>e.target.checked?[...v,f]:v.filter(x=>x!==f))}/><span>{f}</span></label>)}</div></fieldset>
  <fieldset className="recommendation-choice-group"><legend>설치 형태</legend><p>원하는 형태 한 가지를 선택하세요. 아직 모르시면 선택하지 않아도 돼요.</p><div className="recommendation-installation-choices">{types.map(([value,label,detail])=><label className={installation===value?'is-selected':''} key={value}><input type="radio" name="installation-type" value={value} disabled={completed} checked={installation===value} onChange={()=>setInstallation(value)}/><span><strong>{label}</strong><small>{detail}</small></span></label>)}</div>{installation!=='any'&&<button type="button" className="recommendation-clear" disabled={completed} onClick={()=>setInstallation('any')}>설치 형태 아직 미정</button>}</fieldset>
  <button className="ui-button primary" disabled={completed} type="submit">{completed?'후보 확인 요청 완료':'이 조건으로 후보 확인'}</button>
 </form>;
}
