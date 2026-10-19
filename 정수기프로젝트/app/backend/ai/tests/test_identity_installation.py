import pytest
from fastapi.testclient import TestClient
from ai.main import create_app,Settings
from ai.demo_identity import DemoIdentityStore


@pytest.fixture
def client(tmp_path,monkeypatch):
    path=tmp_path/'auth.db'
    monkeypatch.setenv('CONSENT_BACKEND','sqlite');monkeypatch.setenv('CONSENT_DB',str(path))
    return TestClient(create_app(Settings(require_login=False,consent_db=path,brief_root=tmp_path/'briefs')))


def new(client,customer='DEMO-U01'):
    s=client.post('/demo-sessions',json={'demo_customer_id':customer}).json()
    return s,{'X-Demo-Session-Key':s['session_key']}


def verify(client,s,h,customer='DEMO-U01',outcome='success'):
    return client.post(f"/demo-sessions/{s['session_id']}/identity",headers=h,json={'claimed_demo_customer_id':customer,'outcome':outcome})


def grant(client,s,h):
    return client.post(f"/demo-sessions/{s['session_id']}/consent",headers=h,json={'action':'grant','scopes':['contract_terms']})


def test_identity_and_consent_separate(client):
    s,h=new(client)
    assert grant(client,s,h).json()['code']=='DEMO_IDENTITY_REQUIRED'
    assert verify(client,s,h).json()['identity_state']=='demo_verified'
    # 인증 시연만으로 권한 토큰을 받지 못합니다.
    assert client.get('/contracts/current',headers={**h,'X-Session-ID':s['session_id']}).status_code==403
    g=grant(client,s,h);assert g.status_code==200
    assert client.get('/contracts/current',headers={**h,'X-Session-ID':s['session_id'],'X-Tool-Access-Token':g.json()['tool_access_token']}).status_code==200


@pytest.mark.parametrize('customer,outcome,code',[('DEMO-U02','success','DEMO_OWNER_MISMATCH'),('DEMO-U01','failure','DEMO_IDENTITY_FAILED')])
def test_failure_revokes_old_grant(client,customer,outcome,code):
    s,h=new(client);verify(client,s,h);token=grant(client,s,h).json()['tool_access_token']
    assert verify(client,s,h,customer,outcome).json()['code']==code
    assert grant(client,s,h).status_code==403
    assert client.get('/contracts/current',headers={**h,'X-Session-ID':s['session_id'],'X-Tool-Access-Token':token}).status_code==403


def test_wrong_session_and_forged_success(client):
    s,h=new(client);other,oh=new(client,'DEMO-U02')
    assert verify(client,s,oh).status_code==403
    assert client.post(f"/demo-sessions/{s['session_id']}/identity",headers=h,json={'claimed_demo_customer_id':'DEMO-U01','identity_state':'demo_verified'}).status_code==422
    assert grant(client,other,oh).status_code==403


def test_expiry_and_revoke(client):
    now=[0];client.app.state.identities=DemoIdentityStore(clock=lambda:now[0],ttl=10)
    s,h=new(client);verify(client,s,h);assert grant(client,s,h).status_code==200
    now[0]=10;assert grant(client,s,h).status_code==403
    verify(client,s,h);assert grant(client,s,h).status_code==200
    client.post(f"/demo-sessions/{s['session_id']}/consent",headers=h,json={'action':'revoke','scopes':[]})
    assert grant(client,s,h).status_code==403


def test_profile_change_invalidates_identity(client):
    s,h=new(client);verify(client,s,h)
    client.post(f"/demo-sessions/{s['session_id']}/consent",headers=h,json={'action':'select_profile','demo_customer_id':'DEMO-U02','scopes':[]})
    assert grant(client,s,h).status_code==403
    assert verify(client,s,h,'DEMO-U01').status_code==403


def desk(**kwargs):
    return {'model_id':'WD520VCT','drilling_needed':'yes','surface_material':'natural','pump_needed':'no','breaker_needed':'no',**kwargs}










def test_identity_change_blocked_during_active_chat(client):
    s,h=new(client)
    working=client.app.state.sessions.begin(s['session_id'])
    try: assert verify(client,s,h).status_code==409
    finally: client.app.state.sessions.finish(s['session_id'],None)


