import {candidateRequest,renewalPreferencesFromMessages} from '../api/renewalSelection.js';
import {loadConversation,saveConversation,resetConversation} from '../api/chatApi.js';
import RenewalReason from '../components/products/RenewalReason.jsx';
import{shouldResetConversation}from '../api/connectionState.js';
import{responseTopic,responseLabels}from '../api/responseTopic.js';
import lgSymbol from '../assets/lg-symbol.png';
import{consentPurpose,hasConsent}from '../api/consentPurpose.js';
import React,{useEffect,useRef,useState}from 'react';
import{Link}from 'react-router-dom';
import{apiRequest,sendChatMessage,downloadServerBrief}from '../api/chatApi.js';
import ChatInput from '../components/chat/ChatInput.jsx';
import Conversation from '../components/chat/Conversation.jsx';
import Sidebar from '../components/layout/Sidebar.jsx';
import Welcome from '../components/layout/Welcome.jsx';
import CustomerProductPicker from '../components/account/CustomerProductPicker.jsx';
import SelectedProductBar from '../components/account/SelectedProductBar.jsx';
import{useCustomerProduct}from '../context/CustomerProductContext.jsx';
import{services}from '../components/layout/topics.js';
import Icon from '../components/shared/Icon.jsx';
import RequiredInformation from '../components/chat/RequiredInformation.jsx';
import LoginPanel from '../components/account/LoginPanel.jsx';

