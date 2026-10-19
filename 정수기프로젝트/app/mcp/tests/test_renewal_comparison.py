from pypdf import PdfReader
import pytest
from 정수기프로젝트.app.consent import ConsentStore
from 정수기프로젝트.app.mcp.subscription.renewal_comparison import compare_retention_renewal

def test_official_discount_months_and_displayed_comparison_share_rates(auth):
    result=compare_retention_renewal(*auth,offer_id='LG-SNAPSHOT-WD723RH',comparison_date='2026-10-06',comparison_months=36,maintenance_monthly_fee=5000,planned_start_date='2026-11-01')
    option=result['renewal_options'][1]
    assert option['model_id']=='WD723RH'
    assert option['subscription_months']==36
    assert option['charge_items'][0]['amount']==24900
    assert option['charge_items'][11]['amount']==24900
    assert option['charge_items'][12]['amount']==49900
    assert option['subscription_scenario_cost']==12*24900+24*49900
    assert option['estimated_total'] is None
    assert option['scenario_total']==option['confirmed_subtotal']+option['subscription_scenario_cost']


@pytest.fixture
def auth(tmp_path,monkeypatch):
    monkeypatch.setenv('CONSENT_BACKEND','sqlite');monkeypatch.setenv('CONSENT_DB',str(tmp_path/'consent.db'));monkeypatch.setenv('EVALUATION_REFERENCE_DATE','2026-10-06')
    # 이 그룹은 일부 비용이 빠진 시나리오를 별도 fixture로 유지합니다.
    import csv
    from 정수기프로젝트.app.mcp.subscription import renewal_comparison, subscription_offers
    monkeypatch.setattr(renewal_comparison,'CONTEXT_PATH',tmp_path/'missing-context.csv')
    rows=list(csv.DictReader(subscription_offers.OFFER_PATH.open(encoding='utf-8-sig')))
    for row in rows:row['installation_fee']=''
    catalog=tmp_path/'offers.csv'
    with catalog.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    monkeypatch.setattr(subscription_offers,'OFFER_PATH',catalog)
    store=ConsentStore();s=store.create('DEMO-U01');g=store.event(s['session_id'],s['session_key'],'grant',['contract_terms','contract_costs'])
    return s['session_id'],g['tool_access_token']


def run(auth,**patch):
    kwargs=dict(offer_id='DEMO-NEW-01',planned_start_date='2028-09-01',comparison_date='2026-10-06',comparison_months=36,maintenance_monthly_fee=5000,installation_conditions={'drilling_needed':'yes','surface_material':'natural','pump_needed':'no','breaker_needed':'no'})
    kwargs.update(patch);return compare_retention_renewal(*auth,**kwargs)


def test_identical_horizon_and_unknown_base_installation(auth):
    r=run(auth);assert r['comparison_start']=='2026-10-06' and r['comparison_end']=='2029-10-05'
    assert r['renewal_start']=='2028-09-01'
    keep,new=r['renewal_options']
    assert keep['maintenance_months']==14 and keep['maintenance_cost']==70000
    assert new['subscription_cost']==12*24900+2*29900
    assert len(new['charge_items'])==14 and new['remaining_mandatory_months']==22
    assert new['estimated_total'] is None and 'installation_fee' in new['missing_fields']
    assert r['difference'] is None
    assert new['confirmed_subtotal']==r['common_current_contract_cost']+new['subscription_cost']+50000


def test_unknown_upkeep_is_not_free(auth):
    r=run(auth,maintenance_monthly_fee=None)
    assert r['renewal_options'][0]['estimated_total'] is None
    assert r['renewal_options'][0]['missing_fields']==['maintenance_monthly_fee']


def test_unconfirmed_work_no_total(auth):
    r=run(auth,installation_conditions={})
    assert r['renewal_options'][1]['installation']['estimated_additional_installation_fee'] is None
    assert 'pump_needed' in r['renewal_options'][1]['missing_fields']


@pytest.mark.parametrize('months',[0,121,True])
def test_invalid_period(auth,months):
    assert run(auth,comparison_months=months)['status']=='error'


def test_reference_and_short_horizon(auth):
    assert run(auth,comparison_date='2026-10-07')['missing_fields']==['billing_reference_date']
    assert run(auth,comparison_months=6)['missing_fields']==['comparison_months']


