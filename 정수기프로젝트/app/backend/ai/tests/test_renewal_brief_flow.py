from io import BytesIO
from pypdf import PdfReader
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from ai.main import create_app,Settings
from 정수기프로젝트.app.mcp import tools
from 정수기프로젝트.app.mcp.client_adapter import call_tool
from 정수기프로젝트.app.agent.langchain_agent import verified_result


@pytest.fixture
def connected(tmp_path,monkeypatch):
    path=tmp_path/'auth.db';root=tmp_path/'briefs';monkeypatch.setenv('EVALUATION_REFERENCE_DATE','2026-10-14')
    monkeypatch.setenv('CONSENT_BACKEND','sqlite');monkeypatch.setenv('CONSENT_DB',str(path));monkeypatch.setattr(tools,'BRIEF_ROOT',root)
    async def runner(message,context):
        tool='create_renewal_brief' if '준비서' in message else 'compare_retention_renewal'
        result=await call_tool(tool,{'offer_id':'DEMO-NEW-01','comparison_date':'2026-10-06','comparison_months':36},trusted_authorization=context['tool_authorization'])
        raw={'reply':{'status':'answered','topic':'contract','answer':'모델 임의 답변','sources':[],'cards':[],'missing_fields':[]}}
        return verified_result(raw,[result])
    client=TestClient(create_app(Settings(consent_db=path,brief_root=root),agent_runner=runner))
    client.app.state.logins.seed('fixture','LongFixture!123')
    client.post('/auth/login',json={'username':'fixture','password':'LongFixture!123'})
    s=client.post('/demo-sessions',json={'demo_customer_id':'DEMO-U01'}).json()
    headers={'X-Demo-Session-Key':s['session_key'],'X-Session-ID':s['session_id']}
    client.post(f"/demo-sessions/{s['session_id']}/identity",headers=headers,json={'claimed_demo_customer_id':'DEMO-U01'})
    g=client.post(f"/demo-sessions/{s['session_id']}/consent",headers=headers,json={'action':'grant','scopes':['contract_terms','contract_costs']}).json()
    headers['X-Tool-Access-Token']=g['tool_access_token']
    return client,s,headers


def test_compare_card_then_registered_brief_download(connected):
    c,s,h=connected
    result=c.post('/chat',headers=h,json={'session_id':s['session_id'],'message':'유지 재구독 비교'}).json()
    assert result['cards'][0]['type']=='renewal_comparison'
    data=result['cards'][0]['data']
    assert data['difference']==358600 and data['options'][1]['estimated_total']==1086400
    assert data['decision']['lower_cost_choice']=='keep'
    assert data['assumptions']
    assert data['request']['offer_id']=='DEMO-NEW-01'
    assert data['request']['planned_start_date']=='2026-10-14'
    assert data['comparison_start']=='2026-10-14'
    created=c.post('/chat',headers=h,json={'session_id':s['session_id'],'message':'같은 비교 준비서'}).json()
    assert created['status']=='brief_created',created
    download=c.get('/briefs/'+created['brief_id'],headers=h)
    assert download.status_code==200
    assert download.headers['content-type']=='application/pdf'
    assert download.content.startswith(b'%PDF')
    text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(download.content)).pages)
    assert '1,086,400원' in text and '남는 계약/의무기간' in text
    assert s['session_key'] not in text and h['X-Tool-Access-Token'] not in text
    c.post('/auth/logout',json={})
    assert c.get('/briefs/'+created['brief_id'],headers=h).status_code==401


def test_registered_scenario_default_offer_without_date(connected):
    c,s,h=connected
    from 정수기프로젝트.app.mcp.subscription.renewal_comparison import compare_retention_renewal
    result=compare_retention_renewal(s['session_id'],h['X-Tool-Access-Token'],'','',36)
    assert result['status']=='ok' and result['difference']==358600
    assert result['renewal_options'][0]['missing_fields']==[]
    assert result['renewal_options'][1]['missing_fields']==[]
    assert result['renewal_options'][1]['offer_id']=='DEMO-NEW-01'
    assert result['assumptions']
