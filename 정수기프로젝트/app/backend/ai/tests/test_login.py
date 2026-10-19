import pytest
from fastapi.testclient import TestClient
from ai.main import create_app,Settings
from ai.login_store import LoginDenied

PASSWORD='OnlyFixture!12345'

@pytest.fixture
def client(tmp_path,monkeypatch):
    path=tmp_path/'login.db';monkeypatch.setenv('CONSENT_BACKEND','sqlite');monkeypatch.setenv('CONSENT_DB',str(path))
    async def runner(message,context):return {'reply':{'status':'answered','topic':'unknown','answer':'일반 안내','sources':[],'cards':[],'missing_fields':[]}}
    c=TestClient(create_app(Settings(consent_db=path,brief_root=tmp_path/'briefs'),agent_runner=runner))
    c.app.state.logins.seed('user1',PASSWORD,'DEMO-U01');c.app.state.logins.seed('user2',PASSWORD,'DEMO-U02')
    return c


def login(client,user='user1',password=PASSWORD):return client.post('/auth/login',json={'username':user,'password':password})


def test_guest_general_and_private_requires_login(client):
    assert client.get('/auth/me').json()['account'] is None
    g=client.post('/guest-sessions').json()
    assert client.post('/chat',json={'session_id':g['session_id'],'message':'정수기 기능이 궁금해요'}).status_code==200
    assert client.post('/demo-sessions',json={'demo_customer_id':'DEMO-U01'}).status_code==401
    assert client.get('/demo-profiles').status_code==401


def test_login_cookie_persistence_and_hash_storage(client):
    r=login(client);assert r.status_code==200
    cookie=r.headers['set-cookie'];assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie
    assert 'token' not in r.json() and r.json()['account']['demo_customer_id']=='DEMO-U01'
    assert client.get('/auth/me').json()['account']['display_name']=='이서연'
    with client.app.state.consents.connect() as db:
        row=db.execute('SELECT salt,password_hash FROM demo_accounts WHERE username=?',('user1',)).fetchone()
        assert PASSWORD not in str(row) and len(row[1])==64
    # API 인스턴스가 바뀌어도 DB 로그인 세션을 확인
    new_app=create_app(client.app.state.settings)
    assert new_app.state.logins.account(client.cookies.get('water_login'))['username']=='user1'


@pytest.mark.parametrize('user,password',[('user1','wrong'),('unknown',PASSWORD)])
def test_invalid_credentials_same_error(client,user,password):
    assert login(client,user,password).json()['code']=='LOGIN_FAILED'
    assert client.get('/auth/me').json()['account'] is None


def test_rate_limit(client):
    for _ in range(5):assert login(client,password='wrong').status_code==401
    assert login(client).status_code==429


def test_other_account_contract_denied(client):
    login(client)
    assert client.post('/demo-sessions',json={'demo_customer_id':'DEMO-U02'}).status_code==403
    s=client.post('/demo-sessions',json={'demo_customer_id':'DEMO-U01'}).json()
    h={'X-Demo-Session-Key':s['session_key']}
    assert client.post(f"/demo-sessions/{s['session_id']}/identity",headers=h,json={'claimed_demo_customer_id':'DEMO-U01'}).status_code==200
    assert client.post(f"/demo-sessions/{s['session_id']}/consent",headers=h,json={'action':'grant','scopes':['contract_terms']}).status_code==200
    login(client,'user2')
    assert client.get('/contracts/current',headers={**h,'X-Session-ID':s['session_id']}).status_code==403


def test_logout_invalidates_cookie_and_personal_access(client):
    login(client);s=client.post('/demo-sessions',json={'demo_customer_id':'DEMO-U01'}).json();h={'X-Demo-Session-Key':s['session_key']}
    client.post(f"/demo-sessions/{s['session_id']}/identity",headers=h,json={'claimed_demo_customer_id':'DEMO-U01'})
    g=client.post(f"/demo-sessions/{s['session_id']}/consent",headers=h,json={'action':'grant','scopes':['contract_terms']}).json()
    token=client.cookies.get('water_login');assert client.post('/auth/logout',json={}).status_code==200
    assert client.get('/auth/me').json()['account'] is None
    assert client.get('/contracts/current',headers={**h,'X-Session-ID':s['session_id'],'X-Tool-Access-Token':g['tool_access_token']}).status_code==401
    with pytest.raises(LoginDenied):client.app.state.logins.account(token)


def test_origin_forgery_and_expiry(client):
    assert client.post('/auth/login',headers={'Origin':'https://evil.example'},json={'username':'user1','password':PASSWORD}).status_code==403
    login(client);client.app.state.logins.clock=lambda:10**12
    assert client.get('/auth/me').json()['account'] is None


def test_duplicate_seed_not_overwritten(client):
    with pytest.raises(ValueError):client.app.state.logins.seed('user1','ChangedPassword!123','DEMO-U02')
    assert login(client).status_code==200


def test_four_fixture_accounts_and_short_password_exception(client):
    store=client.app.state.logins;store.seed_fixture_accounts()
    for n in range(1,5):
        token=store.login(f'test{n}','1234')
        assert store.account(token)['demo_customer_id']==f'DEMO-U0{n}'
        store.logout(token)
    token=store.login('test1','1234');store.seed_fixture_accounts()
    with pytest.raises(LoginDenied):store.account(token)
    with pytest.raises(ValueError):store.seed('ordinary','1234','DEMO-U01')
    assert login(client).status_code==200
