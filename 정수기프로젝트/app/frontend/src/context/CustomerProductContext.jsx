import{readConnection,saveConnection}from '../api/connectionStorage.js';
import{isProductConnected,publicSessionAfterLogin}from '../api/connectionState.js';
import React,{createContext,useContext,useRef,useState,useEffect}from 'react';
import{createDemoSession,consentEvent,loadCurrentContract,verifyDemoIdentity,currentAccount,loginAccount,logoutAccount,createGuestSession,restoreConnection}from '../api/chatApi.js';
const Context=createContext(null);
export function CustomerProductProvider({children}){
  const[session,setSession]=useState(null);const[selectedProduct,setSelectedProduct]=useState(null);const[isChanging,setChanging]=useState(true);
  const[account,setAccount]=useState(null);
  const owner=useRef(null);const current=useRef(null);const pending=useRef(null);
  function toProduct(profile,result){
    const terms=result.terms||{};
    return {demo_customer_id:profile.demo_customer_id,productId:profile.demo_customer_id,productName:profile.display_name+' · '+profile.product_model,modelId:profile.product_model,imageUrl:result.product?.image_url||null,displayName:result.product?.display_name||profile.product_model,serviceType:profile.usage_type,status:'연결됨',contract:result.status==='ok'?{contractId:result.document_id,startDate:terms.contract_start,mandatoryUseEnd:terms.mandatory_end,contractEnd:terms.contract_end,monthlyFee:terms.monthly_fee}:null,purchase:result.status==='not_applicable'?{}:null};
  }
  useEffect(()=>{let alive=true;(async()=>{
    try{
      const r=await currentAccount();if(!alive)return;
      owner.current=r.account;setAccount(r.account);
      const cached=readConnection(window.sessionStorage,r.account);
      if(cached){
        try{
          const result=await restoreConnection(cached);if(!alive)return;
          commit({...cached,scopes:result.scopes,expires_at:Date.now()+result.expires_in_seconds*1000,identity_expires_at:Date.now()+result.identity_expires_in_seconds*1000});
          setSelectedProduct(toProduct(r.account,result));
        }catch{if(alive)commit(null);}
      }
    }catch{if(alive){owner.current=null;commit(null);}}
    finally{if(alive)setChanging(false);}
  })();return()=>{alive=false;};},[]);
  function commit(value){current.current=value;setSession(value);saveConnection(window.sessionStorage,value,owner.current);return value;}
  async function ensureSession(){
    if(current.current&&Date.now()<current.current.expires_at)return current.current;
    if(pending.current)return pending.current;
    pending.current=createGuestSession().then(s=>{setSelectedProduct(null);return commit({...s,expires_at:Date.now()+s.expires_in_seconds*1000,scopes:[]});}).finally(()=>{pending.current=null;});
    return pending.current;
  }
  async function revoke(){
    const old=current.current;
    if(old?.tool_access_token){try{await consentEvent(old,'revoke');}catch(error){if(error.status!==403)throw error;}}
    commit(null);setSelectedProduct(null);
  }
  async function verifyIdentity(profile,claimedId,outcome='success'){
    if(!account||profile.demo_customer_id!==account.demo_customer_id)throw new Error('로그인이 필요한 서비스입니다.');
    if(isChanging)return;setChanging(true);
    try{
      await revoke();const s=await createDemoSession(profile.demo_customer_id);
      const fresh={...s,expires_at:Date.now()+s.expires_in_seconds*1000,scopes:[]};commit(fresh);
      const result=await verifyDemoIdentity(fresh,claimedId,outcome);
      commit({...fresh,identity_state:result.identity_state,identity_expires_at:Date.now()+result.expires_in_seconds*1000});
    }finally{setChanging(false);}
  }
  async function selectProduct(profile,scopes){
    if(isChanging)return;setChanging(true);
    try{
      const fresh=current.current;
      if(!fresh||fresh.demo_customer_id!==profile.demo_customer_id||fresh.identity_state!=='demo_verified'||Date.now()>=fresh.identity_expires_at)throw new Error('계정 확인을 먼저 진행해 주세요.');
      const grant=await consentEvent(fresh,'grant',scopes);const authorized=commit({...fresh,...grant});
      const result=scopes.includes('contract_terms')?await loadCurrentContract(authorized):{status:'not_applicable'};
      if(!['ok','not_applicable'].includes(result.status))throw new Error('계약 자료를 확인할 수 없습니다.');
      const terms=result.terms||{};
      setSelectedProduct(toProduct(profile,result));
    }finally{setChanging(false);}
  }
  async function clearSelectedProduct(){setChanging(true);try{await revoke();}finally{setChanging(false);}}
  useEffect(()=>{
    if(!session?.identity_expires_at)return;
    const timer=setTimeout(()=>{window.dispatchEvent(new Event('water-contract-expired'));clearSelectedProduct().catch(()=>{commit(null);setSelectedProduct(null);});},Math.max(0,Math.min(session.expires_at,session.identity_expires_at)-Date.now()));
    return()=>clearTimeout(timer);
  },[session?.session_id,session?.identity_expires_at]);
  async function login(username,password){const result=await loginAccount(username,password);const publicSession=publicSessionAfterLogin(owner.current,current.current);owner.current=result.account;commit(publicSession);setSelectedProduct(null);setAccount(result.account);}
  async function logout(){await logoutAccount();owner.current=null;commit(null);setSelectedProduct(null);setAccount(null);}
  useEffect(()=>{const reset=()=>{owner.current=null;commit(null);setSelectedProduct(null);setAccount(null);};window.addEventListener('water-login-required',reset);return()=>window.removeEventListener('water-login-required',reset);},[]);
  const value={account,login,logout,session,selectedProduct,isChanging,isVerified:isProductConnected(session,selectedProduct),ensureSession,verifyIdentity,selectProduct,clearSelectedProduct,resetCustomerContext:clearSelectedProduct};
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useCustomerProduct(){const value=useContext(Context);if(!value)throw new Error('CustomerProductProvider가 필요합니다.');return value;}
