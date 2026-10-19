import pytest
from 정수기프로젝트.app.mcp.subscription.subscription_offers import lookup_subscription_offers
from 정수기프로젝트.app.mcp.support.service_tools import recommend_water_purifier
from 정수기프로젝트.app.mcp.subscription.renewal_comparison import compare_retention_renewal
from 정수기프로젝트.app.consent import ConsentStore
from 정수기프로젝트.app.agent.langchain_agent import verified_result
MODELS={'WD520VCT','WU923AWB','WD721RH','WD722RH','WD723RH','WD724RH'}

def test_demo_catalog_covers_all_ready_models(monkeypatch):
    monkeypatch.setenv('CATALOG_SCOPE','comparison_ready')
    result=lookup_subscription_offers()
    from 정수기프로젝트.app.mcp.subscription.subscription_offers import demo_catalog_model_ids
    assert {o['model_id'] for o in result['offers']}==demo_catalog_model_ids()
    assert {'WD221MHB','WD520AWB','WD524VHMT'}.issubset(demo_catalog_model_ids())
    assert all(o['rates'] and o['contract_months'] for o in result['offers'])
    recommendation=recommend_water_purifier()
    assert len(recommendation['products'])>=6
    assert {p['model_id'] for p in recommendation['products']}.issubset(demo_catalog_model_ids())
    raw={'reply':{'status':'answered','topic':'purchase','answer':'추천','sources':[],'cards':[],'missing_fields':[]}}
    assert all(c.data.comparison_supported for c in verified_result(raw,[recommendation]).reply.cards)

@pytest.mark.parametrize('model',sorted(MODELS))
def test_demo_catalog_selection_can_render_comparison(model,monkeypatch,tmp_path):
    monkeypatch.setenv('CATALOG_SCOPE','comparison_ready')
    monkeypatch.setenv('CONSENT_BACKEND','sqlite')
    monkeypatch.setenv('CONSENT_DB',str(tmp_path/'sessions.db'))
    store=ConsentStore();session=store.create('DEMO-U01')
    grant=store.event(session['session_id'],session['session_key'],'grant',['contract_terms','contract_costs'])
    offer=next(o for o in lookup_subscription_offers()['offers'] if o['model_id']==model)
    result=compare_retention_renewal(session['session_id'],grant['tool_access_token'],offer['offer_id'],'',36)
    assert result['status'] in {'ok','unverified'}
    raw={'reply':{'status':'answered','topic':'contract','answer':'비교','sources':[],'cards':[],'missing_fields':[]}}
    response=verified_result(raw,[result]).reply
    assert response.cards[0].type=='renewal_comparison'
    assert response.cards[0].data.options[1].model_id==model
    if offer['source_kind']=='official':
        assert response.cards[0].data.options[1].estimated_total is None
        assert response.cards[0].data.options[1].scenario_total is not None
