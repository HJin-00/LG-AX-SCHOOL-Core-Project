import React,{useState}from 'react';
import{useCustomerProduct}from '../../context/CustomerProductContext.jsx';
import{consentPurpose,consentFields,hasConsent}from '../../api/consentPurpose.js';
export default function InlineConsent({message,onResume,onLogin,onComplete,disabled}){
 const{account,session,isChanging,verifyIdentity,selectProduct}=useCustomerProduct();
 const[checked,setChecked]=useState([]);const[error,setError]=useState('');const[done,setDone]=useState(false);const[busy,setBusy]=useState(false);
 const purpose=consentPurpose(message.requestTopic||message.topic,message.requestQuestion||'');
 const identityValid=session?.demo_customer_id===account?.demo_customer_id&&session?.identity_state==='demo_verified'&&Date.now()<session.identity_expires_at;
 const requiredScopes=identityValid?purpose.scopes.filter(scope=>!hasConsent(session,{scopes:[scope]})):purpose.scopes;
 async function approve(){
  if(disabled||busy||done)return;setBusy(true);setError('');
  try{
   if(!account)throw new Error('내 계약 조회는 로그인 후 진행할 수 있어요.');
   const valid=session?.demo_customer_id===account.demo_customer_id&&session?.identity_state==='demo_verified'&&Date.now()<session.identity_expires_at;
   if(!valid)await verifyIdentity(account,account.demo_customer_id);
   await selectProduct(account,[...new Set([...(valid?session.scopes||[]:[]),...purpose.scopes])]);
   setDone(true);onComplete?.();onResume?.(message);
  }catch(e){setError(e.message);}finally{setBusy(false);}
 }
 if(done)return <p className="inline-consent-complete" role="status">조회 동의를 등록했어요. 이어서 질문을 확인할게요.</p>;
 return <section className="inline-consent"><h4>이 질문에 필요한 정보 조회</h4><p>{purpose.title}에 필요한 아래 범위만 확인합니다.</p>{!account?<button className="ui-button primary" type="button" disabled={disabled} onClick={onLogin}>로그인하고 이 대화에서 동의하기</button>:<>
 {requiredScopes.length<purpose.scopes.length&&<p>이미 동의한 범위는 유지하고, 추가로 필요한 정보만 요청합니다.</p>}{requiredScopes.map(scope=><label key={scope}><input type="checkbox" checked={checked.includes(scope)} disabled={disabled||busy||isChanging} onChange={e=>{const selected=e.currentTarget.checked;setChecked(old=>selected?[...new Set([...old,scope])]:old.filter(v=>v!==scope));}}/><span><strong>{consentFields[scope].title}</strong><small>{consentFields[scope].description}</small></span></label>)}
 <button type="button" className="ui-button primary" disabled={disabled||busy||isChanging||!requiredScopes.every(scope=>checked.includes(scope))} onClick={approve}>{busy?'동의를 등록하고 있어요…':'동의하고 이 질문 이어가기'}</button></>}{error&&<p role="alert">{error}</p>}</section>;
}
