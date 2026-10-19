"""LangChain 단일 Agent. 권한은 도구 클로저에만 주입하고 상태 체크포인터는 사용하지 않습니다."""
import json
import logging
import os
import sys
import re
from datetime import date
from typing import Literal
from pydantic import BaseModel,Field,model_validator
from pathlib import Path
# FastAPI의 ai 패키지와 같은 응답·예외 타입을 사용합니다.
backend_path=str(Path(__file__).resolve().parents[1] / 'backend')
if backend_path not in sys.path:
    sys.path.insert(0,backend_path)
from ai.agent_adapter import AgentUnavailable, ToolFailure, ModelProviderFailure
from ai.schemas import AgentResult
from ai.server_context import reference_date
from .consultation_policy import consultation_reason, FINANCIAL_TOOLS, restricted_result, reason_response_override
from ai.response_guard import guard_response, cost_text

TOOLS={'get_official_channel', 'compare_retention_renewal', 'create_contract_document_brief', 'create_renewal_brief', 'search_contract_knowledge', 'assess_contract_document_costs', 'lookup_subscription_offers', 'compare_contract_options', 'lookup_product_features', 'suggest_contract_timing', 'lookup_contract_document'}
PROMPT_PATH=Path(__file__).with_name('system_message.txt')


class ModelDecision(BaseModel):
    status: Literal['answered','needs_info']
    topic: Literal['purchase','troubleshoot','care_subscription','contract','unknown']
    primary_task: Literal['usage','features','troubleshoot','care','contract','cancel','renewal','recommend','purchase_method','installation','product_information'] | None = None
    answer: str = Field(min_length=1,max_length=2000)
    missing_fields: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def status_fields(self):
        if self.status=='needs_info' and not self.missing_fields:
            raise ValueError('needs_info requires missing_fields; refusal uses answered and []')
        if self.status=='answered':self.missing_fields=[]
        return self


def allows_brief_creation(message,history=None):
    """파일 실행 승인만 확인한다. 일반 상담의 도구 목록을 분류하는 함수가 아니다."""
    if re.search(r'만들지|생성하지|작성하지|필요\s*없',message):return False
    if re.search(r'준비서.*(만들|생성|작성|정리)|파일로.*정리|준비서로|다운로드.*(해|할|받)',message):return True
    previous=next((h.get('content','') for h in reversed(history or []) if h.get('role')=='assistant'),'')
    offered=bool(re.search(r'준비서.*(?:할까요|만들까요|원하|생성.*까요)',previous))
    accepted=bool(re.search(r'^(?:네|예|응|좋아|오케이)(?:$|[\s,.!])|^(?:그렇게|그걸로|그거)\s*(?:해|정리|만들|생성)',message.strip()))
    return offered and accepted


def comparison_preferences(context):
    """모델이 추정한 요금·환경보다 고객이 실제 입력한 값을 우선합니다."""
    allowed={'card_id','card_spend','card_eligibility','card_application_date','planned_start_date','billing_reference_date','offer_id','comparison_date','comparison_months','maintenance_monthly_fee','installation_conditions','new_model_id'}
    inputs={}
    text=context.get('turn_message','')
    for entry in [*context.get('history',[]),{'role':'user','content':text}]:
        content=entry.get('content','')
        if entry.get('role')!='user':continue
        if '{' not in content:
            if re.search(r'재구독|전환|교체|바꾸|바꿔|새로|비교',content):
                chosen=re.search(r'(?<![A-Z0-9])(W[DSU][A-Z0-9]+)(?![A-Z0-9])',content,re.I)
                if chosen:inputs.pop('offer_id',None);inputs['new_model_id']=chosen.group(1).upper()
                dates=re.findall(r'(\d{4})[-년]\s*(\d{1,2})[-월]\s*(\d{1,2})',content)
                if len(dates)==1:
                    try:inputs['planned_start_date']=date(*map(int,dates[0])).isoformat()
                    except ValueError:pass
            if re.search(r'비교|바꿔|변경|개월로',content):
                months=re.search(r'([0-9]{1,3})\s*개월',content)
                if months:inputs['comparison_months']=int(months.group(1))
            if re.search(r'카드\s*(?:없이|미사용|사용\s*안|제외|빼|할인\s*(?:없이|해제))|카드.*(?:쓰지|사용하지)',content):
                inputs.update(card_id='none',card_spend=0,card_eligibility='unconfirmed',card_application_date='')
            continue
        try:
            obj=json.loads(content[content.index('{'):])
            if isinstance(obj,dict):
                if 'required_features' in obj or 'installation_type' in obj or 'care_mode' in obj:
                    inputs.pop('offer_id',None);inputs.pop('new_model_id',None)
                if obj.get('new_model_id') and not obj.get('offer_id'):inputs.pop('offer_id',None)
                inputs.update({k:v for k,v in obj.items() if k in allowed})
        except (ValueError,TypeError):pass
    # 이번 턴의 명시적 전환 날짜는 과거 폼 입력보다 우선합니다.
    if re.search(r'재구독|전환|교체|바꿔|새로|비교',text) and not '{' in text:
        match=re.search(r'(\d{4})[-년]\s*(\d{1,2})[-월]\s*(\d{1,2})',text)
        if match:
            try:inputs['planned_start_date']=date(*map(int,match.groups())).isoformat()
            except ValueError:inputs['planned_start_date']='-'.join(match.groups())
        elif '오늘' in text:inputs['planned_start_date']=reference_date()
    if 'billing_reference_date' in inputs:inputs['comparison_date']=inputs.pop('billing_reference_date')
    if 'maintenance_monthly_fee' not in inputs:
        for item in reversed([*context.get('history',[]),{'role':'user','content':text}]):
            if item.get('role')!='user':continue
            value=item.get('content','')
            match=re.search(r'관리비[^\n]{0,16}?([0-9][0-9,]*)\s*(?:원|$)',value,re.M)
            if match and not re.search(r'모르|예시|만약|미확인|\?',value):
                inputs['maintenance_monthly_fee']=int(match.group(1).replace(',',''));break
    if '{' not in text:
        match=re.search(r'([0-9]{1,3})\s*개월',text)
        if match:inputs['comparison_months']=int(match.group(1))
    return inputs


PRIVATE_TOOLS={'lookup_contract_document','assess_contract_document_costs','compare_contract_options','create_contract_document_brief','compare_retention_renewal','create_renewal_brief','suggest_contract_timing'}
COST_TOOLS={'assess_contract_document_costs','compare_contract_options'}


def request_boundary(context):
    message=context.get('turn_message','')
    if re.search(r'다른\s*고객|타인|남의|DEMO-U0[2-4].*(바꿔|조회)',message):return 'other_customer'
    action_text=re.sub(r'실제[^\n.!?]*?해지\s*신청(?:은|이|을)?\s*(?:아니야|아닙니다|아니고|하지\s*마)','',message)
    if re.search(r'실제[^\n.!?]*?(?:해지\s*(?:신청|접수|처리)|해지(?:해|시켜)\s*줘)|자동이체[^\n.!?]*취소(?:해|해줘|처리)|실제.*해지하고',action_text):return 'unsupported_action'
    if re.search(r'(?:토큰|동의|권한).{0,18}(?:만들|위조|우회|임의)',message):return 'authorization_bypass'
    return None


def boundary_reply(kind):
    if kind=='authorization_bypass':return {'status':'answered','topic':'contract','answer':'권한 토큰을 만들거나 동의를 우회해서 조회할 수 없습니다. 동의 화면에서 필요한 범위를 승인한 본인 계약만 조회할 수 있습니다.','missing_fields':[],'sources':[],'cards':[]}
    text='다른 고객의 계약으로 바꾸거나 조회할 수 없습니다. 현재 승인된 본인 계약 범위에서만 상담할 수 있습니다.' if kind=='other_customer' else '실제 LG 계약 해지·자동이체 취소는 이 서비스에서 수행하지 않습니다. 원하시면 본인 계약의 기간과 예상 비용을 확인하거나 상담 준비서를 정리할 수 있습니다.'
    return {'status':'answered','topic':'contract','answer':text,'missing_fields':[],'sources':[],'cards':[]}


def has_cost_date(context):
    texts=[context.get('turn_message','')]+[h.get('content','') for h in context.get('history',[]) if h.get('role')=='user']
    return any(re.search(r'\d{4}-\d{2}-\d{2}|\d{4}년\s*\d{1,2}월\s*\d{1,2}일|오늘',text) for text in texts)


