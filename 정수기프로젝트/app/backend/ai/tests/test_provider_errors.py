from fastapi.testclient import TestClient
from ai.main import create_app,Settings
from ai.agent_adapter import ModelProviderFailure
from 정수기프로젝트.app.agent.langchain_agent import provider_failure

class ProviderException(Exception):
    def __init__(self,body=None,status=None):self.body=body;self.status_code=status


def test_nested_credit_error_has_safe_message():
    inner=ProviderException({'error':{'message':'Your credit balance is too low to access the Anthropic API. private-fixture-value'}},400)
    outer=RuntimeError('wrapped');outer.__context__=inner
    result=provider_failure(outer)
    assert result.code=='MODEL_CREDIT_EXHAUSTED'
    assert 'private-fixture-value' not in str(result)
    assert provider_failure(ValueError('bad tool data')) is None
    assert provider_failure(ProviderException(status=401)).code=='MODEL_AUTH_FAILED'
    assert provider_failure(ProviderException(status=429)).code=='MODEL_RATE_LIMIT'
    result=provider_failure(ProviderException({'error':{'code':'credit_balance_exhausted','type':'insufficient_quota'}},429))
    assert result.code=='MODEL_CREDIT_EXHAUSTED'


def test_model_credit_not_reported_as_tool_failure(tmp_path,monkeypatch):
    monkeypatch.setenv('CONSENT_BACKEND','sqlite');monkeypatch.setenv('CONSENT_DB',str(tmp_path/'db'))
    async def runner(message,context):raise ModelProviderFailure('MODEL_CREDIT_EXHAUSTED','모델 잔액을 확인해 주세요.')
    c=TestClient(create_app(Settings(consent_db=tmp_path/'db',brief_root=tmp_path/'briefs'),agent_runner=runner))
    s=c.post('/guest-sessions').json()
    r=c.post('/chat',json={'session_id':s['session_id'],'message':'비교'})
    assert r.status_code==503
    assert r.json()['error']['code']=='MODEL_CREDIT_EXHAUSTED'
    assert '도구 실행' not in r.json()['answer']
    assert r.json()['error']['retryable'] is False
