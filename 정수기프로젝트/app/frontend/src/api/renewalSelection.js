export function renewalPreferencesFromMessages(messages){
 const result={required_features:[],installation_type:'any',care_mode:'any',exclude_owned_model:true};
 for(const message of messages){const text=message.requestQuestion||message.text||'';const start=text.indexOf('{');if(start<0)continue;try{const obj=JSON.parse(text.slice(start));for(const key of Object.keys(result))if(key in obj)result[key]=obj[key];}catch{}}
 return result;
}
export function candidateRequest(messages,request){
 return {...renewalPreferencesFromMessages(messages),planned_start_date:request.planned_start_date,comparison_months:request.comparison_months,card_id:request.card_id||'none',card_spend:request.card_spend??null,card_eligibility:request.card_eligibility||'unconfirmed',card_application_date:request.card_application_date};
}

export function submittedCardSelection(form,fallback){
 const value=key=>form.get(key);
 return {...fallback,card_id:String(value('card_id')||fallback.card_id||'none'),card_spend:value('card_spend')==null?fallback.card_spend:value('card_spend')===''?null:Number(value('card_spend')),card_eligibility:String(value('card_eligibility')||fallback.card_eligibility||'unconfirmed'),card_application_date:String(value('card_application_date')||fallback.card_application_date||'')};
}
