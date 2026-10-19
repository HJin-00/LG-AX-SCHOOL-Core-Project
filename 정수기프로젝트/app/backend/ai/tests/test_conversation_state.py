import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ai.main import create_app,Settings

@pytest.fixture
def connected(tmp_path,monkeypatch):
 monkeypatch.setenv('CONSENT_BACKEND','sqlite');monkeypatch.setenv('CONSENT_DB',str(tmp_path/'consent.db'))
 async def runner(q,context):return {'reply':{'status':'answered','topic':'contract','answer':'확인','sources':[],'cards':[],'missing_fields':[]}}
 app=create_app(Settings(require_login=False,consent_db=tmp_path/'consent.db',brief_root=tmp_path),runner)
 with TestClient(app) as c:
  d=c.post('/demo-sessions',json={'demo_customer_id':'DEMO-U01'}).json();sid=d['session_id'];h={'X-Session-ID':sid,'X-Demo-Session-Key':d['session_key']}
  c.post('/demo-sessions/'+sid+'/identity',headers=h,json={'claimed_demo_customer_id':'DEMO-U01'})
  g=c.post('/demo-sessions/'+sid+'/consent',headers=h,json={'action':'grant','scopes':['contract_terms','contract_costs']}).json();h['X-Tool-Access-Token']=g['tool_access_token']
  yield c,app,sid,h

def test_reset_preserves_connection_and_clears_server_history(connected):
 c,app,sid,h=connected;c.post('/chat',headers=h,json={'session_id':sid,'message':'이전 비교 질문'})
 state={'messages':[{'role':'assistant','answer':'이전 답변'}],'activeTopic':'renewal'}
 assert c.post('/conversation/state',headers=h,json={'state':state}).status_code==200
 assert c.post('/conversation/reset',headers=h).status_code==200
 assert c.get('/conversation/current',headers=h).json()['state'] is None
 working=app.state.sessions.begin(sid)
 assert working.history==[] and working.context_input=={}
 app.state.sessions.finish(sid,None)
 assert c.get('/connection/current',headers=h).status_code==200

def test_snapshot_restores_only_after_owner_and_token_revalidation(connected):
 c,app,sid,h=connected;state={'messages':[{'role':'assistant','answer':'내 비교 결과'}],'activeTopic':'renewal','renewalContext':{'planned_start_date':'2026-12-01'}}
 assert c.post('/conversation/state',headers=h,json={'state':state}).status_code==200
 assert c.get('/conversation/current',headers=h).json()['state']==state
 assert c.get('/conversation/current',headers={'X-Session-ID':sid}).status_code==403
 assert c.get('/conversation/current',headers={**h,'X-Tool-Access-Token':'wrong-token'}).status_code==403
 c.post('/demo-sessions/'+sid+'/consent',headers=h,json={'action':'revoke','scopes':[]})
 assert c.get('/conversation/current',headers=h).status_code==403

def test_ui_state_does_not_modify_agent_history_or_allow_extra_storage(connected):
 c,app,sid,h=connected
 assert c.post('/conversation/state',headers=h,json={'state':{'messages':[],'activeTopic':'cancel'}}).status_code==200
 working=app.state.sessions.begin(sid);assert working.history==[];app.state.sessions.finish(sid,None)
 assert c.post('/conversation/state',headers=h,json={'state':{'messages':[],'access_token':'not-allowed'}}).status_code==422

def test_zoneinfo_fallback_without_system_timezone_database():
 import subprocess,os,sys
 env={**os.environ,'PYTHONTZPATH':''};env.pop('EVALUATION_REFERENCE_DATE',None)
 result=subprocess.run([sys.executable,'-c','from zoneinfo import ZoneInfo;from datetime import datetime;print(datetime.now(ZoneInfo("Asia/Seoul")).utcoffset())'],env=env,capture_output=True,text=True)
 assert result.returncode==0 and '9:00:00' in result.stdout


@pytest.mark.parametrize('message',[None,{'role':'assistant','cards':'broken'},{'role':'assistant','cards':[None]},{'role':'assistant','answer':{}}])
def test_rejects_corrupt_display_state(connected,message):
 c,app,sid,h=connected
 assert c.post('/conversation/state',headers=h,json={'state':{'messages':[message]}}).status_code==422
 assert c.get('/conversation/current',headers=h).json()['state'] is None

def test_revision_and_reset_epoch_reject_old_tab(connected):
 c,app,sid,h=connected
 state={'messages':[{'role':'assistant','answer':'current'}]}
 first=c.get('/conversation/current',headers=h).json()
 version={k:first[k] for k in ('revision','epoch')}
 saved=c.post('/conversation/state',headers=h,json={'state':state,**version})
 assert saved.status_code==200
 assert c.post('/conversation/state',headers=h,json={'state':{'messages':[]},**version}).status_code==409
 latest=saved.json()
 assert c.post('/conversation/reset',headers=h).status_code==200
 assert c.post('/conversation/state',headers=h,json={'state':state,'revision':latest['revision'],'epoch':latest['epoch']}).status_code==409
 assert c.get('/conversation/current',headers=h).json()['state'] is None


def test_invalid_nested_card_cannot_replace_good_snapshot(connected):
 c,app,sid,h=connected
 state={'messages':[{'role':'assistant','answer':'유효한 답변','next_actions':['compare_new']}]}
 saved=c.post('/conversation/state',headers=h,json={'state':state}).json()
 bad={'messages':[{'role':'assistant','cards':[{'type':'renewal_comparison','data':{}}]}]}
 assert c.post('/conversation/state',headers=h,json={'state':bad,'revision':saved['revision'],'epoch':saved['epoch']}).status_code==422
 assert c.get('/conversation/current',headers=h).json()['state']==state
