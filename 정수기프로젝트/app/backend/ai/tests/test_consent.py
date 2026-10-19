import asyncio
import pytest
from fastapi.testclient import TestClient
from ai.main import create_app, Settings
from 정수기프로젝트.app.consent import ConsentStore, ConsentDenied
from 정수기프로젝트.app.mcp.contracts import protected_tools
from 정수기프로젝트.app.mcp.client_adapter import call_tool, get_tool_specs, MCPToolError



@pytest.fixture
def setup(tmp_path, monkeypatch):
    path=tmp_path/'consent.sqlite3'
    monkeypatch.setenv('CONSENT_DB',str(path))
    async def runner(message, context):
        auth=context['tool_authorization']
        result=await call_tool('lookup_contract_terms',{},trusted_authorization=auth)
        return {'status':'answered','topic':'contract','answer':result['status']}
    client=TestClient(create_app(Settings(require_login=False,consent_db=path,brief_root=tmp_path/'briefs'),agent_runner=runner))
    return client,ConsentStore(path)


def new(client, customer='DEMO-U01'):
    r=client.post('/demo-sessions',json={'demo_customer_id':customer})
    assert r.status_code==200
    data=r.json();h={'X-Demo-Session-Key':data['session_key']}
    assert client.post(f"/demo-sessions/{data['session_id']}/identity",headers=h,json={'claimed_demo_customer_id':customer}).status_code==200
    return data,h


def event(client,data,headers,action='grant',scopes=None,customer=None):
    body={'action':action,'scopes':scopes if scopes is not None else ['contract_terms','contract_costs']}
    if customer:body['demo_customer_id']=customer
    if action=='grant' and headers.get('X-Demo-Session-Key'):
        try:
            selected=client.app.state.consents.owned(data['session_id'],headers['X-Demo-Session-Key'])[1]
        except ConsentDenied: pass
        else:
            client.post(f"/demo-sessions/{data['session_id']}/identity",headers=headers,json={'claimed_demo_customer_id':selected,'outcome':'success'})
    return client.post(f"/demo-sessions/{data['session_id']}/consent",headers=headers,json=body)




def test_decline_wrong_key_other_session_and_profile_switch(setup):
    client,store=setup;a,ha=new(client);b,hb=new(client,'DEMO-U02')
    assert event(client,a,{},'grant').status_code==403
    token=event(client,a,ha).json()['tool_access_token']
    assert protected_tools.lookup_contract_terms(b['session_id'],token)['status']=='forbidden'
    assert event(client,a,ha,'select_profile',[],'DEMO-U02').status_code==200
    assert protected_tools.lookup_contract_terms(a['session_id'],token)['status']=='forbidden'
    token2=event(client,a,ha).json()['tool_access_token']
    cost=protected_tools.assess_exit_costs(a['session_id'],token2,'2026-10-02')
    assert cost['estimated_total'] is None and cost['confirmed_subtotal']==50000
    assert event(client,a,ha,'decline',[]).status_code==200
    assert protected_tools.lookup_contract_terms(a['session_id'],token2)['status']=='forbidden'


def test_scope_expiry_no_contract_and_required_date(setup,tmp_path):
    client,store=setup;data,h=new(client)
    token=event(client,data,h,scopes=['contract_terms']).json()['tool_access_token']
    terms=protected_tools.lookup_contract_terms(data['session_id'],token)['terms']
    assert 'arrears' not in terms and 'discount_return' not in terms
    assert protected_tools.assess_exit_costs(data['session_id'],token,'2026-10-02')['status']=='forbidden'
    c,hc=new(client,'DEMO-U03');ctoken=event(client,c,hc).json()['tool_access_token']
    assert protected_tools.lookup_contract_terms(c['session_id'],ctoken)['status']=='not_applicable'
    token=event(client,data,h).json()['tool_access_token']
    assert protected_tools.assess_exit_costs(data['session_id'],token,'')['status']=='needs_info'
    assert protected_tools.assess_exit_costs(data['session_id'],token,'2026-02-30')['code']=='INVALID_DATE'
    clock=[1000];expiring=ConsentStore(tmp_path/'ttl.sqlite3',ttl=2,clock=lambda:clock[0])
    d=expiring.create('DEMO-U01');t=expiring.event(d['session_id'],d['session_key'],'grant',['contract_terms'])['tool_access_token']
    clock[0]=1002
    with pytest.raises(ConsentDenied):expiring.authorize(d['session_id'],t,'contract_terms')