def test_unknown_offer_and_oversize_horizon(auth):
    assert run(auth,offer_id='UNKNOWN')['status']=='unverified'
    assert run(auth,comparison_months=120)['missing_fields']==['comparison_months']


def test_permission_and_customer_scope(auth):
    assert compare_retention_renewal('','',offer_id='DEMO-NEW-01',comparison_date='2026-10-06',comparison_months=36)['status']=='forbidden'


def test_protocol_and_verified_response(auth):
    import asyncio
    from 정수기프로젝트.app.mcp.client_adapter import call_tool,MCPToolError
    from 정수기프로젝트.app.agent.langchain_agent import verified_result
    async def go():
        result=await call_tool('compare_retention_renewal',{'offer_id':'DEMO-NEW-01','planned_start_date':'2028-09-01','comparison_date':'2026-10-06','comparison_months':36},trusted_authorization={'session_id':auth[0],'access_token':auth[1]})
        raw={'reply':{'status':'answered','topic':'contract','answer':'재구독이 더 저렴합니다','sources':[],'cards':[],'missing_fields':[]}}
        reply=verified_result(raw,[result]).reply
        assert '총액 미확정' in reply.answer and '더 저렴' not in reply.answer
        with pytest.raises(MCPToolError):
            await call_tool('compare_retention_renewal',{'session_id':'other'},trusted_authorization={'session_id':auth[0],'access_token':auth[1]})
    asyncio.run(go())


def test_brief_recomputes_and_is_owned(auth,tmp_path,monkeypatch):
    from 정수기프로젝트.app.mcp.subscription.renewal_comparison import create_renewal_brief
    from 정수기프로젝트.app.mcp import tools
    from 정수기프로젝트.app.agent.langchain_agent import verified_result
    monkeypatch.setattr(tools,'BRIEF_ROOT',tmp_path/'briefs')
    result=create_renewal_brief(*auth,offer_id='DEMO-NEW-01',comparison_date='2026-10-06',comparison_months=36)
    assert 'absolute_path' not in result
    store=ConsentStore();path=store.brief_path(result['brief_id'],auth[0],token=auth[1])
    assert path is not None
    from pathlib import Path
    body='\n'.join(page.extract_text() for page in PdfReader(path).pages)
    for text in ['기존 제품 유지','기존 계약 정산 후 재구독','총액: 미확정','비교 종료 후 남는 계약','기본 설치비']:
        assert text in body
    raw={'reply':{'status':'answered','topic':'contract','answer':'완료','sources':[],'cards':[],'missing_fields':[]}}
    reply=verified_result(raw,[result]).reply
    assert reply.status=='brief_created' and reply.brief_id==result['brief_id']
    assert reply.cards[0].type=='renewal_comparison'
    assert reply.cards[0].data.difference is None
    with store.connect() as db:db.execute('UPDATE sessions SET grant_hash=NULL WHERE id=?',(auth[0],))
    from 정수기프로젝트.app.consent import ConsentDenied
    with pytest.raises(ConsentDenied):store.brief_path(result['brief_id'],auth[0],token=auth[1])


def test_brief_invalid_request_never_writes(auth,tmp_path,monkeypatch):
    from 정수기프로젝트.app.mcp.subscription.renewal_comparison import create_renewal_brief
    from 정수기프로젝트.app.mcp import tools
    root=tmp_path/'no-files';monkeypatch.setattr(tools,'BRIEF_ROOT',root)
    assert create_renewal_brief('','',offer_id='DEMO-NEW-01',comparison_date='2026-10-06',comparison_months=36)['status']=='forbidden'
    assert create_renewal_brief(*auth,offer_id='UNKNOWN',comparison_date='2026-10-06',comparison_months=36)['status']=='unverified'
    assert not root.exists()


def test_renewal_card_refuses_false_difference(auth):
    from copy import deepcopy
    from ai.schemas import RenewalData
    from 정수기프로젝트.app.agent.langchain_agent import verified_result
    result=run(auth)
    raw={'reply':{'status':'answered','topic':'contract','answer':'임의 답변','sources':[],'cards':[],'missing_fields':[]}}
    card=verified_result(raw,[result]).reply.cards[0].data.model_dump()
    card['difference']=1
    with pytest.raises(ValueError):RenewalData.model_validate(card)
    card['difference']=None;card['options'][1]['estimated_total']=0
    with pytest.raises(ValueError):RenewalData.model_validate(card)