async def make_tools(context, observations):
    """질문 단어로 도구를 숨기지 않는다. 선택은 LLM, 권한·입력 검증은 서버."""
    from langchain_core.tools import StructuredTool
    from 정수기프로젝트.app.mcp.client_adapter import get_tool_specs, call_tool
    from 정수기프로젝트.app.consent import ConsentStore, ConsentDenied
    from .response_topics import customer_question
    auth=dict(context.get('tool_authorization') or {})
    question=customer_question(context.get('turn_message',''))
    preferences=comparison_preferences(context)
    reason=consultation_reason(context)
    kind=request_boundary(context)
    import asyncio
    cache={}
    locks={}
    private_scopes={
        'lookup_contract_document':'contract_terms',
        'suggest_contract_timing':'contract_terms',
        'assess_contract_document_costs':'contract_costs',
        'compare_contract_options':'contract_costs',
        'compare_retention_renewal':'contract_costs',
    }
    def authorized_subject(name):
        scope=private_scopes[name]
        return ConsentStore().authorize(auth.get('session_id',''),auth.get('access_token',''),scope)['demo_customer_id']
    def bind(name):
        async def execute(**kwargs):
            kwargs=dict(kwargs)
            plan=context.get('consultation_plan') or {}
            if plan.get('purpose')=='date_comparison' and name=='assess_contract_document_costs':
                value={'status':'tool_selection_required','message':'현재는 두 날짜의 총부담 비교 요청입니다. 단일 날짜 정산을 반복하지 말고 두 날짜와 그 사이 이용요금을 포함하는 비교 결과를 사용하세요.','_tool_name':name}
                observations.append(value);return value
            if plan.get('purpose')=='contract_reference' and not plan.get('requires_contract_period_example') and not plan.get('requests_timing') and name in PRIVATE_TOOLS:
                value={'status':'tool_selection_required','message':'현재 요청은 일반 계약 개념이나 공개 혜택 조건 확인입니다. 개인 계약 조회·동의가 필요한 과제로 바꾸지 말고 공개 근거를 조회해 현재 질문에 답하세요.','_tool_name':name}
                observations.append(value);return value
            if plan.get('purpose')=='contract_fees' and name in FINANCIAL_TOOLS:
                value={'status':'tool_selection_required','message':'현재 과제는 계약 월요금 설명입니다. 해지 정산/재구독 계산은 이 질문에서 실행하지 않습니다. 계약 요금 조회 결과로 답하세요.','_tool_name':name}
                observations.append(value);return value
            if plan.get('requests_timing') and name not in {'suggest_contract_timing','lookup_contract_document'}:
                value={'status':'tool_selection_required','message':'현재 요청은 날짜 미정에 대한 시점 후보입니다. suggest_contract_timing 결과를 안내하고 선택 날짜로 재계산은 고객 선택 후 진행하세요.','_tool_name':name}
                observations.append(value);return value
            owned=context.get('product_model')
            if name=='search_contract_knowledge':
                kwargs['purpose']='consultation_reference'
                models=re.findall(r'W[DSU][A-Z0-9]+',kwargs.get('query',''),re.I)
                kwargs['model_id']=models[0].upper() if len(set(models))==1 else (owned or '')
            if name=='lookup_product_features' and owned:
                requested=kwargs.get('model_ids',[])
                if not requested or all(m.strip().upper() in {'','UNKNOWN','내 제품','MY_PRODUCT'} for m in requested):kwargs['model_ids']=[owned]
            if name in {'compare_retention_renewal','create_renewal_brief'} and not (preferences.get('offer_id') or preferences.get('new_model_id')):
                value={'status':'needs_info','missing_fields':['offer_id'],'message':'원하는 기능의 새 모델 후보를 먼저 확인하고 비교할 제품을 선택해 주세요. 임의 모델로 계산하지 않습니다.','_tool_name':name}
                observations.append(value);return value
            if name=='lookup_subscription_offers':
                if 'required_features' in plan:
                    kwargs['required_features']=plan['required_features']
                    kwargs['sort_by']='monthly_fee' if plan.get('renewal_reason')=='budget' else 'default'
                exclude=kwargs.pop('exclude_owned_model',False)
                # 고객이 원하는 필터만 실행 도구에 전달. 업무 도구 선택은 LLM이 수행한다.
                if exclude and owned:
                    kwargs['exclude_model_id']=owned
                    if kwargs.get('model_id')==owned:kwargs['model_id']=''
            # 위험한 분쟁 비용 확정은 선택 뒤에 거절한다. 다른 정상 도구를 선택해 주지 않는다.
            if reason=='service_dispute' and (name in FINANCIAL_TOOLS or (name=='create_contract_document_brief' and any(kwargs.get(k) for k in ('exit_date','exit_date_a','exit_date_b','comparison_date')))):
                value={**restricted_result(reason),'_tool_name':name};observations.append(value);return value
            if name=='assess_contract_document_costs' and not has_cost_date(context):
                kwargs['exit_date']=reference_date()
            if name=='compare_contract_options' and not has_cost_date(context):
                value={'status':'needs_info','missing_fields':['exit_date'],'message':'해지 검토일을 확인해 주세요.','_tool_name':name};observations.append(value);return value
            if name in COST_TOOLS:
                # 현재 입력의 존재하지 않는 날짜를 모델이 다른 날짜로 고쳐 계산하지 못하게 한다.
                typed_dates=re.findall(r'(\d{4})[-년]\s*(\d{1,2})[-월]\s*(\d{1,2})',context.get('turn_message',''))
                invalid=False
                for parts in typed_dates:
                    try:date(*map(int,parts))
                    except ValueError:invalid=True
                if invalid:
                    value={'status':'needs_info','missing_fields':['exit_date'],'message':'입력한 날짜가 존재하지 않습니다. 정확한 해지 검토일을 확인해 주세요.','_tool_name':name};observations.append(value);return value
            if name in COST_TOOLS:
                fields=['exit_date'] if name=='assess_contract_document_costs' else ['exit_date_a','exit_date_b']
                for field in fields:
                    try:date.fromisoformat(kwargs.get(field,''))
                    except (TypeError,ValueError):
                        value={'status':'needs_info','missing_fields':[field],'message':'해지 검토일을 정확한 YYYY-MM-DD 날짜로 확인해 주세요.','_tool_name':name}
                        observations.append(value);return value
            if name=='compare_contract_options':
                kwargs['comparison_date']=preferences.get('comparison_date') or ''
            if name in {'compare_retention_renewal','create_renewal_brief'}:
                # The billing reference is a server/customer fact, never an LLM guess.
                kwargs['comparison_date']=preferences.get('comparison_date') or ''
                # 모델이 임의 날짜를 만들지 않도록 고객 입력만 전달. 미지정은 도구의 오늘 기본값.
                kwargs['planned_start_date']=preferences.get('planned_start_date') or ''
                kwargs['comparison_months']=preferences.get('comparison_months',36)
                for field in ('planned_start_date','comparison_months','installation_conditions','offer_id','comparison_date','card_id','card_spend','card_eligibility','card_application_date'):
                    if field in preferences:kwargs[field]=preferences[field]
                if preferences.get('new_model_id') and not preferences.get('offer_id'):
                    chosen=preferences['new_model_id']
                    kwargs['offer_id']={'WD520VCT':'DEMO-NEW-01','WU923AWB':'DEMO-NEW-02'}.get(chosen,'LG-SNAPSHOT-'+chosen)
                # 고객이 모르는 비용을 모델이 만들어서 입력하지 못하게 한다.
                kwargs['maintenance_monthly_fee']=preferences.get('maintenance_monthly_fee')
            key=(name,json.dumps(kwargs,sort_keys=True,ensure_ascii=False,default=str))
            async with locks.setdefault(key,asyncio.Lock()):
                if key in cache:
                    cached,subject=cache[key]
                    if name.startswith('create_'):
                        try:
                            path=ConsentStore().brief_path(cached['brief_id'],auth.get('session_id',''),token=auth.get('access_token',''))
                            if path is not None:return cached
                        except ConsentDenied:pass
                        cache.pop(key,None)
                    elif name not in private_scopes:return cached
                    elif name in private_scopes:
                        try:
                            if authorized_subject(name)==subject:return cached
                        except ConsentDenied:pass
                        cache.pop(key,None)
                try:
                    value={**await call_tool(name,kwargs,trusted_authorization=auth),'_tool_name':name}
                except Exception as exc:
                    logging.getLogger(__name__).warning('agent_failure trace_id=%s stage=tool tool=%s error_type=%s retry_count=0',context.get('trace_id',''),name,type(exc).__name__)
                    raise
                observations.append(value)
                delivered=value
                if value.get('status') in {'needs_info','forbidden'}:
                    delivered={**value,'next_action':'final_answer_request_input','continue_tool_calls':False,'agent_instruction':'사용자 입력이나 동의가 필요한 결과입니다. 같은 질문에서 증상을 임의로 나누거나 다른 인자로 반복하지 말고 ModelDecision으로 필요한 질문 하나를 반환하세요.'}
                if value.get('status')=='not_applicable' and name in private_scopes:
                    delivered={**value,'next_action':'final_answer_not_applicable','continue_tool_calls':False,'agent_instruction':'선택 고객에게 적용되는 구독 계약이 없습니다. 구독 비용을 다른 자료로 계산하거나 같은 도구를 반복하지 말고 적용 제외를 최종 안내하세요. 구매 취소·환불은 별도 질문과 근거가 필요합니다.'}
                if name=='lookup_subscription_offers' and len(value.get('offers',[]))>8:
                    delivered={'status':value['status'],'catalog_count':len(value['offers']),'offers':[{'offer_id':o['offer_id'],'model_id':o['model_id'],'care_details':o['care_details'],'source_kind':o['source_kind'],'features':(o.get('product') or {}).get('features',{}),'rate_note':o.get('rate_note'),'monthly_fee':o.get('display_monthly_fee') if o.get('price_is_snapshot') else o['rates'][0]['monthly_fee']} for o in value['offers'][:6]],'message':'전체 후보는 화면에 표시합니다. 이 미리보기 6개가 전체라고 답하지 마세요.','limitations':value['limitations']}
                if name.startswith('create_') and value.get('status')=='ok' and value.get('brief_id'):
                    cache[key]=(delivered,None)
                elif not name.startswith('create_') and value.get('status') in {'ok','unverified','needs_info','not_applicable'}:
                    if name in private_scopes:
                        try:cache[key]=(delivered,authorized_subject(name))
                        except ConsentDenied:pass
                    else:cache[key]=(delivered,None)
                return delivered
        return execute
    result=[]
    for spec in await get_tool_specs():
        if spec['name'] not in TOOLS:continue
        if kind in {'other_customer','unsupported_action','authorization_bypass'}:continue
        # 파일 생성은 명시적 실행 승인만 확인한다. 상담 주제와 단어에 따른 제한은 없다.
        if spec['name'].startswith('create_') and not context.get('brief_creation_allowed',False):continue
        result.append(StructuredTool.from_function(name=spec['name'],description=spec['description'],args_schema=spec['input_schema'],coroutine=bind(spec['name'])))
    return result


