"""계약 중심 서비스의 도구 경계·LLM 선택·중복 호출·공식 채널 회귀."""
import asyncio
import pytest
from 정수기프로젝트.app.agent.langchain_agent import make_tools,verified_result,TOOLS
from 정수기프로젝트.app.mcp.client_adapter import get_tool_specs,call_tool,MCPToolError,ALLOWED_TOOLS
EXPECTED={'get_official_channel', 'compare_retention_renewal', 'create_contract_document_brief', 'create_renewal_brief', 'search_contract_knowledge', 'assess_contract_document_costs', 'lookup_subscription_offers', 'compare_contract_options', 'lookup_product_features', 'suggest_contract_timing', 'lookup_contract_document'}

def test_registered_and_exposed_tools_are_contract_only():
 specs=asyncio.run(get_tool_specs())
 assert {s['name'] for s in specs}==EXPECTED==TOOLS==ALLOWED_TOOLS
 assert len(specs)==len(EXPECTED)
 for s in specs:
  assert 'session_id' not in s['input_schema'].get('properties',{})
  assert 'access_token' not in s['input_schema'].get('properties',{})

@pytest.mark.parametrize('question',['새 정수기 추천해줘','온수가 미지근해요','내 계약 알려줘','두 날짜 비교해줘'])
def test_question_does_not_force_or_hide_contract_tools(question):
 names={t.name for t in asyncio.run(make_tools({'turn_message':question},[]))}
 assert names==EXPECTED-{'create_contract_document_brief','create_renewal_brief'}

@pytest.mark.parametrize('purpose,url',[('product','https://www.lge.co.kr/category/water-purifiers'),('support','https://www.lge.co.kr/ai-commerce/aiAssistant'),('contract','https://www.lge.co.kr/support')])
def test_public_official_channel_needs_no_private_authority(purpose,url):
 data=asyncio.run(call_tool('get_official_channel',{'purpose':purpose}))
 reply=verified_result({'reply':{'status':'answered','topic':'contract','answer':'초안','sources':[],'cards':[],'missing_fields':[]}},[{**data,'_tool_name':'get_official_channel'}]).reply
 assert str(reply.sources[0].url)==url
 assert reply.missing_fields==[] and reply.cards==[]
 assert '자동 전달' in reply.answer

def test_retired_tool_cannot_be_invoked():
 with pytest.raises(MCPToolError):asyncio.run(call_tool('assess_symptom_next_step',{}))

def test_parallel_public_calls_are_reused_once():
 async def run():
  observations=[];tool=next(t for t in await make_tools({},observations) if t.name=='get_official_channel')
  a,b=await asyncio.gather(tool.ainvoke({'purpose':'support'}),tool.ainvoke({'purpose':'support'}))
  assert a==b and len(observations)==1
 asyncio.run(run())

@pytest.mark.parametrize('name,args,key',[('lookup_product_features',{'model_ids':['WD520VCT']},'products'),('lookup_subscription_offers',{},'offers')])
def test_restored_model_comparison_tools_execute_through_mcp(name,args,key):
 result=asyncio.run(call_tool(name,args))
 assert result['status']=='ok' and result[key]


def test_public_benefit_question_does_not_require_personal_contract_consent():
 async def run():
  observations=[]
  context={'turn_message':'교체보상 포인트를 해지비에서 빼도 되나요?', 'consultation_plan':{'purpose':'contract_reference'}}
  selected={t.name:t for t in await make_tools(context,observations)}
  private=await selected['lookup_contract_document'].ainvoke({})
  assert private['status']=='tool_selection_required' and 'consent' not in private.get('missing_fields',[])
  result=await selected['search_contract_knowledge'].ainvoke({'query':'교체보상 10만 포인트 혜택'})
  assert result['documents'] and result['status']=='ok'
  reply=verified_result({'reply':{'status':'answered','topic':'contract','answer':'포인트와 해지 정산은 별도로 확인합니다.','sources':[],'cards':[],'missing_fields':[]}},observations).reply
  assert reply.status=='answered' and reply.missing_fields==[] and reply.sources
 asyncio.run(run())


def test_date_comparison_does_not_execute_repeated_single_date_settlements():
 async def run():
  observations=[]
  selected={t.name:t for t in await make_tools({'consultation_plan':{'purpose':'date_comparison'}},observations)}
  result=await selected['assess_contract_document_costs'].ainvoke({'exit_date':'2026-10-31'})
  assert result['status']=='tool_selection_required'
  assert 'cost_items' not in result and '총부담' in result['message']
 asyncio.run(run())