def test_omitted_reference_uses_verified_billing_date(auth):
    r=run(auth,comparison_date='')
    assert r['comparison_date']=='2026-10-06'
    assert r['comparison_request']['comparison_date']=='2026-10-06'


def test_consultation_offer_uses_tool_evidence_only(auth):
    from 정수기프로젝트.app.agent.langchain_agent import verified_result
    raw={'reply':{'status':'answered','topic':'contract','answer':'일반 설명','sources':[],'cards':[],'missing_fields':[], 'consultation_recommended':True,'consultation_reason':'모델 임의 제안'}}
    assert verified_result(raw,[]).reply.consultation_recommended is False
    result=verified_result(raw,[run(auth)]).reply
    assert result.consultation_recommended is True and result.consultation_reason!='모델 임의 제안'


def test_created_brief_does_not_repeat_offer(auth,tmp_path,monkeypatch):
    from 정수기프로젝트.app.mcp.subscription.renewal_comparison import create_renewal_brief
    from 정수기프로젝트.app.mcp import tools
    from 정수기프로젝트.app.agent.langchain_agent import verified_result
    monkeypatch.setattr(tools,'BRIEF_ROOT',tmp_path/'briefs')
    result=create_renewal_brief(*auth,offer_id='DEMO-NEW-01',comparison_date='2026-10-06',comparison_months=36)
    raw={'reply':{'status':'answered','topic':'contract','answer':'임의','sources':[],'cards':[],'missing_fields':[]}}
    reply=verified_result(raw,[result]).reply
    assert reply.status=='brief_created' and not reply.consultation_recommended


def test_nonnegative_unknown_cost_can_still_rank_choices(auth):
    r=run(auth,installation_conditions={})
    assert r['difference'] is None
    assert r['decision']['lower_cost_choice']=='keep'
    assert r['decision']['basis']=='nonnegative_missing_cost_bound'
    assert r['decision']['minimum_saving']==288600


def test_selected_model_and_mid_contract_transition_includes_exit(auth):
    r=run(auth,offer_id='DEMO-NEW-02',planned_start_date='2026-11-15',installation_conditions={'drilling_needed':'no','pump_needed':'no','breaker_needed':'no','outlet_needed':'no','external_outlet_drilling':'no','external_water_drilling':'no','thick_sink':'no'})
    assert r['renewal_start']=='2026-11-15'
    keep,new=r['renewal_options']
    assert new['model_id']=='WU923AWB' and new['product']['features']
    assert keep['model_id']=='WD520VCT'
    assert new['exit_cost_total']==70000
    assert new['charge_items'][0]['charge_date']=='2026-11-15'
    assert new['confirmed_subtotal']==new['existing_subscription_cost']+new['exit_cost_total']+new['subscription_cost']+new['initial_cost']+new['maintenance_cost']
    assert keep['confirmed_subtotal']==keep['existing_subscription_cost']+keep['arrears']+keep['maintenance_cost']


def test_transition_date_rejects_invalid_or_past(auth):
    for day in ['2026-02-30','2026-10-05']:
        r=run(auth,planned_start_date=day)
        assert r['status']=='needs_info' and r['missing_fields']==['planned_start_date']


def test_partial_horizon_does_not_bill_rest_of_kept_contract(auth):
    r=run(auth,planned_start_date='2026-11-01',comparison_months=12)
    keep,new=r['renewal_options']
    assert keep['maintenance_cost']==0
    assert keep['existing_subscription_cost']==12*29900
    assert new['subscription_cost']==12*24900
    assert new['remaining_contract_months']==48


def test_catalog_cards_preserve_models_rates_and_official_features():
    from 정수기프로젝트.app.mcp.subscription.subscription_offers import lookup_subscription_offers
    from 정수기프로젝트.app.agent.langchain_agent import verified_result
    r=lookup_subscription_offers(planned_start_date='2026-10-08')
    reply=verified_result({'reply':{'status':'answered','topic':'contract','answer':'후보','sources':[],'cards':[],'missing_fields':[]}},[r]).reply
    assert reply.cards[0].type=='renewal_catalog'
    assert len({o.model_id for o in reply.cards[0].data.offers})==36
    assert all(o.selection_reason and o.product.features and o.monthly_fee is not None and o.monthly_fee>0 for o in reply.cards[0].data.offers)


