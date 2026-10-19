from pypdf import PdfReader
import asyncio
import json
import pytest











def test_old_error_ui_marker_does_not_block_contract_switch():
    from 정수기프로젝트.app.agent.langchain_agent import make_tools
    specs=asyncio.run(make_tools({'turn_message':'[상담 주제: 사용 오류]\n내 계약기간 알려줘'},[]))
    assert 'lookup_contract_document' in {t.name for t in specs}


def test_previous_switch_reason_does_not_overwrite_period_question(context):
    model=ToolModel(responses=[AIMessage(content='',tool_calls=[{'id':'lookup','name':'lookup_contract_document','args':{}}]),AIMessage(content='',tool_calls=[{'id':'out','name':'ModelDecision','args':reply()['reply']}])])
    result=asyncio.run(build_runner(model)('내 계약기간 알려줘',{**context,'history':[{'role':'user','content':'다른 정수기로 바꾸려고 하는데 고민돼요'}]}))
    assert result.reply.resolved_topic=='contract'
    assert result.reply.answer=='모델 초안'  # 기간 도구가 모델의 질문별 설명을 덮어쓰지 않음
    assert result.reply.missing_fields==[]



def test_searched_policy_is_not_overwritten_by_period_lookup(context):
    from 정수기프로젝트.app.mcp.client_adapter import call_tool
    from 정수기프로젝트.app.rag.retriever import search_contract_knowledge
    terms=asyncio.run(call_tool('lookup_contract_document',{},trusted_authorization=context['tool_authorization']))
    draft=reply();draft['reply']['answer']='계약 종료 후 케어십 방문관리는 별도 가입 조건을 확인해야 합니다.'
    result=verified_result(draft,[terms,search_contract_knowledge('계약 종료 후 케어십 방문관리')],prefer_knowledge=True)
    assert '케어십' in result.reply.answer
    assert result.reply.sources

def test_repeated_lookup_without_final_explanation_is_not_answered(context):
    model=ToolModel(responses=[AIMessage(content='',tool_calls=[{'id':'loop','name':'lookup_contract_document','args':{}}])])
    with pytest.raises(ToolFailure):asyncio.run(build_runner(model)('내 계약기간 알려줘',context))


def test_repeated_search_without_evidence_cannot_claim_success(monkeypatch):
    from 정수기프로젝트.app.mcp import client_adapter
    async def empty(*args,**kwargs):return {'status':'unverified','documents':[]}
    monkeypatch.setattr(client_adapter,'call_tool',empty)
    model=ToolModel(responses=[AIMessage(content='',tool_calls=[{'id':'loop','name':'search_contract_knowledge','args':{'query':'없는 문서'}}])])
    with pytest.raises(ToolFailure):asyncio.run(build_runner(model)('없는 문서 검색해줘',{}))


def test_explicit_service_reason_still_requests_service_history(context):
    model=ToolModel(responses=[AIMessage(content='',tool_calls=[{'id':'care','name':'lookup_care_guidance','args':{}}]),AIMessage(content='',tool_calls=[{'id':'out','name':'ModelDecision','args':{'status':'answered','topic':'care_subscription','answer':'관리 안내','missing_fields':[]}}])])
    result=asyncio.run(build_runner(model)('변경 이유는 관리 미이행·수리 지연·반복 고장입니다. 필요한 이력을 확인해줘.\n{"exit_reason":"service_dispute"}',context))
    assert result.reply.missing_fields==['service_history']
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from 정수기프로젝트.app.consent import ConsentStore
from 정수기프로젝트.app.mcp import tools
from 정수기프로젝트.app.agent.langchain_agent import build_runner,verified_result
from ai.agent_adapter import ToolFailure,load_agent

# 아래 기존 검사는 업무 실행 그래프를 격리한다. 의미 판단은 별도 고정 계획 검사/실제 AI 반복 평가로 검증한다.
real_build_runner=build_runner
async def neutral_plan(question,history):return {'purpose':'other'}
def build_runner(model):return real_build_runner(model,plan_runner=neutral_plan)

class ToolModel(FakeMessagesListChatModel):
    def bind_tools(self,tools,**kwargs):return self

@pytest.fixture
def context(tmp_path,monkeypatch):
    monkeypatch.setenv('CONSENT_BACKEND','sqlite');monkeypatch.setenv('CONSENT_DB',str(tmp_path/'auth.db'))
    monkeypatch.setenv('EVALUATION_REFERENCE_DATE','2026-10-06');monkeypatch.setattr(tools,'BRIEF_ROOT',tmp_path/'briefs')
    store=ConsentStore();s=store.create('DEMO-U01')
    g=store.event(s['session_id'],s['session_key'],'grant',['contract_terms','contract_costs'])
    return {'tool_authorization':{'session_id':s['session_id'],'access_token':g['tool_access_token']},'history':[]}

