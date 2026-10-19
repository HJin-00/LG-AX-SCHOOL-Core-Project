// 모델 조회 권한과 실제 선택 제품이 함께 유효할 때만 연결 완료로 표시합니다.
export function isProductConnected(session, product, now=Date.now()) {
 return !!(session?.tool_access_token && product?.modelId
  && session.demo_customer_id===product.demo_customer_id
  && session.identity_state==='demo_verified'
  && now<session.expires_at && now<session.identity_expires_at
  && session.scopes?.some(scope=>['contract_terms','care_info'].includes(scope)));
}

// 비로그인 → 내 계약 연결 또는 같은 고객의 재동의는 대화를 이어간다.
// 로그아웃·다른 고객 변경 때만 이전 고객의 대화를 지운다.
export function shouldResetConversation(previousCustomerId,nextCustomerId) {
 return !!previousCustomerId && previousCustomerId!==nextCustomerId;
}

// 첫 로그인은 공개 상담만 이어받는다. 개인 계약 권한이나 다른 계정 세션은 이전하지 않는다.
export function publicSessionAfterLogin(previousAccount,session,now=Date.now()) {
 if(previousAccount||!session||session.session_key||session.tool_access_token||session.demo_customer_id||now>=session.expires_at)return null;
 return session;
}