def test_followup_preferences_preserve_transition_and_offer():
    from 정수기프로젝트.app.agent.langchain_agent import comparison_preferences
    ctx={'history':[{'role':'user','content':'유지·재구독 비교 계속\n{"offer_id":"DEMO-NEW-02","comparison_months":36}'}],
         'turn_message':'유지·재구독 비교 계속\n{"planned_start_date":"2026-11-15","billing_reference_date":"2026-10-06"}'}
    p=comparison_preferences(ctx)
    assert p['offer_id']=='DEMO-NEW-02' and p['planned_start_date']=='2026-11-15' and p['comparison_date']=='2026-10-06'



def test_current_spoken_transition_overrides_prior_form():
    from 정수기프로젝트.app.agent.langchain_agent import comparison_preferences
    p=comparison_preferences({'history':[{'role':'user','content':'{"planned_start_date":"2028-09-01"}'}],'turn_message':'2026년 11월 15일에 새로 재구독하면? '})
    assert p['planned_start_date']=='2026-11-15'


def test_arrears_included_once_per_choice(auth,monkeypatch):
    from 정수기프로젝트.app.mcp.subscription import renewal_comparison
    original=renewal_comparison._load
    def load(*args):
        c,b,error=original(*args)
        if b:b={**b,'arrears':33000}
        return c,b,error
    monkeypatch.setattr(renewal_comparison,'_load',load)
    # compare_contract_options independently reads the same synthetic billing fixture.
    from 정수기프로젝트.app.mcp.contracts import contract_documents
    monkeypatch.setattr(contract_documents,'_load',load)
    r=run(auth,planned_start_date='2026-11-15')
    keep,new=r['renewal_options']
    assert keep['arrears']==33000
    assert new['exit_cost_total']==103000
    assert sum(i['amount'] for i in new['exit_cost_items'])==103000


def test_penalty_included_before_mandatory_end(auth,monkeypatch):
    monkeypatch.setenv('EVALUATION_REFERENCE_DATE','2026-08-30')
    from 정수기프로젝트.app.mcp.subscription import subscription_offers
    from datetime import date
    offers=subscription_offers.load_offers()
    monkeypatch.setattr(subscription_offers,'load_offers',lambda:[o.model_copy(update={'available_from':date(2026,8,1)}) for o in offers])
    from 정수기프로젝트.app.mcp.subscription import renewal_comparison
    from 정수기프로젝트.app.mcp.contracts import contract_documents
    original=renewal_comparison._load
    def load(*args):
        c,b,error=original(*args)
        if b:b={**b,'as_of':'2026-08-30'}
        return c,b,error
    monkeypatch.setattr(renewal_comparison,'_load',load)
    monkeypatch.setattr(contract_documents,'_load',load)
    r=run(auth,comparison_date='2026-08-30',planned_start_date='2026-08-31')
    assert 'renewal_options' in r,r
    assert r['renewal_options'][1]['exit_cost_total']==170000


def test_explicit_transition_brief_keeps_chosen_model_and_date(auth,tmp_path,monkeypatch):
    from 정수기프로젝트.app.mcp.subscription.renewal_comparison import create_renewal_brief
    from 정수기프로젝트.app.mcp import tools
    monkeypatch.setattr(tools,'BRIEF_ROOT',tmp_path/'briefs')
    result=create_renewal_brief(*auth,offer_id='DEMO-NEW-02',comparison_date='',comparison_months=36,planned_start_date='2026-11-15')
    path=ConsentStore().brief_path(result['brief_id'],auth[0],token=auth[1])
    text='\n'.join(page.extract_text() for page in PdfReader(path).pages)
    assert '2026-11-15' in text and 'WU923AWB' in text and '기존 계약 해지 비용: 70,000원' in text