def test_llm_schema_hides_authority(setup):
    specs=asyncio.run(get_tool_specs())
    for spec in specs:
        if spec['name'] in {'lookup_contract_terms','assess_exit_costs'}:
            assert 'access_token' not in spec['input_schema']['properties']
            assert 'session_id' not in spec['input_schema']['properties']


def test_managed_brief_requires_key_and_revocation_blocks_download(setup):
    client,store=setup;data,h=new(client)
    app=client.app
    path=app.state.settings.brief_root/'test.md'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('# 가상 준비서',encoding='utf-8')
    app.state.briefs.register('brief-test-0001',path,data['session_id'])
    working=app.state.sessions.begin(data['session_id'])
    working.brief_ids.add('brief-test-0001')
    app.state.sessions.finish(data['session_id'],working)
    headers={'X-Session-ID':data['session_id']}
    url='/briefs/brief-test-0001'
    assert client.get(url,headers=headers).status_code==403
    assert client.get(url,headers={**headers,**h}).status_code==200
    assert event(client,data,h,'revoke',[]).status_code==200
    assert client.get(url,headers={**headers,**h}).status_code==403


def test_scope_failure_reason_has_no_contract_or_secrets(setup):
    client,store=setup;data,h=new(client)
    token=event(client,data,h,scopes=['contract_terms']).json()['tool_access_token']
    result=protected_tools.assess_exit_costs(data['session_id'],token,'2026-10-03')
    assert result['code']=='CONSENT_SCOPE_REQUIRED'
    assert result['required_scope']=='contract_costs'
    assert result['estimated_total'] is None
    assert token not in str(result) and data['session_id'] not in str(result)
    wrong=protected_tools.assess_exit_costs(data['session_id'],'wrong','2026-10-03')
    assert wrong['code']=='INVALID_TOOL_TOKEN' and 'required_scope' not in wrong
    event(client,data,h,'revoke',[])
    assert protected_tools.assess_exit_costs(data['session_id'],token,'2026-10-03')['code']=='CONSENT_REQUIRED'


def test_expiry_reason_requires_matching_token(tmp_path):
    clock=[1000]
    store=ConsentStore(tmp_path/'reasons.sqlite3',ttl=2,clock=lambda:clock[0])
    data=store.create('DEMO-U01')
    token=store.event(data['session_id'],data['session_key'],'grant',['contract_terms'])['tool_access_token']
    clock[0]=1002
    with pytest.raises(ConsentDenied) as error:
        store.authorize(data['session_id'],token,'contract_costs')
    assert error.value.code=='SESSION_EXPIRED'
    with pytest.raises(ConsentDenied) as error:
        store.authorize(data['session_id'],'wrong','contract_costs')
    assert error.value.code=='INVALID_TOOL_TOKEN'


def test_additive_scope_keeps_reason_history_but_reduction_clears(setup):
    client,_=setup;data,h=new(client);sid=data['session_id']
    grant=client.post(f'/demo-sessions/{sid}/consent',headers=h,json={'action':'grant','scopes':['contract_terms']})
    assert grant.status_code==200
    working=client.app.state.sessions.begin(sid)
    working.history=[{'role':'user','content':'계약 조건이 헷갈려서 교체를 고민해요'},{'role':'assistant','content':'어떤 조건이 궁금한가요?'}]
    client.app.state.sessions.finish(sid,working)
    r=client.post(f'/demo-sessions/{sid}/consent',headers=h,json={'action':'grant','scopes':['contract_terms','contract_costs']})
    assert r.status_code==200
    working=client.app.state.sessions.begin(sid)
    assert working.history[0]['content']=='계약 조건이 헷갈려서 교체를 고민해요'
    client.app.state.sessions.finish(sid,working)
    r=client.post(f'/demo-sessions/{sid}/consent',headers=h,json={'action':'grant','scopes':['contract_terms']})
    assert r.status_code==200
    working=client.app.state.sessions.begin(sid)
    assert working.history==[]
    client.app.state.sessions.finish(sid,working)
