const KEY='water-authorized-connection-v1';
const FIELDS=['session_id','session_key','tool_access_token','demo_customer_id','expires_at','identity_state','identity_expires_at','scopes'];
export function saveConnection(storage,session,account){
 try{
  if(!session?.tool_access_token||!account?.username){storage.removeItem(KEY);return;}
  storage.setItem(KEY,JSON.stringify({owner:account.username,session:Object.fromEntries(FIELDS.filter(k=>k in session).map(k=>[k,session[k]]))}));
 }catch{}
}
export function readConnection(storage,account,now=Date.now()){
 try{
  const value=JSON.parse(storage.getItem(KEY)||'null');const s=value?.session;
  if(!account||value?.owner!==account.username||s?.demo_customer_id!==account.demo_customer_id||!s?.tool_access_token||!s?.session_key||now>=s.expires_at||now>=s.identity_expires_at){storage.removeItem(KEY);return null;}
  return s;
 }catch{try{storage.removeItem(KEY);}catch{}return null;}
}