def product_card_payload(product,ready_models):
    fields=('model_id','features','checked_at','limitations','is_demo','display_name','image_url','product_url','purchase_price','purchase_price_status','subscription_monthly_from','price_checked_at','price_note','card_benefits','purchase_benefits','family_id','color_name','color_hex')
    return {**{k:product[k] for k in fields if k in product},
            'comparison_supported':product['model_id'] in ready_models,
            'source_ids':[v['document_id'] for v in product['sources']],
            'variants':[product_card_payload(v,ready_models) for v in product.get('variants',[])]}


def verified_result(raw,observations,token='',catalog_view=True,prefer_knowledge=False,request_question=''):
    raw=raw.model_dump(mode='json',exclude_unset=True) if isinstance(raw,AgentResult) else raw
    if token and token in json.dumps(raw,ensure_ascii=False):raise ToolFailure('권한 정보가 포함된 응답입니다.')
    # LLM이 정한 주된 목적에 맞는 실제 결과를 표시한다. 실행할 도구를 선택하는 로직이 아니다.
    primary=raw.get('reply',{}).get('resolved_topic')
    result_roles={
        'usage':{'get_official_channel'},
        'features':{'lookup_product_features','search_contract_knowledge'},
        'product_information':{'lookup_product_features','search_contract_knowledge'},
        'troubleshoot':{'get_official_channel'},
        'care':{'get_official_channel'},
        'contract':{'suggest_contract_timing','lookup_contract_document','search_contract_knowledge','create_contract_document_brief','get_official_channel'},
        'cancel':{'suggest_contract_timing','lookup_contract_document','assess_contract_document_costs','compare_contract_options','search_contract_knowledge','create_contract_document_brief'},
        'renewal':{'lookup_contract_document','suggest_contract_timing','lookup_subscription_offers','compare_retention_renewal','lookup_product_features','search_contract_knowledge','create_renewal_brief'},
        'recommend':{'get_official_channel','lookup_subscription_offers','lookup_product_features','search_contract_knowledge'},
        'purchase_method':{'get_official_channel','lookup_subscription_offers','search_contract_knowledge'},
        'installation':{'get_official_channel','search_contract_knowledge'},
    }
    if primary in result_roles:
        relevant=[o for o in observations if o.get('_tool_name') in result_roles[primary] or o.get('status')=='forbidden' or o.get('brief_id') or o.get('_tool_name')=='get_official_channel']
        if relevant:observations=relevant
    if any(o.get('status')=='error' for o in observations):raise ToolFailure('계약 도구 실행 실패')
    briefs=[o for o in observations if o.get('status')=='ok' and o.get('brief_id')]
    if briefs and raw.get('reply',{}).get('status')!='brief_created':
        raw={**raw,'reply':{**raw['reply'],'status':'brief_created','brief_id':briefs[-1]['brief_id'],'missing_fields':[]}}
    guarded_observations=observations
    result=guard_response({**raw,'tool_results':guarded_observations})
    reply=result['reply']
    term_rows=[o for o in observations if o.get('status')=='ok' and o.get('terms')]
    fee_question=bool(re.search(r'월.?요금|월.?구독료|할인.*(종료|끝|이후)|납부.*요금',request_question))
    if term_rows and fee_question and reply.get('status')=='answered':
        terms=term_rows[-1]['terms']
        if not term_rows[-1].get('financial_fields_available','monthly_fee' in terms):
            reply.update(status='needs_info',topic='contract',missing_fields=['consent'],answer='할인과 월요금 확인에는 요금 정보 조회 동의가 필요해요. 필요한 범위에 동의하면 계약서의 요금 조건을 확인할게요.',cards=[])
        else:
            rates=terms.get('annual_monthly_fees',{})
            lines=['계약서에 정해진 연차별 월요금입니다.']
            from datetime import date, timedelta, datetime
            from zoneinfo import ZoneInfo
            reference=date.fromisoformat(os.environ["EVALUATION_REFERENCE_DATE"]) if os.environ.get("EVALUATION_REFERENCE_DATE") else datetime.now(ZoneInfo("Asia/Seoul")).date()
            def anniversary(start,years):
                try:return start.replace(year=start.year+years)
                except ValueError:return start.replace(year=start.year+years,day=28)
            start=date.fromisoformat(terms['contract_start']) if terms.get('contract_start') else None
            end=date.fromisoformat(terms['contract_end']) if terms.get('contract_end') else None
            mandatory=date.fromisoformat(terms['mandatory_end']) if terms.get('mandatory_end') else None
            after=mandatory+timedelta(days=1) if mandatory else None
            matching=[]
            for year,amount in sorted(rates.items(),key=lambda item:int(item[0])):
                label=f"{year}년차: 월 {amount:,}원"
                if start:
                    begins=anniversary(start,int(year)-1)
                    finishes=anniversary(start,int(year))-timedelta(days=1)
                    if end and begins>end:continue
                    if end:finishes=min(finishes,end)
                    label+=f" ({begins.isoformat()} ~ {finishes.isoformat()})"
                    if begins<=reference<=finishes:label+=" · 현재 적용"
                    if after and begins<=after<=finishes:matching.append(f"의무사용기간 종료 다음 날 {after.isoformat()}은 {year}년차로, 월 {amount:,}원입니다.")
                lines.append(label)
            if matching:lines[0:0]=matching
            if end and after and after>end:lines.insert(0,'의무사용기간 종료 후에는 전체 계약도 종료됩니다. 종료 후 관리 요금은 별도 조건을 확인해야 해요.')
            if not rates:lines.append(f"계약서 기본 월요금: {terms['monthly_fee']:,}원. 할인 종료 이후 별도 요금표는 확인되지 않았습니다.")
            lines.append('카드 청구할인과 포인트는 별도 조건이며, 위 금액에서 자동 차감하지 않았어요. 시연용 가상 계약 기준입니다.')
            reply.update(topic='contract',answer='\n'.join(lines),cards=[],missing_fields=[])
    comparisons=[o for o in observations if o.get('status')=='ok' and 'options'in o]
    if comparisons and reply['status']=='answered':
        v=comparisons[-1];lines=[f"비교 기준일: {v['comparison_date']}"]
        for o in v['options']:
            # 항목 합계 검증은 기존 비용 검증기를 재사용합니다.
            cost_text(o['exit_costs'])
            if o['additional_total']!=o['additional_subscription_fee']+o['exit_costs']['estimated_total']:raise ToolFailure('비교 금액 불일치')
            lines.append(f"{o['exit_date']}: 추가 구독료 {o['additional_subscription_fee']:,}원 + 해지 비용 {o['exit_costs']['estimated_total']:,}원 = 추가 부담 {o['additional_total']:,}원")
        lines.extend([f"추가 부담 차이: {v['difference']:,}원",v['limitations']]);reply['answer']='\n'.join(lines);reply['topic']='contract'
    if any(o.get('rule_id')=='SYNTH-CONTRACT-V2' for o in observations):
        reply['sources']=[{'document_id':'SYNTH-CONTRACT-V2','title':'시연용 가상 계약·비용 기준'}]+[s for s in reply.get('sources',[]) if s['document_id']!='SYNTH-01']
    installations=[o for o in observations if 'estimated_additional_installation_fee' in o]
    if installations:
        v=installations[-1]
        total=v['estimated_additional_installation_fee'];subtotal=v['confirmed_subtotal']
        reply.update(status='needs_info' if v['missing_fields'] else 'answered',topic='purchase',missing_fields=v['missing_fields'],brief_id=None)
        heading=f'예상 추가 설치비: {total:,}원' if total is not None else f'확인된 추가 작업 소계: {subtotal:,}원. 예상 추가 설치비는 확인이 더 필요합니다.'
        reply['answer']=heading+'\n'+v['limitations']+('\n확인이 필요한 항목: '+', '.join(v['missing_fields']) if v['missing_fields'] else '')
        reply['sources']=list({r['source_id']:{'document_id':r['source_id'],'title':'LG 공식 모델별 설치 비용 안내','url':r['source_url'],'section':r['source_section'],'model_id':r['model_id'],'checked_at':r['checked_at']} for r in v['work_items']}.values())
    renewals=[o for o in observations if 'renewal_options' in o]
    if renewals:
        v=renewals[-1];lines=[f"비교 기간: {v['comparison_start']} ~ {v['comparison_end']}",f"재구독 시작 예정일: {v['renewal_start']}"]
        for o in v['renewal_options']:
            label='기존 제품 유지' if o['choice']=='keep' else '기존 계약 정산 후 재구독'
            total=o['estimated_total']
            lines.append(label+': '+(f"예상 {total:,}원" if total is not None else f"확인된 소계 {o['confirmed_subtotal']:,}원, 총액 미확정"))
            if o['missing_fields']:
                labels={'maintenance_monthly_fee':'종료 후 관리·소모품 비용','installation_fee':'기본 설치비','registration_fee':'등록비','other_initial_fee':'기타 초기비','future_price':'전환 시점 실제 적용 요금','new_subscription_terms':'신규 의무기간·가입·요금 조건','pump_needed':'펌프 필요 여부','breaker_needed':'차단기 필요 여부','drilling_needed':'타공 필요 여부','surface_material':'상판 재질'}
                lines.append('확인 필요: '+', '.join(labels.get(k,k) for k in o['missing_fields']))
            if o['choice']=='renew':
                lines.append(f"비교 종료 후 남는 계약 {o['remaining_contract_months']}개월 / 의무기간 "+(f"{o['remaining_mandatory_months']}개월" if o['remaining_mandatory_months'] is not None else '확인 필요'))
                if o.get('scenario_total') is not None:lines.append(f"현재 수집 요금 조건의 참고 합계 {o['scenario_total']:,}원. 미래 가입 총액이 아니며 초기비 미확인분은 제외합니다.")
        decision=v.get('decision',{});choice=decision.get('lower_cost_choice')
        if choice in {'keep','renew'}:lines.insert(0,('현재 제품 유지' if choice=='keep' else '기존 계약 정산 후 재구독')+f"가 비교에 포함한 비용 기준으로 최소 {decision['minimum_saving']:,}원 낮습니다.")
        lines.append(v['limitations'])
        brief_id=v.get('brief_id')
        if brief_id:lines.insert(0,'유지'+'·재구독 비교 상담 준비서를 생성했습니다. 실제 가입·해지 신청은 아닙니다.')
        reply.update(status='brief_created' if brief_id else 'answered',topic='contract',answer='\n'.join(lines),missing_fields=[],brief_id=brief_id)
        reply['sources']=[{'document_id':'SYNTH-CONTRACT-V2','title':'시연용 가상 계약·비용 기준'},v.get('offer_source') or {'document_id':'SYNTH-OFFER-V1','title':'시연용 신규 구독 조건'}]
    reply['cards']=[]
    cost_rows=[o for o in observations if o.get('_tool_name')=='assess_contract_document_costs' and o.get('status') in {'ok','unverified'} and o.get('cost_items')]
    if cost_rows and reply.get('status')=='answered':
        cost=cost_rows[-1]
        reply['cards']=[{'type':'contract','data':{'period_summary':{k:cost['period_summary'].get(k) for k in ('mandatory_end','contract_end','exit_date')},'cost_items':cost['cost_items'],'confirmed_subtotal':cost['confirmed_subtotal'],'estimated_total':cost.get('estimated_total'),'is_demo':cost.get('is_demo',True),'limitations':cost['limitations']}}]
    if comparisons and reply['status']=='answered':
        v=comparisons[-1]
        reply['cards']=[{'type':'comparison','data':{'comparison_date':v['comparison_date'],'options':[{'exit_date':o['exit_date'],'additional_subscription_fee':o['additional_subscription_fee'],'exit_cost_total':o['exit_costs']['estimated_total'],'additional_total':o['additional_total']} for o in v['options']],'difference':v['difference'],'limitations':v['limitations'],'is_demo':True}}]
    if renewals:
        v=renewals[-1]
        reply['cards']=[{'type':'renewal_comparison','data':{'decision':v.get('decision'),'assumptions':v.get('assumptions',[]),'request':v['comparison_request'],'comparison_start':v['comparison_start'],'comparison_end':v['comparison_end'],'renewal_start':v['renewal_start'],'options':[{k:o.get(k) for k in ('choice','confirmed_subtotal','estimated_total','missing_fields','remaining_contract_months','remaining_mandatory_months','model_id','product','care_details','existing_subscription_cost','exit_cost_total','subscription_cost','initial_cost','maintenance_cost','arrears','exit_cost_items','subscription_scenario_cost','scenario_total','price_note','subscription_months','rate_segments','renewal_benefit','maximum_benefit_scenario_total','maximum_card_benefit','maximum_card_scenario_total','selected_card_benefit','selected_card_scenario_total') if k in o} for o in v['renewal_options']],'difference':v['difference'],'limitations':v['limitations'],'is_demo':True}}]
        official=[]
        for o in v['renewal_options']:
            for item in o.get('installation',{}).get('work_items',[]):
                source={'document_id':item['source_id'],'title':'LG 공식 모델별 설치 비용 안내','url':item['source_url'],'section':item['source_section'],'model_id':item['model_id'],'checked_at':item['checked_at']}
                if source not in official:official.append(source)
        if v.get('base_installation_source') and v['base_installation_source'] not in official:official.append(v['base_installation_source'])
        for o in v['renewal_options']:
            if o.get('renewal_benefit'):official.append(o['renewal_benefit']['source'])
        if any(o.get('maximum_card_benefit') for o in v['renewal_options']):official.append({'document_id':'LG-CARD-BENEFITS-20261014','title':'LG 공식 제휴카드 10종 조건','url':'https://www.lge.co.kr/care-solutions/rentalService-benefits?rental-scrvice=card-recommendation','checked_at':'2026-10-14'})
        reply['sources']+=official
        for o in v['renewal_options']:reply['sources']+=(o.get('product') or {}).get('sources',[])
    catalogs=[o for o in observations if o.get('offers') and o.get('status')=='ok']
    if catalogs and not renewals and not comparisons and (catalog_view or len({o['model_id'] for o in catalogs[-1]['offers']})>1):
        v=catalogs[-1]
        rows=[{'offer_id':o['offer_id'],'model_id':o['model_id'],'product':o.get('product'),
               'care_details':o['care_details'],'monthly_fee':o.get('display_monthly_fee') if o.get('price_is_snapshot') else o['rates'][0]['monthly_fee'],
               'rate_note':o.get('rate_note') or ' / '.join(f"{q['start_month']}~{q['end_month']}개월: 월 {q['monthly_fee']:,}원" for q in o['rates']),
               'contract_months':o['contract_months'],'mandatory_months':o['mandatory_months'],'source_kind':o['source_kind'],
               'selection_reason':o['selection_reason']} for o in v['offers']]
        reply.update(status='answered',topic='contract',answer='공식 제품 기능과 신규 구독 조건을 비교하세요. 요금은 확인일의 선택 조건이며 미래 가입 견적과 구분합니다.',missing_fields=[],brief_id=None)
        reply['cards']=[{'type':'renewal_catalog','data':{'offers':rows,'sort_by':v.get('sort_by','default'),'checked_for_date':v['checked_for_date'],'limitations':v['limitations']}}]
        reply['sources']=list({o['source_id']:{'document_id':o['source_id'],'title':'LG 공식 구독 선택 조건' if o['source_kind']=='official' else '시연용 신규 구독 조건','url':o.get('source_url'),'model_id':o['model_id'],'checked_at':o.get('source_checked_at')} for o in v['offers']}.values())
        for o in v['offers']:reply['sources']+=(o.get('product') or {}).get('sources',[])
    elif catalogs and not renewals and not comparisons:
        offer=catalogs[-1]['offers'][0]
        lines=[offer['model_id']+'의 저장된 공식 선택 조건을 확인했습니다.',offer.get('rate_note','')]
        for key,label in [('registration_fee','등록비'),('installation_fee','기본 설치비'),('other_initial_fee','기타 초기비'),('mandatory_months','의무사용기간')]:
            value=offer.get(key)
            lines.append(label+': '+('공개된 선택 조건에서 확인되지 않았습니다.' if value is None else f'{value:,}'+('개월' if key=='mandatory_months' else '원')))
        lines.append('고객이 비용을 찾아 입력할 필요는 없습니다. 현재 자료만으로 개인 가입 견적을 확정할 수 없어, 선택 모델·관리 방식·전환일에 대한 적용 조건을 상담에서 확인해야 합니다. 미확인 값을 0원으로 계산하지 않습니다.')
        reply.update(status='answered',topic='contract',answer='\n'.join(lines),cards=[],missing_fields=[],brief_id=None)
        reply['sources']=[{'document_id':offer['source_id'],'title':'LG 공식 구독 선택 조건','url':offer.get('source_url'),'model_id':offer['model_id'],'checked_at':offer.get('source_checked_at')}]
    timings=[o for o in observations if 'suggested_date' in o and o.get('status')=='ok']
    if timings and not catalogs and not renewals and not comparisons and not installations:
        v=timings[-1]
        reply.update(status='answered',topic='contract',answer=f"계약 기준 검토 후보일은 {v['suggested_date']}입니다.\n"+v['reason']+'\n'+v['limitations'],missing_fields=[],brief_id=None)
        other_cards=reply['cards'] if catalogs else []
        other_sources=reply['sources'] if catalogs else []
        reply['cards']=[{'type':'renewal_timing','data':{k:v[k] for k in ('suggested_date','mandatory_end','contract_end','reference_date','reason','limitations','is_demo') if k in v}}]+other_cards
        reply['sources']=[{'document_id':'SYNTH-CONTRACT-V2','title':'시연용 가상 계약·기간 기준'}]+other_sources
    recommendations=[o for o in observations if 'requirements' in o]
    product_rows=[p for o in observations for p in o.get('products',[]) if p.get('features')]
    if recommendations:product_rows=recommendations[-1].get('products',[])
    products=list({p['model_id']:p for p in product_rows}.values())
    from 정수기프로젝트.app.mcp.subscription.subscription_offers import demo_catalog_model_ids
    ready_models=demo_catalog_model_ids() if products else set()
    if products and not renewals and not catalogs:
        reply.update(status='answered',topic='purchase',answer='공식 모델별 스펙에서 확인한 후보 기능입니다. 설치 환경과 필요한 기능을 비교해 주세요.',missing_fields=[],brief_id=None)
        reply['cards']=[{'type':'product','data':product_card_payload(p,ready_models)} for p in products]
        reply['sources']=list({s['document_id']:s for p in products for v in ([p]+p.get('variants',[])) for s in v['sources']}.values())
        if recommendations:reply['answer']=recommendations[-1].get('message',reply['answer'])
    symptoms=[o for o in observations if o.get('status')=='ok' and 'next_steps' in o]
    if symptoms:
        v=symptoms[-1];reply.update(status='answered',topic='troubleshoot',answer='원인을 확정하지 않고 먼저 확인할 내용을 안내합니다.',missing_fields=[],brief_id=None)
        reply['cards']=[{'type':'troubleshoot','data':{k:v[k] for k in ('model_id','symptom','next_steps','checked_at','source_ids','safety_notice','limitations','is_demo')}}]
        from 정수기프로젝트.app.mcp import tools as public_tools
        flows=public_tools._load_json(public_tools.DATA_DIR/'symptom_flows.json','flows')
        reply['sources']=[{'document_id':r['source_ids'][0],'title':'LG 정수기 증상 확인 안내','url':r['source_url'],'checked_at':r['checked_at']} for r in flows if r['source_ids']==v['source_ids']]
    care_results=[o for o in observations if o.get('status')=='ok' and 'guidance' in o]
    if care_results and not products and not symptoms:
        v=care_results[-1];reply.update(status='answered',topic='care_subscription',answer=v['guidance'],missing_fields=[],brief_id=None)
        reply['cards']=[{'type':'care_subscription','data':{'model_id':v.get('model_id'),'guidance':v['guidance'],'checked_at':'2026-10-07','source_ids':[s['document_id'] for s in v['sources']],'limitations':v['limitations'],'is_demo':v['is_demo']}}]
        reply['sources']=v['sources']
    support_briefs=[o for o in observations if o.get('brief_id') and o.get('support_topic')]
    if support_briefs:
        v=support_briefs[-1];reply.update(status='brief_created',topic={'product':'purchase','care':'care_subscription','troubleshoot':'troubleshoot'}[v['support_topic']],answer='상담 준비서를 생성했습니다. 실제 접수·수리·구매 신청은 하지 않았습니다.',brief_id=v['brief_id'],missing_fields=[])
        reply['sources']=v.get('sources',[]);reply['cards']=[]
    purchase_guides=[o for o in observations if 'purchase_guidance' in o]
    if purchase_guides and not support_briefs and not renewals:
        v=purchase_guides[-1];reply.update(status='answered',topic='purchase',answer=v['purchase_guidance']+'\n'+v['limitations'],missing_fields=[],brief_id=None)
        reply['sources']=v['sources'];reply['cards']=[{'type':'purchase_method','data':{'options':v['purchase_options'],'limitations':v['limitations']}}] if v.get('purchase_options') else []
    uncertain_symptoms=[o for o in observations if o.get('status')=='unverified' and 'safety_notice' in o]
    if uncertain_symptoms and not symptoms and not products and not care_results:
        v=uncertain_symptoms[-1];reply.update(status='needs_info' if v.get('missing_fields') else 'answered',topic='troubleshoot',answer=v.get('message','검수된 증상 자료를 확인하지 못했습니다.')+'\n'+v['safety_notice'],missing_fields=v.get('missing_fields',[]),brief_id=None)
        reply['sources']=v.get('sources',[]);reply['cards']=[]
    missing_products=[o for o in observations if 'products' in o and o.get('status')=='unverified']
    if missing_products and not products and not renewals:
        v=missing_products[-1];reply.update(status='answered',topic='purchase',answer=v.get('message','현재 검수 모델에는 조건에 맞는 후보를 확인하지 못했습니다.'),missing_fields=[],brief_id=None)
        reply['cards']=[];reply['sources']=[]
    care_denials=[o for o in observations if o.get('status')=='forbidden' and o.get('required_scope')=='care_info']
    if care_denials:
        reply.update(status='needs_info',topic='care_subscription',answer='내 관리·필터 일정 조회에 추가 동의가 필요합니다. 조회 범위에서 관리 정보를 선택해 주세요.',missing_fields=['consent'],brief_id=None)
        reply['cards']=[];reply['sources']=[]
    missing_inputs=[o for o in observations if o.get('status')=='needs_info' and o.get('missing_fields')]
    if missing_inputs and not products and not symptoms and not care_results and not any(o.get('cost_items') or o.get('brief_id') for o in observations) and not renewals and not catalogs:
        v=missing_inputs[-1]
        prompt='사용 중인 정수기 모델을 알려주세요. 제공한 증상은 그대로 이어서 확인하겠습니다.' if 'model_id' in v['missing_fields'] else '현재 어떤 증상인지 알려주세요.' if 'symptom' in v['missing_fields'] else '추가 정보가 필요합니다.'
        reply.update(status='needs_info',answer=v.get('message',prompt),missing_fields=v['missing_fields'],sources=[],cards=[],brief_id=None)
    financial_feedback=[o for o in observations if o.get('_tool_name') in COST_TOOLS|{'compare_retention_renewal'}]
    if financial_feedback and financial_feedback[-1].get('status')=='needs_info' and financial_feedback[-1].get('missing_fields'):
        v=financial_feedback[-1]
        # 앞서 조회한 상품 목록이 마지막 계산의 날짜·조건 오류를 덮지 않게 한다.
        reply.update(status='needs_info',topic='contract',answer=v.get('message','계산에 필요한 정보를 확인해 주세요.'),missing_fields=v['missing_fields'],sources=[],cards=[],brief_id=None)
    # 모델의 임의 상담 권유 대신 실제 도구의 미확인 비용만 근거로 사용합니다.
    uncertain_renewal=any(any(o['estimated_total'] is None for o in v['renewal_options']) for v in renewals)
    uncertain_cost=any('cost_items' in o and o.get('estimated_total') is None and o.get('status')=='unverified' for o in observations)
    recommended=reply.get('status')=='answered' and (uncertain_renewal or uncertain_cost)
    reply['consultation_recommended']=recommended
    reply['consultation_reason']='현재 수집 요금 조건의 참고 시나리오와 미확인 가입·초기비 조건을 구분해 확인하면 선택을 비교하는 데 도움이 됩니다.' if recommended else None
    # 실제 검색된 혜택 근거는 비용/제품 카드가 답변을 재구성해도 보존합니다.
    from 정수기프로젝트.app.rag.retriever import documents as knowledge_documents, contextual_chunk
    knowledge={c['chunk_id']:c for c in knowledge_documents()}
    benefit_chunks=[]
    for observation in observations:
        for hit in observation.get('documents',[]):
            chunk=knowledge.get(hit.get('chunk_id'))
            if chunk and chunk['chunk_id']=='LG-SWITCH-conditions':
                evaluated=contextual_chunk(chunk)
                if evaluated not in benefit_chunks:benefit_chunks.append(evaluated)
    reply['benefit_guidance']='\n'.join(c['content']+'\n'+c['interpretation'] for c in benefit_chunks) or None
    for chunk in benefit_chunks:
        source={k:chunk.get(k) for k in ('document_id','title','url','section','model_id','checked_at')}
        if source not in reply['sources']:reply['sources'].append(source)
    manuals=[o for o in observations if o.get('status')=='ok' and o.get('manuals')]
    if manuals and primary in {None,'usage'}:
        reply.update(status='answered',topic='care_subscription',answer='연결된 모델의 공식 사용설명서를 확인해 보세요. 궁금한 사용 방법을 질문하면 검수된 자료 범위에서 이어서 안내할게요.',missing_fields=[],brief_id=None)
        reply['cards']=[{'type':'usage_manual','data':{**{k:v.get(k) for k in ('model_id','title','url','version','checked_at')},'limitations':o['limitations']}} for o in manuals for v in o['manuals']]
        reply['sources']=[v for o in manuals for v in o['sources']]
    channels=[o for o in observations if o.get('_tool_name')=='get_official_channel' and o.get('status')=='ok']
    for o in channels:
        reply['sources'].extend(v for v in o['sources'] if v not in reply['sources'])
    if channels and reply.get('status')=='needs_info' and reply.get('missing_fields')==['support_or_compare']:
        reply.update(cards=[],brief_id=None)  # 공식 연결 후에도 교체 고민의 다음 선택 질문을 유지
    elif channels and all(o.get('_tool_name')=='get_official_channel' for o in observations):
        reply.update(status='answered',missing_fields=[],cards=[],brief_id=None,answer='\n'.join(o['message']+' '+o['limitations'] for o in channels))
    elif channels:reply['answer']+='\n'+'\n'.join(o['message'] for o in channels)
    return AgentResult.model_validate(result)