function productToContract(product){
 if(!product)return null;
 return {serviceType:product.serviceType,productName:product.productName,contractId:product.contract?.contractId||product.productId,contractStart:product.contract?.startDate,mandatoryUseEnd:product.contract?.mandatoryUseEnd,contractEnd:product.contract?.contractEnd,monthlyFee:product.contract?.monthlyFee};
}
export default function ServicePage({serviceType}){
 const{account,logout,session,selectedProduct,isVerified,isChanging,ensureSession,resetCustomerContext}=useCustomerProduct();
 const[showContractQuestion,setShowContractQuestion]=useState(false);const[hiddenInformationAt,setHiddenInformationAt]=useState(null);
 const[showRenewalReason,setShowRenewalReason]=useState(false);
 const[sidebarOpen,setSidebarOpen]=useState(false);
 const service=services[serviceType];const[messages,setMessages]=useState([]);const[draft,setDraft]=useState('');const[activeTopic,setActiveTopic]=useState(null);
 const[loadingLabel,setLoadingLabel]=useState('상담 답변을 준비하고 있어요');const[isSending,setSending]=useState(false);const[showProductPicker,setShowProductPicker]=useState(false);const[briefDownloaded,setBriefDownloaded]=useState(false);
 const[recommendationCompleted,setRecommendationCompleted]=useState(false);const[connection,setConnection]=useState('연결 확인 중');
 const[showLogin,setShowLogin]=useState(false);const[pendingCategory,setPendingCategory]=useState(null);
 const[queryConsent,setQueryConsent]=useState(consentPurpose('contract'));const[pendingQuestion,setPendingQuestion]=useState(null);
 const pendingScroll=useRef(null);
 const chatMainRef=useRef(null);const locked=useRef(false);const saveChain=useRef(Promise.resolve());const stateVersion=useRef({revision:0,epoch:0});const resetInProgress=useRef(false);const storageBlocked=useRef(false);const restoringSnapshot=useRef(false);const [storageError,setStorageError]=useState('');const [restoreAttempt,setRestoreAttempt]=useState(0);const previousCustomer=useRef(null);
 const selectedContract=productToContract(selectedProduct);
 const[connectionNotice,setConnectionNotice]=useState('');
 useEffect(()=>{const expired=()=>setConnectionNotice('계약 조회 권한이 만료됐어요. 계약을 다시 연결해 상담을 이어주세요.');window.addEventListener('water-contract-expired',expired);return()=>window.removeEventListener('water-contract-expired',expired);},[]);
 useEffect(()=>{let alive=true;apiRequest('/health').then(h=>{if(alive)setConnection(h.agent_connected?'AI 연결됨':'API 연결됨 · AI 설정 필요');}).catch(()=>{if(alive)setConnection('서버 연결 확인 필요');});return()=>{alive=false;};},[]);
 useEffect(()=>{if(!chatMainRef.current)return;if(pendingScroll.current!=null){const element=document.getElementById(`message-${pendingScroll.current}`);if(element){element.scrollIntoView({behavior:'smooth',block:'start'});pendingScroll.current=null;return;}}if(isSending)chatMainRef.current.scrollTop=chatMainRef.current.scrollHeight;},[messages,isSending]);
 useEffect(()=>{
   const customer=account?.demo_customer_id||null;
   // 계약 연결은 권한 세션만 갱신한다. 고객이 같으면 질문·응답·입력을 유지한다.
   if(shouldResetConversation(previousCustomer.current,customer)){
     setShowRenewalReason(false);setShowContractQuestion(false);setMessages([]);setDraft('');setActiveTopic(null);setBriefDownloaded(false);setRecommendationCompleted(false);
     setPendingQuestion(null);setPendingCategory(null);setShowProductPicker(false);setShowRenewalPreferences(false);setRenewalContext(null);
   }
   previousCustomer.current=customer;
 },[account?.demo_customer_id]);
 async function sendMessage(text=draft,topic=activeTopic,options={}){
  setShowRenewalReason(false);setShowContractQuestion(false);setShowRenewalPreferences(false);
  const question=text?.trim();if(!question||locked.current||isChanging||!conversationReady)return null;
  setLoadingLabel(topic==='renewal'?'선택한 제품의 유지·재구독 비용을 비교하고 있어요':topic==='recommend'?'조건에 맞는 정수기 후보를 찾고 있어요':topic==='contract'||topic==='cancel'?'계약 조건과 예상 비용을 확인하고 있어요':topic==='troubleshoot'?'제품 증상과 안전한 점검 방법을 확인하고 있어요':'질문에 필요한 자료를 확인하고 있어요');
  locked.current=true;setSending(true);if(!options.silent)setDraft('');setBriefDownloaded(false);setActiveTopic(topic);
  try{
   const active=await ensureSession();
   if(!restoredConversation.current){restoredConversation.current=active.session_id;stateVersion.current={revision:0,epoch:0};}
   await saveChain.current;
   if(!options.silent)setMessages(m=>[...m,{role:'user',text:options.displayText||question}]);
   const result=await sendChatMessage({session:active,message:question,product:selectedProduct});
   const resolved=responseTopic(result,topic,options.originTopic);setActiveTopic(resolved);
   setMessages(m=>{pendingScroll.current=m.length;return [...m,{...result,role:'assistant',requestContextTopic:options.originTopic||topic,requestTopic:resolved,requestQuestion:question,requestLabel:responseLabels[resolved]||service.categories.find(c=>c.id===resolved)?.label||'상담 질문',allowRenewalSelection:serviceType==='existing',requestSummary:options.summary||null}];});return result;
  }catch(error){setMessages(m=>[...m,{role:'error',text:error.message,code:error.code,retryQuestion:question,retryTopic:topic}]);return null;}
  finally{locked.current=false;setSending(false);}
 }
 function startCategory(category,forceNew=false){
  if(!category||isSending||isChanging||!conversationReady)return;
  setShowContractQuestion(false);
  setActiveTopic(category.id);
  if(category.id==='renewal'){return sendMessage(category.prompt,category.id);}
  setShowRenewalReason(false);
  const previous=messages.findLastIndex(m=>m.requestTopic===category.id);
  if(previous>=0&&!forceNew){document.getElementById(`message-${previous}`)?.scrollIntoView({behavior:'smooth',block:'start'});return;}
  sendMessage(category.prompt,category.id,{categoryStart:true});
 }
 useEffect(()=>{if(selectedProduct&&pendingCategory&&!isChanging&&hasConsent(session,consentPurpose(pendingCategory.id))){const category=pendingCategory;setPendingCategory(null);startCategory(category);}},[selectedProduct?.productId,pendingCategory,isChanging,session?.tool_access_token]);
 useEffect(()=>{if(pendingQuestion&&!isChanging&&hasConsent(session,queryConsent)){const q=pendingQuestion;setPendingQuestion(null);sendMessage(q.question,q.topic,q.options);}},[pendingQuestion,isChanging,session?.tool_access_token]);
 async function signOut(){try{await logout();setMessages([]);setDraft('');setShowProductPicker(false);setPendingCategory(null);}catch(e){setMessages(m=>[...m,{role:'error',text:e.message}]);}}
 async function startNewChat(){
  if(isSending||isChanging||resetInProgress.current)return;
  resetInProgress.current=true;setConversationReady(false);
  try{await saveChain.current.catch(()=>{});const active=await ensureSession();const result=await resetConversation(active);stateVersion.current={revision:result.revision,epoch:result.epoch};storageBlocked.current=false;setStorageError('');setShowRenewalPreferences(false);setRenewalContext(null);setShowRenewalReason(false);setShowContractQuestion(false);setMessages([]);setDraft('');setActiveTopic(null);setBriefDownloaded(false);setRecommendationCompleted(false);}
  catch(error){setStorageError(error.message);}
  finally{resetInProgress.current=false;setConversationReady(true);}
 }
 async function selectRenewalOffer(offer){
  return sendMessage('유지·재구독 비교를 계속해줘. 선택한 제품으로 기존 계약 정산 비용과 신규 구독 비용을 비교해줘. 고객이 지정한 전환일이 없으면 오늘 기준으로 비교하고 결과에서 날짜와 비교 기간을 변경할 수 있게 해줘.\n'+JSON.stringify({...(renewalContext||{}),...(offer.selection_preferences||{}),...(offer.offer_id?{offer_id:offer.offer_id}:{new_model_id:offer.model_id})}),'renewal',{silent:true,summary:[offer.model_id,offer.care_details].filter(Boolean).join(' · ')});
 }
 async function requestRenewalBrief(request){
  return await sendMessage('이 유지·재구독 비교 조건으로 상담 준비서를 생성해줘. 새 계산으로 조건과 권한을 확인하고 미확인 항목도 포함해줘.\n'+JSON.stringify(request),'renewal',{silent:true});
 }
 async function prepareConsultation(message){
  const renewal=message.cards?.find(c=>c.type==='renewal_comparison');
  if(renewal)return requestRenewalBrief(renewal.data.request);
  const comparison=message.cards?.find(c=>c.type==='comparison');
  const cost=message.cards?.find(c=>c.type==='contract'&&c.data.period_summary?.exit_date);
  const request=comparison?{comparison_date:comparison.data.comparison_date,exit_date_a:comparison.data.options[0].exit_date,exit_date_b:comparison.data.options[1].exit_date}:cost?{exit_date:cost.data.period_summary.exit_date}:null;
  return sendMessage('현재 확인된 상담 내용을 상담용 준비서로 생성해줘. 미확인 항목과 상담에서 확인할 질문을 포함해줘.'+(request?'\n'+JSON.stringify(request):''),'contract',{silent:true});
 }
 async function downloadBrief(requestedId){
  if(isSending||isChanging)return;
  const id=typeof requestedId==='string'?requestedId:null;
  if(!id)return;
  try{await downloadServerBrief(await ensureSession(),id);setBriefDownloaded(true);}
  catch(error){setMessages(m=>[...m,{role:'error',text:error.message,code:error.code}]);}
 }
 const[showRenewalPreferences,setShowRenewalPreferences]=useState(false);const[renewalContext,setRenewalContext]=useState(null);
 const [conversationReady,setConversationReady]=useState(true);const restoredConversation=useRef(null);
 useEffect(()=>{
  if(isChanging||isSending)return;
  const key=session?.session_id||null;
  if(!key){restoringSnapshot.current=false;if(restoredConversation.current){setMessages([]);setShowRenewalReason(false);setShowContractQuestion(false);setShowRenewalPreferences(false);setRenewalContext(null);}restoredConversation.current=null;setConversationReady(true);return;}
  if(restoredConversation.current===key&&!storageError){setConversationReady(true);return;}
  if(session.session_key&&!session.tool_access_token){setConversationReady(true);return;}
  let alive=true;restoringSnapshot.current=true;setConversationReady(false);restoredConversation.current=key;
  loadConversation(session).then(({state,revision,epoch})=>{if(!alive)return;stateVersion.current={revision:revision||0,epoch:epoch||0};restoringSnapshot.current=false;storageBlocked.current=false;setStorageError('');if(state){setMessages(state.messages||[]);setActiveTopic(state.activeTopic||null);setShowRenewalReason(Boolean(state.showRenewalReason));setShowContractQuestion(Boolean(state.showContractQuestion));setShowRenewalPreferences(Boolean(state.showRenewalPreferences));setRenewalContext(state.renewalContext||null);pendingScroll.current=Math.max(0,state.messages.length-1);}setConversationReady(true);}).catch(error=>{if(alive){restoredConversation.current=null;setStorageError(error.status===403?'계약 연결이 만료되었습니다. 다시 연결한 뒤 상담을 이어주세요.':error.message||'상담을 불러오지 못했어요. 다시 시도해 주세요.');setConversationReady(false);}});
  return()=>{alive=false;};
 },[session?.session_id,isChanging,isSending,restoreAttempt]);
 useEffect(()=>{
  if(!conversationReady||restoringSnapshot.current||storageError||resetInProgress.current||isSending||isChanging||!session?.session_id||(session.session_key&&!session.tool_access_token))return;
  const snapshot={messages:messages.slice(-40),activeTopic,showRenewalReason,showContractQuestion,showRenewalPreferences,renewalContext};
  const epoch=stateVersion.current.epoch;
  saveChain.current=saveChain.current.then(async()=>{
   if(resetInProgress.current||storageBlocked.current||epoch!==stateVersion.current.epoch)return;
   const result=await saveConversation(session,snapshot,stateVersion.current);
   stateVersion.current={revision:result.revision,epoch:result.epoch};
  }).catch(error=>{storageBlocked.current=true;setStorageError(error.status===409?'다른 창에서 상담이 변경되었습니다. 최신 상담을 다시 불러와 주세요.':'상담을 저장하지 못했어요. 현재 화면을 유지하고 다시 시도해 주세요.');setConversationReady(false);});
 },[messages,activeTopic,showRenewalReason,showContractQuestion,showRenewalPreferences,renewalContext,conversationReady,isSending,isChanging,session?.session_id,session?.tool_access_token]);
 async function disconnectContract(){if(isSending||isChanging)return;await resetCustomerContext();setMessages([]);setActiveTopic(null);setShowRenewalReason(false);setShowContractQuestion(false);setShowRenewalPreferences(false);setRenewalContext(null);}
 const lastAssistant=[...messages].reverse().find(m=>m.role==='assistant');
 const needsConsent=lastAssistant?.missing_fields?.includes('consent');
 return <div className={`app-shell consultation-bento bento-menu-layout${sidebarOpen?' bento-menu-open':''}`} onKeyDown={e=>{if(e.key==='Escape')setSidebarOpen(false);}}>
  {showLogin&&<LoginPanel onClose={()=>{setShowLogin(false);setPendingCategory(null);if(!account)setShowProductPicker(false);}} onSuccess={()=>{setShowLogin(false);if(pendingCategory)setShowProductPicker(true);}}/>}
  {sidebarOpen&&<><button className="bento-menu-backdrop" type="button" aria-label="상담 메뉴 닫기" onClick={()=>setSidebarOpen(false)}/><div id="consultation-sidebar" className="bento-sidebar-panel"><Sidebar disabled={isSending||isChanging||!conversationReady} topics={service.categories} activeTopic={activeTopic} onTopicSelect={category=>{setShowProductPicker(false);startCategory(category);if(window.matchMedia('(max-width:800px)').matches)setSidebarOpen(false);}} onNewChat={startNewChat}/></div></>}
  <div className="work-area">
   <header className="app-header"><div className="bento-header-left"><button className="bento-menu-toggle" type="button" aria-label={sidebarOpen?'상담 메뉴 닫기':'상담 메뉴 열기'} aria-expanded={sidebarOpen} aria-controls="consultation-sidebar" onClick={()=>setSidebarOpen(!sidebarOpen)}><Icon name="menu" size={22}/></button><Link className="bento-brand" to="/" aria-label="홈으로"><img src={lgSymbol} alt=""/><strong>LG전자</strong></Link><span className="bento-header-service">계약·재구독 상담</span></div><div className="bento-header-actions"><button type="button" className="bento-new-chat" disabled={isSending||isChanging||!conversationReady} onClick={startNewChat}>＋ 새 대화</button>{account?<div className="customer-account"><span className="customer-avatar">{account.display_name.slice(0,1)}</span><div><strong>{account.display_name}</strong><small>{isVerified?'계약 연결됨':'로그인됨'}</small></div><button className="account-logout" onClick={signOut} disabled={isSending||isChanging||!conversationReady}>로그아웃</button></div>:<button className="ui-button secondary" disabled={isSending||isChanging||!conversationReady} onClick={()=>setShowLogin(true)}>로그인</button>}<Link className="bento-home-link" to="/">홈으로</Link></div></header>
   <main aria-busy={isSending||isChanging||!conversationReady} className="chat-main" ref={chatMainRef}>
    {connectionNotice&&<div role="status" className="required-information"><p>{connectionNotice}</p><button type="button" onClick={()=>{setShowProductPicker(true);setConnectionNotice('');}}>계약 다시 연결하기</button></div>}
    {storageError&&<div role="alert" className="required-information"><p>{storageError}</p><button type="button" onClick={()=>{restoredConversation.current=null;setRestoreAttempt(n=>n+1);}}>상담 다시 불러오기</button><button type="button" onClick={()=>{setShowProductPicker(true);if(!account)setShowLogin(true);}}>계약 다시 연결하기</button><button type="button" onClick={startNewChat}>새 대화 시작</button></div>}
    {showProductPicker?<><button type="button" className="home-link" disabled={isChanging} onClick={()=>setShowProductPicker(false)}>상담으로 돌아가기</button><CustomerProductPicker key={queryConsent.scopes.join()} purpose={queryConsent} onClose={()=>setShowProductPicker(false)}/></>:<>
     
     {serviceType==='existing'&&selectedProduct&&<SelectedProductBar disabled={isSending||isChanging||!conversationReady} onChangeProduct={()=>{if(!isSending)setShowProductPicker(true);}} onDisconnect={disconnectContract}/>}

     {(showRenewalPreferences||showContractQuestion||showRenewalReason||(lastAssistant?.status==='needs_info'&&lastAssistant.missing_fields?.some(f=>['renewal_preferences','contract_question','renewal_reason','support_or_compare'].includes(f))&&hiddenInformationAt!==messages.length))&&<button type="button" className="ui-button secondary" onClick={()=>{setShowRenewalPreferences(false);setShowContractQuestion(false);setShowRenewalReason(false);setHiddenInformationAt(messages.length);}}>이전 상담으로 돌아가기</button>}
     {showRenewalPreferences?<RequiredInformation fields={['renewal_preferences']} initialValues={renewalPreferencesFromMessages(messages)} disabled={isSending||isChanging||!conversationReady} onSubmit={(text,input)=>sendMessage('선택한 희망 조건에 맞는 새 정수기 후보를 보여줘. 앞서 말한 교체 이유와 조건을 이어받고, 비교 제품은 제가 고를게요.\n'+JSON.stringify({...candidateRequest(messages,renewalContext||{}),...input}),'renewal',{displayText:text})}/>:showContractQuestion?<RequiredInformation fields={['contract_question']} disabled={isSending||isChanging||!conversationReady} onSubmit={(text,input)=>sendMessage('궁금한 계약 조건은 다음과 같아요: '+input.contract_question,'contract',{displayText:text})}/>:showRenewalReason?<RenewalReason disabled={isSending||isChanging||!conversationReady} onSubmit={(text,input)=>{return sendMessage((input.renewal_reason==='계약 조건이 헷갈려요'?'계약 조건 때문에 교체를 고민하고 있어요. 어느 항목이 헷갈리는지 아직 정하지 못했으니 계약 항목을 먼저 선택하게 해주세요. 새 모델 추천은 지금 하지 말아 주세요.':input.renewal_reason==='새로운 기능이 필요해요'||input.renewal_reason==='그냥 다른 제품이 궁금해요'?'새 모델의 어떤 기능이 필요한지 아직 정하지 않았어요. 원하는 기능과 설치·관리 조건을 먼저 선택하게 해주세요.':'교체를 고민하는 이유에 맞는 도움을 받고 싶어요. 이유에 따라 계약 설명, 더 저렴한 후보, 필요한 기능 비교 등 적절한 방법을 안내해 주세요.')+'\n'+JSON.stringify(input),'renewal',{displayText:'교체 이유: '+text});}}/>:!messages.length&&!isSending?<Welcome busy={isSending||isChanging||!conversationReady} serviceType={serviceType} selectedProduct={serviceType==='existing'?selectedProduct:null} onLoadProduct={()=>{setQueryConsent(consentPurpose('contract'));setShowProductPicker(true);if(!account)setShowLogin(true);}} onTopicSelect={category=>startCategory(category,true)}/>:<Conversation onRetry={message=>sendMessage(message.retryQuestion,message.retryTopic,{silent:true})} onNextAction={(action)=>sendMessage(action.id==='compare_new'?'다른 정수기로 바꾸고 싶어요. 새 모델 후보를 추천해 주세요.':action.question,null,{displayText:action.label})} messages={messages} onConsentLogin={()=>setShowLogin(true)} onConsentResume={message=>{setQueryConsent(consentPurpose(message.requestTopic||message.topic,message.requestQuestion));setPendingQuestion({question:message.requestQuestion,topic:message.requestContextTopic||message.requestTopic||message.topic,options:{silent:true,originTopic:message.requestContextTopic}});}} isSending={isSending} onDownloadBrief={downloadBrief} onRequestBrief={requestRenewalBrief} onPrepareConsultation={prepareConsultation}  onSelectRenewalOffer={selectRenewalOffer} onOtherProducts={request=>{const next=candidateRequest(messages,request);setRenewalContext(next);return sendMessage('다른 제품을 고르기 위해 같은 희망 조건과 전환일로 후보를 다시 보여줘. 아직 새 제품을 선택하지 않았으니 임의 비교하지 마.\n'+JSON.stringify(next),'renewal',{silent:true});}} onPreferences={request=>{setRenewalContext(candidateRequest(messages,request));setShowContractQuestion(false);setShowRenewalReason(false);setShowRenewalPreferences(true);}} onChangeRenewal={(request)=>sendMessage('유지·재구독 비교를 계속해줘. 아래 전환일과 제품으로 기존 해지 정산 비용까지 포함해 비교해줘.\n'+JSON.stringify(request),'renewal',{silent:true})} onUseTiming={(date,timing)=>{if(timing?.requestContextTopic==='cancel')return sendMessage('선택한 해지 검토일 기준의 예상 정산 비용을 확인해줘.\n'+JSON.stringify({exit_date:date}),'cancel',{silent:true,summary:date});const chosen=[...messages].reverse().find(m=>m.cards?.some(c=>c.type==='renewal_comparison'))?.cards?.find(c=>c.type==='renewal_comparison')?.data.request;return sendMessage((chosen?'유지·재구독 비교를 계속해줘. 선택한 제품과 전환일 기준으로 비교해줘.':'전환 후보일을 선택했어요. 이 날짜의 신규 제품 후보를 보여줘. 아직 비교 제품을 정하지 않았으니 임의로 같은 제품을 선택해 계산하지 마.')+'\n'+JSON.stringify({...chosen,planned_start_date:date}),'renewal',{silent:true});}} briefDownloaded={briefDownloaded} serviceType={serviceType} onRestartRecommendation={()=>startCategory(service.categories.find(c=>c.id==='recommend'),true)}  recommendationCompleted={recommendationCompleted} contractAuthenticated={isVerified} selectedContract={selectedContract} onContractChange={()=>setShowProductPicker(true)} onContractQuestion={q=>sendMessage(q,'contract')}/>}
     {!showContractQuestion&&!showRenewalReason&&lastAssistant?.status==='needs_info'&&hiddenInformationAt!==messages.length&&!lastAssistant.missing_fields?.includes('consultation_goal')&&<RequiredInformation key={messages.length} initialValues={renewalPreferencesFromMessages(messages)} fields={lastAssistant.missing_fields||[]} onSuggest={()=>{const origin=lastAssistant.requestContextTopic||lastAssistant.requestTopic;return sendMessage(origin==='cancel'?'해지 비용을 확인하려는데 날짜를 아직 모르겠어요. 내 계약 기준으로 해지 검토 후보일을 알려주세요.':'전환 날짜가 미정이에요. 내 계약 기준 후보일을 알려주세요.',origin,{silent:true,originTopic:origin});}} disabled={isSending||isChanging||!conversationReady} onSubmit={(text,input)=>{return sendMessage(('contract_question' in input?'궁금한 계약 조건은 다음과 같아요: '+input.contract_question:'renewal_reason' in input?(input.renewal_reason==='계약 조건이 헷갈려요'?'계약 조건 때문에 교체를 고민하고 있어요. 어느 항목이 헷갈리는지 아직 정하지 못했으니 계약 항목을 먼저 선택하게 해주세요. 새 모델 추천은 지금 하지 말아 주세요.':'교체를 고민하는 이유에 맞는 도움을 받고 싶어요. 이유를 참고해서 필요한 상담을 안내해 주세요.'):'required_features' in input?'이 조건에 맞는 새 정수기 후보를 보여주세요. 비교할 제품은 제가 고를게요.':'선택한 정보로 상담을 이어주세요.')+'\n'+JSON.stringify(input),lastAssistant.requestTopic||lastAssistant.topic,{silent:true,summary:text});}}/>}
    </>}
   </main>
   <ChatInput showExample={!messages.length} value={draft} onChange={setDraft} onSubmit={()=>sendMessage(draft)} busy={isSending} disabled={isSending||isChanging||showProductPicker||!conversationReady}/>
   
  </div>
 </div>;
}
