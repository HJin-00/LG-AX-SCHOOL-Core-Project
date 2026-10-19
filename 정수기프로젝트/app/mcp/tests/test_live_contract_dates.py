import pytest
from 정수기프로젝트.app.mcp.contracts.contract_pdf import load_contract
from 정수기프로젝트.app.consent import ConsentStore
from 정수기프로젝트.app.mcp.subscription.renewal_comparison import compare_retention_renewal

@pytest.mark.parametrize('customer,end',[('DEMO-U01','2026-11-30'),('DEMO-U02','2026-12-31'),('DEMO-U04','2028-10-31')])
def test_runtime_contract_dates_match_cases(customer,end):
    c=load_contract(customer)
    assert c['contract_end']==end
    assert c['contract_start']<=c['mandatory_end']<=c['contract_end']

def test_near_contract_uses_full_renewal_period(tmp_path,monkeypatch):
    monkeypatch.setenv('EVALUATION_REFERENCE_DATE','2026-10-14')
    monkeypatch.setenv('CONSENT_BACKEND','sqlite');monkeypatch.setenv('CONSENT_DB',str(tmp_path/'scope.db'))
    store=ConsentStore();s=store.create('DEMO-U01');g=store.event(s['session_id'],s['session_key'],'grant',['contract_terms','contract_costs'])
    r=compare_retention_renewal(s['session_id'],g['tool_access_token'],'LG-SNAPSHOT-WD723RH','',36)
    assert r['renewal_start']=='2026-10-14'
    assert r['renewal_options'][1]['subscription_months']==36
    assert r['renewal_options'][1]['subscription_scenario_cost']==12*24900+24*49900
    from 정수기프로젝트.app.agent.langchain_agent import verified_result
    rendered=verified_result({'reply':{'status':'answered','topic':'contract','answer':'비교','sources':[],'cards':[],'missing_fields':[]}},[r])
    assert rendered.reply.cards[0].data.options[1].subscription_months==36
    assert rendered.reply.cards[0].data.options[1].rate_segments[0].end_month==12
