import React,{useState}from 'react';
import{consentFields,consentPurpose}from '../../api/consentPurpose.js';
import Icon from '../shared/Icon.jsx';
import{useCustomerProduct}from '../../context/CustomerProductContext.jsx';
export default function CustomerProductPicker({onClose,purpose=consentPurpose('contract')}){
 const{account,verifyIdentity,selectProduct,clearSelectedProduct,isChanging,session}=useCustomerProduct();
 const[error,setError]=useState('');const[agreed,setAgreed]=useState(session?.scopes||[]);
 const verified=account&&session?.demo_customer_id===account.demo_customer_id&&session?.identity_state==='demo_verified'&&Date.now()<session.identity_expires_at;
 async function identify(){setError('');try{await verifyIdentity(account,account.demo_customer_id);}catch(e){setError(e.message);}}
 async function grant(){setError('');try{await selectProduct(account,[...new Set([...(session?.scopes||[]),...purpose.scopes])]);onClose?.();}catch(e){setError(e.message);}}
 async function decline(){try{await clearSelectedProduct();onClose?.();}catch(e){setError(e.message);}}
 return <section className="account-consent-panel"><div className="picker-eyebrow"><Icon name="shield"/>내 계약 정보 연결</div><h2>필요한 정보만 확인할게요</h2><p>현재 계정의 계약 정보를 연결합니다.</p><div className="account-product-summary"><Icon name="water" size={28}/><div><strong>{account?.display_name||'계정 정보 확인 중'}</strong><span>{account?.product_model||'서버 연결을 확인해 주세요'}</span></div></div>
 <div className="consent-step"><span className="step-number">1</span><div><h3>계정 확인</h3><p>{verified?'확인됐어요. 조회할 정보 범위를 선택해 주세요.':'로그인한 계정의 연결 상태를 확인합니다.'}</p><button className="ui-button primary" disabled={!account||isChanging||verified} onClick={identify}>{verified?'확인 완료':'계정 확인하기'}</button></div></div>
 <div className="consent-step"><span className="step-number">2</span><div><h3>{session?.scopes?.length?'조회 범위 추가':purpose.title+'에 필요한 동의'}</h3><p>이번 질문에 필요한 정보만 요청합니다. 동의하지 않아도 공개 자료 상담은 이용할 수 있어요.</p>{purpose.scopes.map(scope=><label className="consent-checkbox" key={scope}><input type="checkbox" checked={agreed.includes(scope)} disabled={!verified||isChanging} onChange={e=>setAgreed(old=>e.target.checked?[...old,scope]:old.filter(s=>s!==scope))}/><span><strong>{consentFields[scope].title} (필수)</strong><small>{consentFields[scope].description}</small></span></label>)}<button className="ui-button primary" disabled={!verified||!purpose.scopes.every(s=>agreed.includes(s))||isChanging} onClick={grant}>{isChanging?'연결 중…':'동의하고 조회 연결'}</button></div></div>
 {error&&<p className="error-message" role="alert">{error}</p>}<button className="ui-button secondary" onClick={decline} disabled={isChanging}>개인 정보 연결 없이 상담</button></section>;
}
