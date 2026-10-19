import asyncio
from 정수기프로젝트.app.agent.consultation_policy import consultation_reason,FINANCIAL_TOOLS
from 정수기프로젝트.app.agent.langchain_agent import make_tools


def test_reason_and_followup_preservation():
    assert consultation_reason({'turn_message':'방문관리가 자꾸 늦어서 바꿀까 고민돼요'})=='service_dispute'
    assert consultation_reason({'turn_message':'계약이 끝나면 위약금 면제야?'})=='unspecified'
    assert consultation_reason({'turn_message':'개인 사정으로 2026-11-15에 해지'})=='personal'
    assert consultation_reason({'turn_message':'얼음 기능이 필요해서 교체'})=='feature_upgrade'
    assert consultation_reason({'turn_message':'고장이라 바꾸고 싶어'})=='needs_reason'
    assert consultation_reason({'history':[{'role':'user','content':'고장이 계속 반복돼'}],'turn_message':'2026-11-15로 계산해줘'})=='service_dispute'
    assert consultation_reason({'history':[{'role':'user','content':'관리가 늦어'}],'turn_message':'문제가 해결됐고 얼음 기능이 필요해'})=='feature_upgrade'


def test_dispute_financial_execution_is_rejected_after_selection():
    tools=asyncio.run(make_tools({'turn_message':'방문관리가 늦어서 해지 비용을 2026-11-15 기준으로 알려줘'},[]))
    names={t.name for t in tools}
    assert names&FINANCIAL_TOOLS
    selected=next(t for t in tools if t.name=='assess_contract_document_costs')
    value=asyncio.run(selected.ainvoke({'exit_date':'2026-11-15'}))
    assert value['missing_fields']==['service_history']
    assert {'lookup_contract_document','get_official_channel','search_contract_knowledge'}<=names
    normal=asyncio.run(make_tools({'turn_message':'개인 사정으로 2026-11-15에 해지'},[]))
    assert 'assess_contract_document_costs' in {t.name for t in normal}


def test_cost_brief_cannot_bypass_dispute_gate():
    observations=[]
    tools=asyncio.run(make_tools({'turn_message':'수리가 반복돼 준비서 만들어줘','brief_creation_allowed':True},observations))
    brief=next(t for t in tools if t.name=='create_contract_document_brief')
    result=asyncio.run(brief.ainvoke({'exit_date':'2026-11-15'}))
    assert result['status']=='needs_info' and result['missing_fields']==['service_history']
    assert len(observations)==1



def test_reason_reply_does_not_repeat_history_question():
    from 정수기프로젝트.app.agent.consultation_policy import reason_response_override
    ctx={'history':[{'role':'user','content':'관리가 늦어서 해지 비용이 궁금해'}], 'turn_message':'입력\n{"service_history":"4개월 주기, 9월 요청 후 두 번 방문 취소"}'}
    assert consultation_reason(ctx)=='service_dispute'
    # Follow-up history itself is allowed to reach the LLM; a later cost question uses the provided record.
    ctx['history'].append({'role':'user','content':ctx['turn_message']});ctx['turn_message']='그럼 위약금은?'
    assert reason_response_override(ctx)['status']=='answered'
    assert reason_response_override({'turn_message':'A/S가 지연됐는데 위약금 면제야?'})['missing_fields']==['service_history']






def test_reason_click_continues_with_required_history():
    from 정수기프로젝트.app.agent.consultation_policy import reason_response_override
    ctx={'history':[{'role':'user','content':'다른 정수기로 바꾸려는데 고민돼요'}],'turn_message':'이전 상담의 추가 입력입니다.\n{"exit_reason":"service_dispute"}'}
    assert reason_response_override(ctx)['missing_fields']==['service_history']
    ctx['turn_message']='이력을 제공했습니다.\n{"service_history":"방문 2회 취소"}'
    ctx['history'].append({'role':'user','content':'{"exit_reason":"service_dispute"}'})
    assert reason_response_override(ctx)['status']=='answered'


