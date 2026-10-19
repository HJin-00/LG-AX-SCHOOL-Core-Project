import React,{useState}from'react';
import{comparisonModelChoices}from'./modelChoices.js';
export default function FeatureModelPicker({onSubmit,disabled}){
 const[a,setA]=useState('WD520VCT');const[b,setB]=useState('WU923AWB');
 return <form className="required-info-panel" onSubmit={e=>{e.preventDefault();if(a!==b)onSubmit?.([a,b]);}}><div className="form-heading"><span>제품 기능 비교</span><h3>비교할 두 모델을 선택하세요</h3></div><div className="required-fields">{[['첫 번째 모델',a,setA],['두 번째 모델',b,setB]].map(([label,value,set])=><label key={label}>{label}<select value={value} disabled={disabled} onChange={e=>set(e.target.value)}>{comparisonModelChoices.map(id=><option key={id} value={id}>{id}</option>)}</select></label>)}</div>{a===b&&<p>서로 다른 모델을 선택해 주세요.</p>}<button className="ui-button primary" disabled={disabled||a===b}>선택한 모델 비교</button></form>;
}
