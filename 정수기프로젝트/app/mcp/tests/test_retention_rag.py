import pytest
from 정수기프로젝트.app.rag.retriever import search_contract_knowledge
from 정수기프로젝트.app.agent.langchain_agent import verified_result


def raw():return {'reply':{'status':'answered','topic':'contract','answer':'혜택 적용 가능','cards':[],'sources':[],'missing_fields':[]}}


def test_switch_benefit_constraints_and_no_cash_assumption(monkeypatch):
    monkeypatch.setenv('EVALUATION_REFERENCE_DATE','2026-10-08')
    result=search_contract_knowledge('정수기 교체보상 10만 포인트 혜택',limit=1)
    assert result['documents'][0]['chunk_id']=='LG-SWITCH-conditions'
    chunk=result['documents'][0]
    assert chunk['valid_until']=='2026-10-31' and len(chunk['eligible_models'])==6
    reply=verified_result(raw(),[result]).reply
    for text in ['폐가전','12월','선착순','복지몰','차감하지','확인되지']:assert text in reply.answer
    assert reply.sources[0].document_id=='LG-SWITCH-202610'


@pytest.mark.parametrize('day,phrase',[('2026-11-01','신청기간 종료'),('2026-09-30','신청기간 시작 전')])
def test_inactive_campaign_remains_inactive_after_response_guard(monkeypatch,day,phrase):
    monkeypatch.setenv('EVALUATION_REFERENCE_DATE',day)
    result=search_contract_knowledge('교체보상 멤버십 포인트',limit=1)
    assert phrase in result['documents'][0]['content']
    reply=verified_result(raw(),[result]).reply
    assert phrase in reply.answer
    assert '현재 혜택' in reply.answer or '즉시 적용' in reply.answer


def test_device_exchange_is_not_automatically_new_contract(monkeypatch):
    monkeypatch.setenv('EVALUATION_REFERENCE_DATE','2026-10-08')
    result=search_contract_knowledge('교체계약 새계약 계약변동',limit=1)
    assert result['documents'][0]['chunk_id']=='KCA-WATER-switch-checklist'
    reply=verified_result(raw(),[result]).reply
    assert '단순 수리·기기 교환·신규 구독' in reply.answer and '면제' in reply.answer



def test_benefit_is_retained_with_cost_cards_without_changing_amount(monkeypatch,tmp_path):
    from 정수기프로젝트.app.consent import ConsentStore
    from 정수기프로젝트.app.mcp.subscription.renewal_comparison import compare_retention_renewal
    monkeypatch.setenv('CONSENT_BACKEND','sqlite');monkeypatch.setenv('CONSENT_DB',str(tmp_path/'consent.db'))
    monkeypatch.setenv('EVALUATION_REFERENCE_DATE','2026-10-08')
    store=ConsentStore();s=store.create('DEMO-U01');g=store.event(s['session_id'],s['session_key'],'grant',['contract_terms','contract_costs'])
    cost=compare_retention_renewal(s['session_id'],g['tool_access_token'],'DEMO-NEW-01','',36)
    knowledge=search_contract_knowledge('교체보상 포인트',limit=1)
    reply=verified_result(raw(),[knowledge,cost]).reply
    assert reply.cards[0].type=='renewal_comparison'
    assert reply.cards[0].data.options[1].estimated_total==1086400
    assert '차감하지' in reply.benefit_guidance
    assert any(s.document_id=='LG-SWITCH-202610' for s in reply.sources)
    assert verified_result(raw(),[cost]).reply.benefit_guidance is None
