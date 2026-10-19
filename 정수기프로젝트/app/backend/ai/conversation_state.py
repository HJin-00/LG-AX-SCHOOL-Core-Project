"""Untrusted display snapshots never become authoritative model history."""
def valid_state(state):
    allowed={'messages','activeTopic','showRenewalReason','showContractQuestion','showRenewalPreferences','renewalContext'}
    if not isinstance(state,dict) or set(state)-allowed or not isinstance(state.get('messages'),list):return False
    if state.get('activeTopic') is not None and not isinstance(state['activeTopic'],str):return False
    if any(k in state and not isinstance(state[k],bool) for k in ('showRenewalReason','showContractQuestion','showRenewalPreferences')):return False
    if state.get('renewalContext') is not None and not isinstance(state['renewalContext'],dict):return False
    from pydantic import TypeAdapter, ValidationError
    from .schemas import Card, Source
    for m in state['messages']:
        if not isinstance(m,dict) or m.get('role') not in {'user','assistant','error'}:return False
        if any(k in m and m[k] is not None and not isinstance(m[k],str) for k in ('text','answer','requestQuestion','requestTopic','requestLabel','code')):return False
        for key in ('cards','sources'):
            if key in m and (not isinstance(m[key],list) or any(not isinstance(v,dict) for v in m[key])):return False
        if 'next_actions' in m and (not isinstance(m['next_actions'],list) or any(not isinstance(v,str) for v in m['next_actions'])):return False
        try:
            TypeAdapter(list[Card]).validate_python(m.get('cards',[]))
            TypeAdapter(list[Source]).validate_python(m.get('sources',[]))
        except (ValidationError,TypeError):return False
        if 'missing_fields' in m and (not isinstance(m['missing_fields'],list) or any(not isinstance(v,str) for v in m['missing_fields'])):return False
        if any(not isinstance(c.get('type'),str) or not isinstance(c.get('data'),dict) for c in m.get('cards',[])):return False
    return True