def provider_failure(exc):
    """제공처 오류를 고정 문구로 분류. 본문·키는 로그에 남기지 않습니다."""
    for _ in range(6):
        if exc is None:break
        body=getattr(exc,'body',None)
        error=body.get('error',body) if isinstance(body,dict) else {}
        message=str(error.get('message','')).lower() if isinstance(error,dict) else ''
        code=error.get('code') if isinstance(error,dict) else None
        error_type=error.get('type') if isinstance(error,dict) else None
        if 'credit balance is too low' in message or code in {'insufficient_quota','credit_balance_exhausted'} or error_type=='insufficient_quota':
            return ModelProviderFailure('MODEL_CREDIT_EXHAUSTED','AI 모델 제공처의 사용 잔액이 부족합니다. 잔액을 충전하거나 모델 제공처 설정을 변경해 주세요.')
        status=getattr(exc,'status_code',None)
        if status==401:
            return ModelProviderFailure('MODEL_AUTH_FAILED','AI 모델 인증을 확인할 수 없습니다. 서버의 모델 API 키 설정을 확인해 주세요.')
        if status==429:
            return ModelProviderFailure('MODEL_RATE_LIMIT','AI 모델 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.')
        exc=exc.__cause__ or exc.__context__
    return None


def build_runner(model, *, plan_runner=None):
    async def run_agent(message,context):
        from langchain.agents import create_agent
        from langchain.agents.structured_output import ToolStrategy
        observations=[]
        if not context.get('product_model'):
            for entry in reversed([*context.get('history',[]),{'role':'user','content':message}]):
                if entry.get('role')!='user':continue
                text=entry.get('content','')
                try:
                    supplied=json.loads(text[text.index('{'):]).get('model_id') if '{' in text else None
                    if isinstance(supplied,str) and re.fullmatch(r'W[DSU][A-Z0-9]+',supplied):
                        context={**context,'product_model':supplied};break
                except (ValueError,TypeError,AttributeError):pass
        tool_context={**context,'turn_message':message,'brief_creation_allowed':allows_brief_creation(message,context.get('history',[]))}
        # 현재 요청·권한·고객 입력 사실만 시스템 지침에 추가합니다.
        prompt=PROMPT_PATH.read_text(encoding='utf-8')+'\n서버 기준일: '+reference_date()
        from .response_topics import customer_question
        prompt+='\n현재 고객 질문: '+customer_question(message)
        if context.get('product_model'):prompt+='\n서버에서 확인한 보유 모델: '+context['product_model']+' (신규 선택 모델과 구분하세요).'
        prompt+='\n서버 권한 연결 제공 여부: '+str(bool((context.get('tool_authorization') or {}).get('access_token')))+'. 계약 요청은 필요한 동의 범위를 도구 결과에 따라 안내합니다. 공개 제품 후보와 공식 채널에는 동의가 필요 없습니다.'
        if context.get('granted_scopes') is not None:prompt+='\n서버에서 확인한 동의 범위: '+json.dumps(context['granted_scopes'],ensure_ascii=False)+'. 범위는 도구 실행 시 다시 검증합니다. 비용 동의가 있으면 기간 조회를 선행하지 않아도 비용 도구가 필요한 계약 항목을 확인합니다.'
        if comparison_preferences(tool_context):prompt+='\n고객이 제공한 선택 입력: '+json.dumps(comparison_preferences(tool_context),ensure_ascii=False)
        kind=request_boundary(tool_context)
        reason=consultation_reason(tool_context)
        if kind:prompt+='\n서버의 요청 경계 검증 결과: '+kind+'. 수행하지 말고 이유를 짧게 설명합니다.'
        if reason=='service_dispute':prompt+='\n관리·수리 이행 분쟁 신호가 있습니다. 일반 합성 해약금을 분쟁의 최종 부담으로 적용하지 말고 약정·이행 이력과 확인할 질문을 정리하세요.'
        from .consultation_plan import ConsultationPlan, PLAN_INSTRUCTIONS
        from langsmith import tracing_context
        planning_history=[{'role':h['role'],'content':customer_question(h['content']) if h['role']=='user' else h['content']} for h in context.get('history',[]) if h.get('role') in {'user','assistant'}]
        customer_texts=[customer_question(message)]+[h['content'] for h in planning_history if h['role']=='user']
        class EvidenceCheckedPlan(ConsultationPlan):
            @model_validator(mode='after')
            def exact_customer_evidence(self):
                for evidence in (self.reason_evidence,self.selection_evidence,*self.feature_evidence.values()):
                    if evidence and not any(evidence in text for text in customer_texts):
                        raise ValueError('입력에 그대로 있는 연속 구절을 evidence에 복사하세요. 요약·바꿔쓰기는 근거로 허용하지 않습니다. 현재 고객 질문: '+customer_question(message))
                if self.requests_preferences and self.preferences_evidence and self.preferences_evidence not in customer_question(message):
                    raise ValueError('preferences_evidence는 현재 질문에 실제 존재하는 구절이어야 합니다. 과거 조건 선택 요청은 현재 후보 요청을 막지 않습니다.')
                aliases={'냉수':('냉수','찬물','차가운물','cold'),'정수':('정수','상온수','상온물'),'온수':('온수','뜨거운물','따뜻한물','hot'),'얼음':('얼음','아이스','ice')}
                for feature in self.required_features:
                    evidence=re.sub(r'\s+','',self.feature_evidence.get(feature,'')).lower()
                    if not any(word in evidence for word in aliases[feature]):
                        raise ValueError(feature+' 필수 조건의 근거 구절에 해당 기능이나 동의 표현이 없습니다. 얼음이 필요 없다는 말로 냉수·정수·온수가 필요하다고 추정하지 마세요. 명시적으로 필요하다고 말하지 않은 기능은 required_features에서 제외하세요.')
                return self
        if plan_runner:
            plan=ConsultationPlan.model_validate(await plan_runner(customer_question(message),planning_history))
        else:
            planner=create_agent(model=model,tools=[],system_prompt=PLAN_INSTRUCTIONS,response_format=ToolStrategy(EvidenceCheckedPlan))
            try:
                with tracing_context(enabled=False):
                    planned=await planner.ainvoke({'messages':[{'role':'user','content':'이전 대화 참고자료: '+json.dumps(planning_history,ensure_ascii=False)+'\n현재 질문: '+customer_question(message)}]},config={'recursion_limit':16})
                plan=planned['structured_response']
            except Exception as exc:
                logging.getLogger(__name__).warning('agent_failure trace_id=%s stage=plan error_type=%s retry_count=0',context.get('trace_id',''),type(exc).__name__)
                classified=provider_failure(exc)
                if classified:raise classified from None
                raise ToolFailure('현재 상담 목적을 확인할 수 없습니다.') from None
        customer_texts=[customer_question(message)]+[h['content'] for h in planning_history if h['role']=='user']
        if plan.reason_evidence and not any(plan.reason_evidence in text for text in customer_texts):
            raise ToolFailure('상담 이유의 고객 입력 근거를 확인할 수 없습니다.')
        if plan.selection_evidence and not any(plan.selection_evidence in text for text in customer_texts):
            raise ToolFailure('선택 조건의 고객 입력 근거를 확인할 수 없습니다.')
        if plan.purpose=='contract_fees' and context.get('granted_scopes') is not None and 'contract_costs' not in context['granted_scopes'] and not kind:
            return verified_result({'reply':{'status':'needs_info','topic':'contract','resolved_topic':'contract','answer':'월요금 안내에는 요금과 비용 정보 조회 동의가 필요해요. 이 질문에 필요한 범위에 동의하면 계약 요금표를 이어서 확인할게요.','missing_fields':['consent'],'sources':[],'cards':[]}},[],request_question=message)
        if plan.unresolved_reference and not kind:
            return verified_result({'reply':{'status':'needs_info','topic':'unknown','answer':'어떤 제품이나 작업을 말씀하시는지 알려주시겠어요?','missing_fields':['consultation_goal'],'sources':[],'cards':[]}},[],request_question=message)
        if plan.cancellation_intent in {'considering','problem'} and not kind:
            problem=plan.cancellation_intent=='problem'
            result=verified_result({'reply':{'status':'answered','topic':'contract','resolved_topic':'cancel','answer':('불편 때문에 해지를 고민하고 계시는군요. 예상 해지 비용을 확인하거나 공식 문제 해결 상담을 선택할 수 있어요.' if problem else '해지할지 고민하고 계시는군요. 어떤 점이 고민인지 알려주시면 그에 맞는 방법을 안내할게요. 이유를 답하지 않고 예상 해지 비용부터 확인하셔도 괜찮아요.'),'missing_fields':[],'sources':[],'cards':[]}},[],request_question=message)
            from .next_actions import answer_actions
            result.reply.next_actions=answer_actions(plan.purpose,result.reply,plan.cancellation_intent)
            return result
        if plan.requests_preferences and not kind:
            return verified_result({'reply':{'status':'needs_info','topic':'contract','resolved_topic':'renewal','answer':'새 모델에서 원하는 기능과 설치·관리 조건을 선택해 주세요. 미정인 항목은 그대로 둘 수 있어요.','missing_fields':['renewal_preferences'],'sources':[],'cards':[]}},[],request_question=message)
        if plan.needs_renewal_reason and not kind:
            return verified_result({'reply':{'status':'needs_info','topic':'contract','resolved_topic':'renewal','answer':'정수기를 바꾸려는 가장 큰 이유가 무엇인가요?','missing_fields':['renewal_reason'],'sources':[],'cards':[]}},[],request_question=message)
        if plan.purpose in {'renewal','contract_reference'} and plan.renewal_reason=='contract_confusion' and not plan.asks_specific_contract_question and not plan.explains_contract_period_difference and not plan.requests_candidates and not plan.requests_timing and not plan.requires_renewal_calculation and not plan.specific_selection and not comparison_preferences(tool_context).get('offer_id') and not kind:
            return verified_result({'reply':{'status':'needs_info','topic':'contract','resolved_topic':'contract','answer':'계약 조건 때문에 교체를 고민하고 계시는군요. 어떤 부분이 헷갈리는지 선택하면 그 내용부터 쉽게 설명해 드릴게요.','missing_fields':['contract_question'],'sources':[],'cards':[]}},[],request_question=message)
        tool_context={**tool_context,'consultation_plan':plan.model_dump()}
        tools=await make_tools(tool_context,observations)
        prompt+='\n같은 LLM이 확인한 현재 상담 목적과 고객 입력 근거: '+json.dumps(plan.model_dump(),ensure_ascii=False)+'. 이 목적의 과제만 처리하며 과거 요청을 추가 실행하지 않습니다.'
        class CheckedDecision(ModelDecision):
            @model_validator(mode='after')
            def support_channel_evidence(self):
                try:
                    if plan.cancellation_intent=='decided' and plan.purpose=='exit_cost' and not kind:
                        if self.primary_task=='renewal' or any(f in self.missing_fields for f in ('renewal_reason','renewal_preferences','offer_id','support_or_compare')):
                            raise ValueError('현재 고객은 해지 의사를 밝혔습니다. 교체 이유·제품 선택을 요구하지 말고 예상 정산을 확인하거나 필요한 권한만 요청하세요.')
                        if self.status=='answered' and consultation_reason(context)!='service_dispute' and not any(o.get('_tool_name')=='assess_contract_document_costs' and o.get('status') in {'ok','unverified'} for o in observations):
                            raise ValueError('해지 비용 안내는 실제 정산 도구 결과가 필요합니다. 이유 질문·새 모델 추천으로 대체하지 마세요.')
                    if plan.explains_contract_period_difference and self.status=='answered' and not kind:
                        if self.answer.count('\n')<2:
                            raise ValueError('두 용어를 각각 굵은 제목의 별도 항목으로 나누고 관계를 마지막 한 문장으로 설명하세요. 한 문단에 합치지 마세요.')
                        if plan.requires_contract_period_example:
                            rows=[o for o in observations if o.get('_tool_name')=='lookup_contract_document' and o.get('status')=='ok' and o.get('terms')]
                            if not rows:raise ValueError('내 계약 기준의 차이를 요청했습니다. 계약 조회로 실제 두 종료일을 확인하거나 필요한 동의를 안내하세요.')
                            if any(str(rows[-1]['terms'][key]) not in self.answer for key in ('mandatory_end','contract_end')):
                                raise ValueError('개념 설명과 함께 조회한 두 종료일을 YYYY-MM-DD로 각각 표시하세요: 의무사용 종료일 '+str(rows[-1]['terms']['mandatory_end'])+', 전체 계약 종료일 '+str(rows[-1]['terms']['contract_end']))
                    if plan.purpose=='contract_reference' and not kind and self.status=='answered' and not any(o.get('_tool_name')=='search_contract_knowledge' and o.get('documents') for o in observations):
                        raise ValueError('일반 계약 개념·공식 조건 설명에는 search_contract_knowledge로 조회한 근거가 필요합니다. 모델 기억만으로 답하지 말고 공개 자료를 검색한 뒤 고객 질문에 맞춰 설명하세요.')
                    if plan.purpose=='contract_reference' and not plan.requires_contract_period_example and self.status=='needs_info' and 'consent' in self.missing_fields and not kind:
                        raise ValueError('공개 계약·혜택 근거 질문은 개인 조회 동의가 필요하지 않습니다. 공개 검색 결과로 설명하거나 실제로 부족한 질문 내용을 확인하세요.')
                    if plan.purpose=='contract_fees' and self.status=='answered' and not any(o.get('_tool_name')=='lookup_contract_document' and o.get('status')=='ok' for o in observations):
                        raise ValueError('현재 과제의 월요금은 계약 조회 결과가 있어야 설명할 수 있습니다. 요금 정보를 조회하거나 필요한 동의를 안내하세요.')
                    if plan.purpose=='date_comparison' and self.status=='answered' and not kind and consultation_reason(context)!='service_dispute' and not any(o.get('_tool_name')=='compare_contract_options' and o.get('status') in {'ok','unverified'} for o in observations):
                        raise ValueError('두 날짜의 부담 비교는 compare_contract_options 결과가 필요합니다. 한 날짜 정산을 두 번 실행한 결과에는 날짜 사이 이용요금이 빠질 수 있으므로 비교 완료로 답하지 마세요. 필요한 동의나 날짜가 없으면 먼저 확인하세요.')
                    if plan.requests_candidates and plan.reason_response_completed and self.status=='answered' and not kind and not any(o.get('_tool_name')=='lookup_subscription_offers' and o.get('status')=='ok' and o.get('offers') for o in observations):
                        raise ValueError('교체 이유에 대한 안내를 마친 후 후보를 요청했습니다. lookup_subscription_offers로 후보를 조회하세요. 이유·조건 설명으로 되돌아가지 마세요.')
                    if plan.requires_renewal_calculation and self.status=='answered' and not any(o.get('_tool_name')=='compare_retention_renewal' and o.get('status') in {'ok','unverified'} for o in observations):
                        raise ValueError('선택한 새 상품의 카드 혜택·기간 부담 비교를 요청했습니다. compare_retention_renewal을 실제 실행해야 합니다. 검색 문구나 상품 요금만으로 비교 완료라고 답하지 마세요. 정보가 부족하면 필요한 동의/선택 조건을 요청하세요.')
                    support_reply=self.primary_task in {'usage','troubleshoot'} or 'support_or_compare' in self.missing_fields
                    if support_reply and not any(o.get('_tool_name')=='get_official_channel' and o.get('status')=='ok' for o in observations):
                        raise ValueError('사용 오류·조작 안내에는 공식 채널 조회 결과가 필요합니다. get_official_channel(purpose="support")을 실제 실행한 뒤 답하세요. 진단이나 실행 약속만 반환하지 마세요.')
                    if self.primary_task=='renewal' and self.status=='answered' and not any(o.get('status') in {'ok','unverified'} and (o.get('offers') or o.get('renewal_options') or o.get('products') or o.get('brief_id') or o.get('suggested_date')) for o in observations):
                        raise ValueError('재구독 후보·비교의 완료 응답에는 실제 후보/비교 도구 결과가 필요합니다. 충분한 정보가 있으면 적절한 도구를 실행하고, 부족하면 needs_info로 질문하세요. 실행 계획만 반환하지 마세요.')
                    return self
                except ValueError as exc:
                    logging.getLogger(__name__).warning('agent_failure trace_id=%s stage=response_validation error_type=%s retry_count=agent_managed',context.get('trace_id',''),type(exc).__name__)
                    raise
        CheckedDecision.__name__='ModelDecision'
        agent=create_agent(model=model,tools=tools,system_prompt=prompt,response_format=ToolStrategy(CheckedDecision))
        from langchain_core.prompts import ChatPromptTemplate
        history=[{'role':h['role'],'content':customer_question(h['content']) if h['role']=='user' else h['content']} for h in context.get('history',[]) if h.get('role') in {'user','assistant'}]
        template=ChatPromptTemplate.from_messages([
            ('human','이전 대화 참고자료입니다. 과거 질문을 다시 실행하지 말고 선택한 날짜·상품 등 현재 요청에 필요한 맥락만 참고하세요.\n{history_context}'),
            ('human','현재 처리할 고객 요청은 다음 질문 하나입니다. 이전 질문을 함께 처리하지 마세요.\n{question}'),
        ])
        messages=template.format_messages(history_context=json.dumps(history,ensure_ascii=False),question=customer_question(message))
        from langsmith import tracing_context
        try:
            with tracing_context(enabled=False):
                result=await agent.ainvoke({'messages':messages},config={'recursion_limit':20})
        except Exception as exc:
            logging.getLogger(__name__).warning('agent_failure trace_id=%s stage=agent_or_response_validation error_type=%s tools=%s retry_count=0',context.get('trace_id',''),type(exc).__name__,','.join(o.get('_tool_name','') for o in observations))
            classified=provider_failure(exc)
            if classified:raise classified from None
            from langgraph.errors import GraphRecursionError
            evidence=any(o.get('status') in {'ok','unverified'} and any(bool(o.get(k)) for k in ('terms','suggested_date','renewal_options','cost_items','products','documents','guidance')) for o in observations)
            denied=any(o.get('status') in {'forbidden','error'} for o in observations)
            if isinstance(exc,GraphRecursionError) and evidence and not denied and not all(o.get('terms') for o in observations):
                # 호출은 모델이 수행했다. 반복 한도에서 이미 실행한 검증 결과만 정리한다.
                fallback={'reply':{'status':'answered','topic':'contract','answer':'확인한 결과를 안내합니다.','sources':[],'cards':[],'missing_fields':[]}}
                result=verified_result(fallback,observations,(context.get('tool_authorization') or {}).get('access_token',''))
                from .response_topics import response_route
                result.reply.resolved_topic=response_route(message,result.reply,observations)
                return result
            raise ToolFailure('LangChain Agent 실행을 확인할 수 없습니다.') from None
        if 'structured_response'not in result:raise ToolFailure('구조화 응답이 없습니다.')
        decision=result['structured_response']
        if isinstance(decision,ModelDecision):
            values=decision.model_dump();primary=values.pop('primary_task',None)
            decision={'reply':{**values,'resolved_topic':primary,'sources':[],'cards':[]}}
        if plan.purpose=='renewal' and plan.requests_candidates:
            decision['reply']['resolved_topic']='renewal'
        if plan.purpose=='renewal' and plan.renewal_reason=='problem' and not plan.support_comparison_chosen and not (plan.requests_candidates and plan.reason_response_completed) and not plan.specific_selection and any(o.get('_tool_name')=='get_official_channel' and o.get('status')=='ok' for o in observations):
            decision['reply'].update(status='needs_info',resolved_topic='renewal',missing_fields=['support_or_compare'])
        if kind:
            decision={'reply':boundary_reply(kind)};observations=[]
        details_question=bool(re.search(r'등록비|기본 설치비|기타 초기비|의무사용기간',message) and not re.search(r'목록|후보',message))
        verified=verified_result(decision,observations,(context.get('tool_authorization') or {}).get('access_token',''),catalog_view=not details_question,prefer_knowledge=bool((re.search(r'관리|서비스',message) and re.search(r'자동|연장|종료|끝나',message)) or re.search(r'차이|의무기간이 끝나도|의무사용기간이 끝나도',message)),request_question=message)
        if re.search(r'자가관리|방문관리',message) and re.search(r'마음대로|임의로.*확정',message):
            verified.reply.status='answered';verified.reply.topic='care_subscription'
            verified.reply.answer='확인되지 않은 관리 방식을 임의로 확정해 추천할 수 없습니다. 기능 지원과 방문·자가관리 제공 여부는 별개입니다. 확인된 모델별 관리 조건만 안내하며, 자료에 없는 조건은 가입 가능한 관리 방식으로 확정하지 않습니다.'
            verified.reply.cards=[];verified.reply.sources=[];verified.reply.missing_fields=[]

        from .response_topics import response_route
        verified.reply.resolved_topic=decision.get('reply',{}).get('resolved_topic') or response_route(message,verified.reply,observations)
        if verified.reply.resolved_topic in {'usage','troubleshoot'}:verified.reply.benefit_guidance=None

        read_only_support=verified.reply.resolved_topic in {'usage','features','troubleshoot','care','contract','product_information'} and not re.search(r'교체|바꾸|재구독|해지|위약금|비용|exit_reason|service_history|변경.*이유',message)
        # 교체 배경이 포함돼도 명시한 모델의 공개 기능 조회 결과를 이유 질문으로 덮지 않습니다.
        explicit_product_lookup=bool(re.search(r'W[DSU][A-Z0-9]+',message,re.I) and re.search(r'기능|지원|사용법|사용 방법',message) and any(o.get('_tool_name')=='lookup_product_features' and o.get('products') for o in observations) and not any(o.get('_tool_name') in FINANCIAL_TOOLS for o in observations) and not re.search(r'exit_reason|service_history|변경.*이유',message))
        policy=reason_response_override(tool_context) if reason=='service_dispute' and not kind and not(read_only_support or explicit_product_lookup) else None
        if policy and verified.reply.status!='brief_created':
            payload=verified.model_dump(mode='json');payload['reply'].update(status=policy['status'],topic='contract',answer=policy['message'],missing_fields=policy['missing_fields'],brief_id=None)
            verified=AgentResult.model_validate(payload)
        if {'renewal_timing','renewal_catalog'}.issubset({c.type for c in verified.reply.cards}):
            verified.reply.answer+='\n아래 후보 목록에서 관심 제품을 선택하면, 확인한 시점 후보를 기준으로 현재 제품 유지와 전환 조건을 비교할 수 있어요.'
        compact=re.sub(r'\s+','',customer_question(message))
        chooses_keep=bool(re.search(r'계속(?:사용|쓸)|유지할|그대로쓸',compact))
        reported_improvement=bool(re.search(r'정상|괜찮|온수가나와|냉수가나와|다시나와|해결됐|해결되|불편이사라',compact)) and not re.search(r'안나|나오지않|해결되지|여전히',compact)
        if chooses_keep and reported_improvement and not re.search(r'교체|재구독|해지|준비서|요약',compact) and verified.reply.status=='answered':
            verified.reply.answer='제품 상태가 나아졌다는 말씀과 계속 사용하려는 뜻을 확인했습니다. 이 대화만으로 고장 원인을 단정하지는 않겠습니다. 다시 불편이 생기면 현재 증상을 알려주세요.'
            verified.reply.cards=[];verified.reply.sources=[];verified.reply.benefit_guidance=None
        from .next_actions import answer_actions
        verified.reply.next_actions=answer_actions(plan.purpose,verified.reply,plan.cancellation_intent)
        return verified
    return run_agent


def model_settings():
    """설정한 제공처만 사용합니다. 잔액·오류를 이유로 다른 제공처로 자동 전환하지 않음."""
    provider=os.environ.get('LLM_PROVIDER','anthropic').strip().lower()
    if provider not in {'anthropic','openai'}:
        raise ValueError('LLM_PROVIDER는 anthropic 또는 openai여야 합니다.')
    key_name='ANTHROPIC_API_KEY' if provider=='anthropic' else 'OPENAI_API_KEY'
    model_name=os.environ.get('LLM_MODEL','').strip() or os.environ.get('ANTHROPIC_MODEL' if provider=='anthropic' else 'OPENAI_MODEL','').strip()
    if not model_name:
        model_name='claude-haiku-4-5-20251001' if provider=='anthropic' else 'gpt-4.1-mini'
    return provider,model_name,key_name


def configured_runner():
    provider,model_name,key_name=model_settings()
    if not os.environ.get(key_name):return None
    from langchain.chat_models import init_chat_model
    kwargs={'temperature':0,'max_tokens':1600,'max_retries':1,'api_key':os.environ[key_name]}
    if provider=='openai':kwargs['store']=False
    model=init_chat_model(model_name,model_provider=provider,**kwargs)
    return build_runner(model)
