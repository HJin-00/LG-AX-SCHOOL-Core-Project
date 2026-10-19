import React from 'react';
export default function ColorChoices({variants,selected,onSelect,disabled}){
 if(variants.length<2)return null;
 return <div className="product-color-options" role="group" aria-label="제품 색상 선택">{variants.map((p,i)=><button type="button" key={p.model_id} disabled={disabled} aria-pressed={i===selected} aria-label={p.color_name+' '+p.model_id} title={p.color_name} onClick={()=>onSelect(i)}><span style={{backgroundColor:p.color_hex}}/>{p.color_name}</button>)}</div>;
}