def reply(status='answered',**fields):
    return {'reply':{'status':status,'topic':'contract','answer':'모델 초안','sources':[],'cards':[],'missing_fields':[],**fields}}


def test_langchain_graph_calls_real_mcp_and_structured_output(context):
    model=ToolModel(responses=[AIMessage(content='',tool_calls=[{'id':'c1','name':'assess_contract_document_costs','args':{'exit_date':'2026-10-06'}}]),AIMessage(content='',tool_calls=[{'id':'out','name':'ModelDecision','args':reply()['reply']}])])
    result=asyncio.run(build_runner(model)('오늘 해지 비용은?',context))
    assert '70,000' in result.reply.answer
    assert result.reply.sources[0].document_id=='SYNTH-CONTRACT-V2'


def test_langchain_comparison_uses_calculated_totals(context):
    model=ToolModel(responses=[AIMessage(content='',tool_calls=[{'id':'c1','name':'compare_contract_options','args':{'exit_date_a':'2026-10-31','exit_date_b':'2026-11-01','comparison_date':'2026-10-06'}}]),AIMessage(content='',tool_calls=[{'id':'out','name':'ModelDecision','args':reply()['reply']}])])
    result=asyncio.run(build_runner(model)('2026-10-31과 2026-11-01 두 날짜 비교해줘',context))
    assert '99,900' in result.reply.answer and '29,900' in result.reply.answer
    assert result.reply.sources[0].document_id=='SYNTH-CONTRACT-V2'


def test_tool_authorization_not_in_model_schema_or_messages(context):
    from 정수기프로젝트.app.agent.langchain_agent import make_tools
    toolspecs=asyncio.run(make_tools(context,[]))
    text=json.dumps([t.args for t in toolspecs])
    assert 'access_token'not in text and 'session_id'not in text


def test_token_leak_rejected():
    with pytest.raises(ToolFailure):verified_result(reply(answer='secret-value'),[],'secret-value')


def test_fake_brief_completion_rejected():
    with pytest.raises(ToolFailure):verified_result(reply('brief_created',brief_id='a'*32),[])