def test_protocol_accepts_declared_transition_date(auth):
    import asyncio
    from 정수기프로젝트.app.mcp.client_adapter import call_tool
    r=asyncio.run(call_tool('compare_retention_renewal',{'offer_id':'DEMO-NEW-01','comparison_date':'2026-10-06','comparison_months':36,'planned_start_date':'2026-11-15'},trusted_authorization={'session_id':auth[0],'access_token':auth[1]}))
    assert r['renewal_start']=='2026-11-15'


def test_every_available_model_has_rates_and_comparison(auth):
    from 정수기프로젝트.app.mcp.subscription.subscription_offers import lookup_subscription_offers
    offers=lookup_subscription_offers(planned_start_date='2026-11-01')['offers']
    assert offers
    models=set()
    for offer in offers:
        models.add(offer['model_id'])
        assert offer['rates'],offer['model_id']
        result=compare_retention_renewal(*auth,offer_id=offer['offer_id'],comparison_date='2026-10-06',comparison_months=36,maintenance_monthly_fee=5000,planned_start_date='2026-11-01')
        assert result['status'] in {'ok','unverified'},(offer['model_id'],result)
        option=result['renewal_options'][1]
        total=option['subscription_cost'] if option['subscription_cost'] is not None else option['subscription_scenario_cost']
        assert total==sum(row['amount'] for row in option['charge_items'])
        assert total>0
        assert option['rate_segments']==offer['rates']
    assert len(models)>=6


def test_selected_card_mcp_comparison_and_pdf_share_same_conditions(auth,tmp_path,monkeypatch):
    import asyncio
    from 정수기프로젝트.app.mcp.client_adapter import call_tool
    from 정수기프로젝트.app.mcp import tools
    monkeypatch.setattr(tools,'BRIEF_ROOT',tmp_path/'briefs')
    args={'offer_id':'LG-SNAPSHOT-WD723RH','comparison_date':'2026-10-06','comparison_months':36,'planned_start_date':'2026-11-01','card_id':'kb','card_spend':800000,'card_eligibility':'promotion','card_application_date':'2026-10-14'}
    authorization={'session_id':auth[0],'access_token':auth[1]}
    result=asyncio.run(call_tool('compare_retention_renewal',args,trusted_authorization=authorization))
    option=result['renewal_options'][1]
    assert option['selected_card_benefit']['card_id']=='kb'
    assert option['selected_card_benefit']['monthly_items'][0]['card_discount']==20000
    assert result['comparison_request']['card_spend']==800000
    brief=asyncio.run(call_tool('create_renewal_brief',args,trusted_authorization=authorization))
    path=ConsentStore().brief_path(brief['brief_id'],auth[0],token=auth[1])
    text='\n'.join(page.extract_text() for page in PdfReader(path).pages)
    assert '인정실적 800,000원' in text and '행사 추가 할인 조건 충족' in text
    assert f"{option['selected_card_scenario_total']:,}원" in text
    assert '2026-11-01' in text and 'WD723RH' in text


def test_missing_transition_date_uses_today_and_full_calendar_horizon(auth,monkeypatch):
    monkeypatch.setenv('EVALUATION_REFERENCE_DATE','2026-10-14')
    result=run(auth,planned_start_date='')
    assert result['renewal_start']=='2026-10-14'
    assert result['comparison_start']=='2026-10-14' and result['comparison_end']=='2029-10-13'
    assert result['renewal_options'][1]['subscription_months']==36
    assert result['renewal_options'][1]['exit_cost_total']==70000
    # 월초 청구 가정: 마지막 부분 월의 10월 1일 관리비도 비교 범위 안에 포함된다.
    assert result['renewal_options'][0]['maintenance_months']==14


def test_changed_transition_date_keeps_today_horizon_and_customer_duration(auth,monkeypatch):
    monkeypatch.setenv('EVALUATION_REFERENCE_DATE','2026-10-14')
    result=run(auth,planned_start_date='2026-11-01',comparison_months=24)
    assert result['renewal_start']=='2026-11-01'
    assert result['comparison_start']=='2026-10-14' and result['comparison_end']=='2028-10-13'
    assert result['comparison_request']['comparison_months']==24
    assert result['renewal_options'][1]['subscription_months']==24
    assert run(auth,planned_start_date='2026-10-13')['missing_fields']==['planned_start_date']
