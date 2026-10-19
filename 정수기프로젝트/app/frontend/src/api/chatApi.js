import axios from 'axios';

const client=axios.create({baseURL:'/api',timeout:100000,withCredentials:true});
export function sessionHeaders(session){
  if(!session)return {};
  return {'X-Session-ID':session.session_id,'X-Demo-Session-Key':session.session_key,...(session.tool_access_token?{'X-Tool-Access-Token':session.tool_access_token}:{})};
}
export async function apiRequest(route,{method='GET',body,session,responseType='json'}={}){
  try{return (await client.request({url:route,method,data:body,headers:sessionHeaders(session),responseType})).data;}
  catch(error){
    const data=error.response?.data;
    const result=new Error(data?.answer||data?.message||(error.code==='ECONNABORTED'?'답변 시간이 길어졌습니다. 다시 시도해 주세요.':'상담 서버 연결을 확인해 주세요.'));
    if(error.response?.status===401)window.dispatchEvent(new Event('water-login-required'));
    result.status=error.response?.status;result.code=data?.code||data?.error?.code||'REQUEST_FAILED';throw result;
  }
}
export const listProfiles=()=>apiRequest('/demo-profiles');
export const createDemoSession=id=>apiRequest('/demo-sessions',{method:'POST',body:{demo_customer_id:id}});
export const consentEvent=(session,action,scopes=[])=>apiRequest(`/demo-sessions/${session.session_id}/consent`,{method:'POST',body:{action,scopes},session});
export const loadCurrentContract=session=>apiRequest('/contracts/current',{session});
export async function sendChatMessage({session,message,product}){
  if(!message?.trim())throw new Error('질문을 입력해 주세요.');
  const body={session_id:session.session_id,message:message.trim()};
  if(product?.modelId)body.product_model=product.modelId;
  // topic·계약 값·토큰을 모델 입력 body에 넣지 않습니다.
  return apiRequest('/chat',{method:'POST',body,session});
}
export async function downloadServerBrief(session,id){
  if(!/^[A-Za-z0-9_-]{8,80}$/.test(id||''))throw new Error('준비서 생성 결과가 없습니다.');
  const blob=await apiRequest(`/briefs/${id}`,{session,responseType:'blob'});
  const url=URL.createObjectURL(blob);const link=document.createElement('a');
  link.href=url;link.download=`정수기_상담준비서_${id}.pdf`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export const verifyDemoIdentity=(session,claimedId,outcome='success')=>apiRequest(`/demo-sessions/${session.session_id}/identity`,{method:'POST',body:{claimed_demo_customer_id:claimedId,outcome},session});
export const estimateInstallation=conditions=>apiRequest('/installation-estimates',{method:'POST',body:conditions});

export const currentAccount=()=>apiRequest('/auth/me');
export const loginAccount=(username,password)=>apiRequest('/auth/login',{method:'POST',body:{username,password}});
export const logoutAccount=()=>apiRequest('/auth/logout',{method:'POST',body:{}});
export const createGuestSession=()=>apiRequest('/guest-sessions',{method:'POST',body:{}});

export const restoreConnection=session=>apiRequest('/connection/current',{session});

export const loadConversation=session=>apiRequest('/conversation/current',{session});
export const saveConversation=(session,state,version={})=>apiRequest('/conversation/state',{method:'POST',body:{state,...version},session});
export const resetConversation=session=>apiRequest('/conversation/reset',{method:'POST',body:{},session});