def test_missing_key_returns_unavailable(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY',raising=False)
    assert load_agent('langchain') is None


def test_provider_settings_can_switch_without_code_change(monkeypatch):
    from 정수기프로젝트.app.agent.langchain_agent import model_settings
    monkeypatch.delenv('LLM_MODEL',raising=False)
    monkeypatch.setenv('LLM_PROVIDER','openai');monkeypatch.setenv('OPENAI_MODEL','gpt-4.1-mini')
    assert model_settings()==('openai','gpt-4.1-mini','OPENAI_API_KEY')
    monkeypatch.setenv('LLM_PROVIDER','anthropic');monkeypatch.setenv('ANTHROPIC_MODEL','claude-haiku-4-5-20251001')
    assert model_settings()==('anthropic','claude-haiku-4-5-20251001','ANTHROPIC_API_KEY')


def test_openai_missing_key_never_uses_anthropic(monkeypatch):
    from 정수기프로젝트.app.agent.langchain_agent import configured_runner
    monkeypatch.setenv('LLM_PROVIDER','openai');monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.setenv('ANTHROPIC_API_KEY','not-a-real-key')
    assert configured_runner()is None


def test_openai_factory_configuration(monkeypatch):
    from 정수기프로젝트.app.agent.langchain_agent import configured_runner
    import langchain.chat_models
    seen={}
    def fake(model,**kwargs):seen.update(model=model,**kwargs);return object()
    monkeypatch.setenv('LLM_PROVIDER','openai');monkeypatch.setenv('OPENAI_API_KEY','not-a-real-key')
    monkeypatch.delenv('LLM_MODEL',raising=False);monkeypatch.setenv('OPENAI_MODEL','gpt-4.1-mini')
    monkeypatch.setattr(langchain.chat_models,'init_chat_model',fake)
    assert configured_runner()is not None
    assert seen['model_provider']=='openai' and seen['store'] is False


def test_v2_brief_content_and_ownership(context):
    from 정수기프로젝트.app.mcp.contracts.contract_documents import create_contract_document_brief
    auth=context['tool_authorization']
    r=create_contract_document_brief(**auth,exit_date='2026-10-31')
    assert r['status']=='ok'
    p=ConsentStore().brief_path(r['brief_id'],auth['session_id'],token=auth['access_token'])
    text='\n'.join(page.extract_text() for page in PdfReader(p).pages)
    assert 'SYNTH-CONTRACT-V2' in text and '70,000원' in text


def test_fastapi_accepts_moved_agent_response(context,tmp_path):
    from fastapi.testclient import TestClient
    from ai.main import create_app,Settings
    from ai.schemas import AgentResult,AgentReply
    async def runner(message,ctx):
        # 이동한 실행부의 응답 타입이 FastAPI와 동일해야 함.
        return verified_result({'reply':{'status':'answered','topic':'contract','answer':'일반 안내','sources':[],'cards':[],'missing_fields':[]}},[])
    client=TestClient(create_app(Settings(require_login=False,consent_db=tmp_path/'api.db',brief_root=tmp_path/'briefs'),agent_runner=runner))
    r=client.post('/chat',json={'session_id':'moved-agent-test','message':'기간 차이'})
    assert r.status_code==200 and r.json()['status']=='answered'


def test_comparison_brief_contains_both_dates_and_extra_fee(context):
    from 정수기프로젝트.app.mcp.contracts.contract_documents import create_contract_document_brief
    auth=context['tool_authorization']
    r=create_contract_document_brief(**auth,exit_date_a='2026-10-31',exit_date_b='2026-11-01',comparison_date='2026-10-06')
    assert r['status']=='ok'
    body='\n'.join(page.extract_text() for page in PdfReader(ConsentStore().brief_path(r['brief_id'],auth['session_id'],token=auth['access_token'])).pages)
    for value in ['2026-10-31','2026-11-01','99,900원','29,900원','SYNTH-CONTRACT-V2']:
        assert value in body


def test_comparison_brief_insufficient_scope(context):
    from 정수기프로젝트.app.mcp.contracts.contract_documents import create_contract_document_brief
    store=ConsentStore();s=store.create('DEMO-U01');g=store.event(s['session_id'],s['session_key'],'grant',['contract_terms'])
    r=create_contract_document_brief(s['session_id'],g['tool_access_token'],exit_date_a='2026-10-31',exit_date_b='2026-11-01',comparison_date='2026-10-06')
    assert r['code']=='CONSENT_SCOPE_REQUIRED'


def test_brief_rejects_mixed_scope(context):
    from 정수기프로젝트.app.mcp.contracts.contract_documents import create_contract_document_brief
    r=create_contract_document_brief(**context['tool_authorization'],exit_date='2026-10-31',exit_date_a='2026-10-31')
    assert r['status']=='needs_info'


def test_mcp_comparison_brief_uses_server_auth(context):
    from 정수기프로젝트.app.mcp.client_adapter import call_tool
    r=asyncio.run(call_tool('create_contract_document_brief',{'exit_date_a':'2026-10-31','exit_date_b':'2026-11-01','comparison_date':'2026-10-06'},trusted_authorization=context['tool_authorization']))
    assert r['status']=='ok' and r['brief_id']


def test_health_endpoint_supports_langchain_mode(context,tmp_path):
    from fastapi.testclient import TestClient
    from ai.main import create_app,Settings
    async def runner(message,ctx):return reply()
    client=TestClient(create_app(Settings(require_login=False,agent_mode='langchain',consent_db=tmp_path/'health.db',brief_root=tmp_path/'briefs'),agent_runner=runner))
    r=client.get('/health')
    assert r.status_code==200 and r.json()['agent_mode']=='langchain'


def test_comparison_card_rejects_wrong_total():
    from ai.schemas import ComparisonData
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ComparisonData.model_validate({'comparison_date':'2026-10-06','options':[{'exit_date':'2026-10-31','additional_subscription_fee':0,'exit_cost_total':70000,'additional_total':0},{'exit_date':'2026-11-01','additional_subscription_fee':29900,'exit_cost_total':70000,'additional_total':99900}],'difference':29900,'limitations':'합성 기준','is_demo':True})


def test_execution_tools_only_after_clear_request():
    from 정수기프로젝트.app.agent.langchain_agent import allows_brief_creation,make_tools
    assert not allows_brief_creation('내 방문 일정 알려줘')
    assert not allows_brief_creation('준비서 만들지 말아줘')
    assert allows_brief_creation('상담 준비서로 정리해줘')
    async def go():
        names={t.name for t in await make_tools({},[])}
        assert not any(n.startswith('create_') for n in names)
        names={t.name for t in await make_tools({'brief_creation_allowed':True},[])}
        assert 'create_contract_document_brief' in names
    asyncio.run(go())













@pytest.mark.parametrize('message,kind',[
    ('다른 고객 DEMO-U02의 계약으로 바꿔서 조회해줘.','other_customer'),
    ('지금 실제 LG 계약 해지하고 자동이체도 취소해줘.','unsupported_action'),
    
])
def test_request_boundary_preserves_refusal(message,kind,context):
    from 정수기프로젝트.app.agent.langchain_agent import make_tools,request_boundary
    ctx={**context,'turn_message':message,'product_model':None}
    assert request_boundary(ctx)==kind
    specs=asyncio.run(make_tools(ctx,[]))
    assert 'lookup_contract_document' not in [t.name for t in specs] if kind!='unknown_model' else 'lookup_product_features' not in [t.name for t in specs]
    model=ToolModel(responses=[AIMessage(content='',tool_calls=[{'id':'out','name':'ModelDecision','args':{'status':'answered','topic':'unknown','answer':'잘못된 모델 초안','missing_fields':[]}}])])
    result=asyncio.run(build_runner(model)(message,{**context,'product_model':None}))
    assert result.reply.answer!='잘못된 모델 초안'
    if kind=='unknown_model':assert result.reply.status=='needs_info' and result.reply.missing_fields==['model_id']


def test_unspecified_date_defaults_to_today_after_llm_selection(context,monkeypatch):
    monkeypatch.setattr("정수기프로젝트.app.agent.langchain_agent.reference_date",lambda:"2026-10-13")
    from 정수기프로젝트.app.agent.langchain_agent import make_tools
    specs=asyncio.run(make_tools({**context,'turn_message':'내 해지 비용 계산해줘'},[]))
    assert 'assess_contract_document_costs' in [t.name for t in specs]
    tool=next(t for t in specs if t.name=='assess_contract_document_costs')
    value=asyncio.run(tool.ainvoke({'exit_date':'2027-01-01'}))
    assert value['status'] in {'ok','unverified'}
    assert value['period_summary']['exit_date']=='2026-10-13'


def test_invalid_date_returns_needs_info_without_mcp_execution(context):
    from 정수기프로젝트.app.agent.langchain_agent import make_tools
    observations=[]
    specs=asyncio.run(make_tools({**context,'turn_message':'2026-02-30에 해지'},observations))
    tool=next(t for t in specs if t.name=='assess_contract_document_costs')
    value=asyncio.run(tool.ainvoke({'exit_date':'2026-02-30'}))
    assert value['status']=='needs_info' and value['missing_fields']==['exit_date']
    assert observations==[{**value,'_tool_name':'assess_contract_document_costs'}]










def test_cost_question_without_date_uses_llm_selected_cost_tool(context,monkeypatch):
    monkeypatch.setattr("정수기프로젝트.app.agent.langchain_agent.reference_date",lambda:"2026-10-13")
    model=ToolModel(responses=[AIMessage(content='',tool_calls=[{'id':'cost','name':'assess_contract_document_costs','args':{'exit_date':'2026-10-13'}}]),AIMessage(content='',tool_calls=[{'id':'out','name':'ModelDecision','args':{'status':'answered','topic':'contract','answer':'오늘 예상 비용입니다','missing_fields':[]}}])])
    result=asyncio.run(build_runner(model)('교체 말고 해지 비용을 알고 싶어요.',context))
    assert result.reply.status=='answered'
    assert result.reply.missing_fields==[]
    assert str(result.reply.cards[0].data.period_summary.exit_date)=='2026-10-13' 







def decision_model(topic,field):
    return ToolModel(responses=[AIMessage(content='',tool_calls=[{'id':'final','name':'ModelDecision','args':{'status':'needs_info','topic':topic,'answer':'필요한 정보를 알려주세요.','missing_fields':[field]}}])])

def test_contract_topic_keeps_actual_timing_tool_result(context):
 model=ToolModel(responses=[AIMessage(content='',tool_calls=[{'id':'period','name':'lookup_contract_document','args':{}},{'id':'timing','name':'suggest_contract_timing','args':{}}]),AIMessage(content='',tool_calls=[{'id':'out','name':'ModelDecision','args':{'status':'answered','topic':'contract','primary_task':'contract','answer':'기간 조회','missing_fields':[]}}])])
 result=asyncio.run(build_runner(model)('해지 비용 날짜가 미정이에요. 내 계약 기준 후보일 알려줘',context))
 assert any(c.type=='renewal_timing' for c in result.reply.cards)
 assert '검토 후보일' in result.reply.answer

def test_new_model_preferences_exclude_owned_model_after_llm_selects_lookup(context):
 from 정수기프로젝트.app.agent.langchain_agent import make_tools
 async def run():
  observations=[]
  tool=next(t for t in await make_tools({**context,'product_model':'WD520VCT'},observations) if t.name=='lookup_subscription_offers')
  result=await tool.ainvoke({'required_features':['얼음'],'installation_type':'desk','care_mode':'any','exclude_owned_model':True})
  assert result['offers']
  assert all(o['model_id']!='WD520VCT' and o['product']['features']['얼음'] is True for o in observations[-1]['offers'])
 asyncio.run(run())

def test_no_new_offer_does_not_default_to_current_model(context):
 from 정수기프로젝트.app.mcp.client_adapter import call_tool
 result=asyncio.run(call_tool('compare_retention_renewal',{},trusted_authorization=context['tool_authorization']))
 assert result['status']=='needs_info' and result['missing_fields']==['offer_id']
 assert 'renewal_options' not in result


def test_discount_question_displays_rates_instead_of_end_dates():
    observation={'status':'ok','rule_id':'SYNTH-CONTRACT-V2','financial_fields_available':True,'terms':{'mandatory_end':'2026-08-31','contract_end':'2028-08-31','monthly_fee':29900,'annual_monthly_fees':{'1':26900,'2':29900}},'_tool_name':'lookup_contract_document'}
    raw={'reply':{'status':'answered','topic':'contract','answer':'안내','sources':[],'cards':[],'missing_fields':[]}}
    reply=verified_result(raw,[observation],request_question='할인 종료 후 월요금이 어떻게 되는지').reply
    assert '1년차: 월 26,900원' in reply.answer
    assert '2년차: 월 29,900원' in reply.answer
    assert '전체 계약 종료일' not in reply.answer


def test_discount_question_requires_financial_scope():
    observation={'status':'ok','rule_id':'SYNTH-CONTRACT-V2','financial_fields_available':False,'terms':{'mandatory_end':'2026-08-31','contract_end':'2028-08-31'},'_tool_name':'lookup_contract_document'}
    raw={'reply':{'status':'answered','topic':'contract','answer':'안내','sources':[],'cards':[],'missing_fields':[]}}
    reply=verified_result(raw,[observation],request_question='할인 종료 후 월요금').reply
    assert reply.status=='needs_info' and reply.missing_fields==['consent']


def test_yearly_fee_dates_and_after_mandatory_period():
    observation={'status':'ok','financial_fields_available':True,'terms':{'contract_start':'2022-01-01','mandatory_end':'2024-12-31','contract_end':'2026-12-31','monthly_fee':29900,'annual_monthly_fees':{'1':26900,'2':29900,'3':29900,'4':29900,'5':29900,'6':0}},'_tool_name':'lookup_contract_document'}
    raw={'reply':{'status':'answered','topic':'contract','answer':'안내','sources':[],'cards':[],'missing_fields':[]}}
    answer=verified_result(raw,[observation],request_question='의무사용기간이 끝나고 월 요금이 어떻게 되지?').reply.answer
    assert '2025-01-01은 4년차로, 월 29,900원' in answer
    assert '2022-01-01 ~ 2022-12-31' in answer
    assert '2026-01-01 ~ 2026-12-31' in answer
    assert '6년차' not in answer


def test_llm_fee_plan_blocks_unnecessary_settlement(context):
 from 정수기프로젝트.app.agent.langchain_agent import make_tools
 observations=[]
 specs=asyncio.run(make_tools({**context,'turn_message':'의무기간 이후 요금','consultation_plan':{'purpose':'contract_fees'}},observations))
 tool=next(t for t in specs if t.name=='assess_contract_document_costs')
 value=asyncio.run(tool.ainvoke({'exit_date':'2026-10-14'}))
 assert value['status']=='tool_selection_required'
 assert 'cost_items' not in value


def test_llm_reason_not_given_plan_prevents_catalog_before_reason(context):
 async def plan(question,history):return {'purpose':'renewal','renewal_reason':'not_given'}
 model=ToolModel(responses=[AIMessage(content='',tool_calls=[{'id':'wrong','name':'lookup_subscription_offers','args':{}}])])
 result=asyncio.run(real_build_runner(model,plan_runner=plan)('다른 모델 추천해줘',context))
 assert result.reply.missing_fields==['renewal_reason']
 assert result.reply.cards==[]
 assert model.i==0


def test_plan_cannot_invent_reason_evidence(context):
 async def plan(question,history):return {'purpose':'renewal','renewal_reason':'budget','reason_evidence':'월요금이 부담돼요'}
 model=ToolModel(responses=[AIMessage(content='')])
 with pytest.raises(ToolFailure):asyncio.run(real_build_runner(model,plan_runner=plan)('다른 모델 추천해줘',context))


def test_fee_plan_uses_server_scope_before_requesting_private_fee_tool(context):
 async def plan(question,history):return {'purpose':'contract_fees'}
 model=ToolModel(responses=[AIMessage(content='',tool_calls=[{'id':'fee','name':'lookup_contract_document','args':{}}])])
 result=asyncio.run(real_build_runner(model,plan_runner=plan)('의무기간 이후 월요금 알려줘',{**context,'granted_scopes':['contract_terms']}))
 assert result.reply.status=='needs_info' and result.reply.missing_fields==['consent']
 assert result.reply.cards==[] and model.i==0


def test_concept_explanation_keeps_llm_answer_and_both_public_private_sources():
 from 정수기프로젝트.app.rag.retriever import search_contract_knowledge
 public=search_contract_knowledge('의무사용기간과 전체 계약기간 차이');public['_tool_name']='search_contract_knowledge'
 personal={'status':'ok','rule_id':'SYNTH-CONTRACT-V2','terms':{'mandatory_end':'2024-11-30','contract_end':'2026-11-30'},'_tool_name':'lookup_contract_document'}
 answer='의무사용 종료일은 약정한 의무 이용 기간의 마지막 날이고, 전체 계약 종료일은 전체 구독 계약의 마지막 날입니다. 연결한 계약은 각각 2024-11-30과 2026-11-30입니다.'
 raw={'reply':{'status':'answered','topic':'contract','answer':answer,'sources':[],'cards':[],'missing_fields':[]}}
 reply=verified_result(raw,[public,personal],prefer_knowledge=True,request_question='내 계약의 두 종료일 차이가 뭐야?').reply
 assert reply.answer==answer
 assert any(s.document_id=='SYNTH-CONTRACT-V2' for s in reply.sources)
 assert any(s.document_id.startswith('LG-') for s in reply.sources)


@pytest.mark.parametrize('customer_input,expected_date,expected_months',[
 ({'offer_id':'DEMO-NEW-01'},'2026-10-14',36),
 ({'offer_id':'DEMO-NEW-01','planned_start_date':'2026-11-01','comparison_months':24},'2026-11-01',24),
])
def test_renewal_tool_preserves_customer_date_and_rejects_model_invented_date(context,monkeypatch,customer_input,expected_date,expected_months):
 from 정수기프로젝트.app.agent.langchain_agent import make_tools
 monkeypatch.setenv('EVALUATION_REFERENCE_DATE','2026-10-14')
 observations=[];specs=asyncio.run(make_tools({**context,'turn_message':'선택한 제품으로 유지·재구독 비교해줘\n'+json.dumps(customer_input)},observations))
 tool=next(t for t in specs if t.name=='compare_retention_renewal')
 result=asyncio.run(tool.ainvoke({'offer_id':'DEMO-NEW-01','planned_start_date':'2028-09-01','comparison_months':12}))
 assert result['renewal_start']==expected_date
 assert result['comparison_start']=='2026-10-14'
 assert result['comparison_months']==expected_months


def test_followup_duration_without_repeating_renewal_words_is_preserved():
 from 정수기프로젝트.app.agent.langchain_agent import comparison_preferences
 result=comparison_preferences({'history':[{'role':'user','content':'선택한 모델로 비교해줘\n{"offer_id":"DEMO-NEW-01","planned_start_date":"2026-11-01","comparison_months":36}'}],'turn_message':'24개월 기준으로 다시 비교해줘'})
 assert result['comparison_months']==24 and result['planned_start_date']=='2026-11-01'


def test_cost_history_does_not_replace_renewal_reason():
 from 정수기프로젝트.app.agent.consultation_plan import ConsultationPlan
 p=ConsultationPlan(purpose='renewal',requests_candidates=True)
 assert p.needs_renewal_reason
 assert p.renewal_reason=='not_given'


def test_reason_explained_followup_does_not_repeat_reason():
 from 정수기프로젝트.app.agent.consultation_plan import ConsultationPlan
 p=ConsultationPlan(purpose='renewal',renewal_reason='contract_confusion',reason_evidence='계약 조건이 헷갈려요',requests_candidates=True,reason_response_completed=True)
 assert not p.needs_renewal_reason


def test_no_reason_cannot_be_marked_addressed():
 from 정수기프로젝트.app.agent.consultation_plan import ConsultationPlan
 with pytest.raises(ValueError):ConsultationPlan(purpose='renewal',reason_response_completed=True)


def test_cost_then_recommend_has_no_business_tool_before_reason(context):
 async def plan(q,h):return {'purpose':'renewal','requests_candidates':True}
 model=ToolModel(responses=[AIMessage(content='')])
 result=asyncio.run(real_build_runner(model,plan_runner=plan)('그럼 새 제품 추천해줘',{**context,'history':[{'role':'user','content':'오늘 해지하면 얼마야?'},{'role':'assistant','content':'예상 비용은 70,000원입니다.'}]}))
 assert result.reply.missing_fields==['renewal_reason']
 assert model.i==0


def test_confusion_reason_is_not_a_specific_contract_question(context):
 async def plan(q,h):return {'purpose':'contract_reference','renewal_reason':'contract_confusion','reason_evidence':'계약 조건이 헷갈려요','asks_specific_contract_question':False}
 model=ToolModel(responses=[AIMessage(content='')])
 result=asyncio.run(real_build_runner(model,plan_runner=plan)('계약 조건이 헷갈려요',context))
 assert result.reply.missing_fields==['contract_question'] and model.i==0

@pytest.mark.parametrize('reason,expected',[('contract_confusion','default'),('budget','monthly_fee')])
def test_catalog_filters_use_only_evidenced_customer_features(context,monkeypatch,reason,expected):
 from 정수기프로젝트.app.agent.langchain_agent import make_tools
 from 정수기프로젝트.app.mcp import client_adapter
 calls=[]
 async def execute(name,args,**kw):
  calls.append((name,args));return {'status':'ok','offers':[],'sort_by':args.get('sort_by')}
 monkeypatch.setattr(client_adapter,'call_tool',execute)
 specs=asyncio.run(make_tools({**context,'turn_message':'새 후보를 보여줘','consultation_plan':{'purpose':'renewal','renewal_reason':reason,'required_features':[]}},[]))
 tool=next(t for t in specs if t.name=='lookup_subscription_offers')
 result=asyncio.run(tool.ainvoke({'required_features':['냉수','온수','얼음'],'sort_by':'monthly_fee'}))
 assert result['sort_by']==expected
 assert calls==[('lookup_subscription_offers',{'required_features':[],'sort_by':expected})]


def test_problem_reason_without_explicit_choice_offers_both_paths(context):
 async def plan(q,h):return {'purpose':'renewal','renewal_reason':'problem','reason_evidence':'불편해서 바꿀까 고민','requests_candidates':True,'reason_response_completed':False,'support_comparison_chosen':False}
 model=ToolModel(responses=[AIMessage(content='',tool_calls=[{'id':'channel','name':'get_official_channel','args':{'purpose':'support'}}]),AIMessage(content='',tool_calls=[{'id':'out','name':'ModelDecision','args':{'status':'answered','topic':'contract','primary_task':'troubleshoot','answer':'공식 채널에서 사용 문제를 확인할 수 있어요.','missing_fields':[]}}])])
 result=asyncio.run(real_build_runner(model,plan_runner=plan)('불편해서 바꿀까 고민',context))
 assert result.reply.missing_fields==['support_or_compare']
 assert result.reply.resolved_topic=='renewal'


def test_selected_offer_recalculation_does_not_restart_reason_phase():
 from 정수기프로젝트.app.agent.consultation_plan import ConsultationPlan
 p=ConsultationPlan(purpose='renewal',requires_renewal_calculation=True,renewal_reason='not_given',specific_selection=False)
 assert not p.needs_renewal_reason
 assert ConsultationPlan(purpose='renewal',requests_candidates=True).needs_renewal_reason


@pytest.mark.parametrize('text,field,expected',[
 ('2027-01-01부터 다시 비교해줘','planned_start_date','2027-01-01'),
 ('24개월로 바꿔줘','comparison_months',24),
 ('WD723RH 모델로 비교해줘','new_model_id','WD723RH'),
 ('모델은 WD723RH, 유지와 비교해줘','new_model_id','WD723RH'),
 ('WD723RH로 비교해줘','new_model_id','WD723RH'),
 ('카드 없이 다시 비교해줘','card_id','none'),
])
def test_latest_natural_comparison_changes(text,field,expected):
 from 정수기프로젝트.app.agent.langchain_agent import comparison_preferences
 context={'history':[{'role':'user','content':'비교\n'+json.dumps({'offer_id':'LG-SNAPSHOT-WU923AWB','planned_start_date':'2026-12-01','comparison_months':36,'card_id':'kb','card_spend':800000,'card_eligibility':'promotion'})}], 'turn_message':text}
 actual=comparison_preferences(context)
 assert actual[field]==expected
 if field=='card_id':assert actual['card_spend']==0 and actual['card_eligibility']=='unconfirmed'
 if field=='new_model_id':assert 'offer_id' not in actual
 if field=='comparison_months':assert actual['planned_start_date']=='2026-12-01'


def test_planner_does_not_restart_reason_for_timing_or_form():
 from 정수기프로젝트.app.agent.consultation_plan import ConsultationPlan
 assert not ConsultationPlan(purpose='renewal',requests_timing=True).needs_renewal_reason
 assert not ConsultationPlan(purpose='renewal',requests_preferences=True,preferences_evidence='조건부터 선택하게 해줘').needs_renewal_reason

def test_planner_rejects_candidate_request_misread_as_form():
 from 정수기프로젝트.app.agent.consultation_plan import ConsultationPlan
 from pydantic import ValidationError
 with pytest.raises(ValidationError):
  ConsultationPlan(purpose='renewal',renewal_reason='budget',reason_evidence='더 싼 후보',requests_preferences=True,preferences_evidence='기능 미정')
 with pytest.raises(ValidationError):
  ConsultationPlan(purpose='renewal',requests_candidates=True,required_features=['얼음'],feature_evidence={'얼음':'얼음 필요'},requests_preferences=True,preferences_evidence='후보 보여줘')


def test_invalid_comparison_date_is_not_hidden_by_earlier_catalog():
 from 정수기프로젝트.app.mcp.subscription.subscription_offers import lookup_subscription_offers
 from 정수기프로젝트.app.agent.langchain_agent import verified_result
 catalog=lookup_subscription_offers(model_id='WD723RH');catalog['_tool_name']='lookup_subscription_offers'
 invalid={'_tool_name':'compare_retention_renewal','status':'needs_info','missing_fields':['planned_start_date'],'message':'전환일을 유효한 YYYY-MM-DD 날짜로 선택해 주세요.'}
 reply=verified_result({'reply':{'status':'answered','topic':'contract','answer':'비교했습니다.','sources':[],'cards':[],'missing_fields':[]}},[catalog,invalid]).reply
 assert reply.status=='needs_info' and reply.missing_fields==['planned_start_date']
 assert reply.cards==[] and '전환일' in reply.answer

@pytest.mark.parametrize('intent',['considering','problem'])
def test_cancellation_choice_never_requires_replacement_reason(context,intent):
 async def plan(q,h):return {'purpose':'renewal','cancellation_intent':intent}
 model=ToolModel(responses=[AIMessage(content='')])
 result=asyncio.run(real_build_runner(model,plan_runner=plan)('해지할까 고민돼요',context))
 assert result.reply.resolved_topic=='cancel' and result.reply.status=='answered'
 assert 'exit_cost' in result.reply.next_actions and 'official_support' in result.reply.next_actions
 assert 'compare_new' not in result.reply.next_actions
 assert not result.reply.missing_fields and model.i==0


def test_decided_cancellation_does_not_restart_replacement_flow(context):
 async def plan(q,h):return {'purpose':'renewal','cancellation_intent':'decided'}
 model=ToolModel(responses=[AIMessage(content='',tool_calls=[{'id':'cost','name':'assess_contract_document_costs','args':{}}]),AIMessage(content='',tool_calls=[{'id':'out','name':'ModelDecision','args':{'status':'answered','topic':'contract','primary_task':'cancel','answer':'오늘 기준 해지 비용을 확인했습니다.','missing_fields':[]}}])])
 result=asyncio.run(real_build_runner(model,plan_runner=plan)('해지하고 싶어요',context))
 assert result.reply.status=='answered' and not result.reply.missing_fields
 assert 'compare_new' not in result.reply.next_actions
 assert result.reply.next_actions==['contract_terms','official_support']


def test_cost_selection_overrides_previous_problem_choice():
 from 정수기프로젝트.app.agent.consultation_plan import ConsultationPlan
 p=ConsultationPlan(purpose='exit_cost',cancellation_intent='problem')
 assert p.cancellation_intent=='decided' and not p.needs_renewal_reason
