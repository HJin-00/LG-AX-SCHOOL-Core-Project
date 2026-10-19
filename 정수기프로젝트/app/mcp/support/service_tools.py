"""한 Agent의 구매·공개 관리·개인 일정·상담 준비 기능."""
import csv
from pathlib import Path
from 정수기프로젝트.app.consent import ConsentStore, ConsentDenied
from 정수기프로젝트.app.mcp.contracts.protected_tools import denied_result
from 정수기프로젝트.app.mcp import tools

CARE_SOURCE={'document_id':'LG-CARE-FAQ','title':'LG 정수기 관리·구매 FAQ','url':'https://www.lge.co.kr/story/faq/water-purifiers-faq','checked_at':'2026-10-07'}


def recommend_water_purifier(required_features=None,installation_type='any'):
    requirements=required_features or []
    allowed={'냉수','온수','정수','얼음','클린세척수','ThinQ'}
    if not isinstance(requirements,list) or not set(requirements)<=allowed or installation_type not in {'any','desk','built_in','stand'}:
        return {'status':'needs_info','missing_fields':['required_features'],'products':[]}
    available_models=tools.candidate_model_ids()
    models=[p['model_id'] for p in tools._load_json(tools.DATA_DIR/'products.json','products') if p['model_id'] in available_models]
    result={'status':'ok','products':[]}
    for n in range(0,len(models),4):result['products']+=tools.lookup_product_features(models[n:n+4]).get('products',[])
    if result['status']=='error':return result
    candidates=[]
    for p in result['products']:
        if any(p['features'].get(k) is not True for k in requirements):continue
        kind=p['features']['설치 유형']
        if installation_type=='desk' and kind!='데스크형':continue
        if installation_type=='built_in' and kind!='언더싱크형':continue
        if installation_type=='stand' and kind!='스탠드형':continue
        candidates.append(p)
    from .product_variants import group_products
    candidates=group_products(candidates)
    labels={'any':'설치 형태 미지정','desk':'데스크형','built_in':'언더싱크형','stand':'스탠드형'}
    basis=('필수 기능: '+', '.join(requirements) if requirements else '필수 기능 미지정')+' / '+labels[installation_type]
    message=f'구매 불가로 표시되지 않은 검수 모델 {len(models)}개에서 {basis} 조건에 맞는 {len(candidates)}개 중 최대 8개를 제품군별 모델명 순으로 보여드려요. 색상만 다른 검수 모델은 한 카드로 묶었어요. 인기·저가·맞춤 점수 순위는 아니에요.'
    if not requirements and installation_type=='any':message+=' 아직 선호 조건이 없어 기본 후보 목록입니다. 꼭 필요한 기능은 냉수·온수·얼음 중 어떤 것인가요?'
    return {'status':'ok' if candidates else 'unverified','products':candidates[:8],'candidate_count':len(candidates),'catalog_count':len(models),'requirements':requirements,
            'selection_basis':basis,'ordering':'model_id_ascending','personalized':bool(requirements or installation_type!='any'),
            'message':message if candidates else '현재 검수 모델에 해당 조건을 만족하는 후보가 없습니다.'}


def lookup_care_guidance(model_id='',question=''):
    if model_id and model_id not in {'WD520VCT','WU923AWB'}:
        return {'status':'unverified','message':'해당 모델의 관리 자료는 아직 검수하지 않았습니다.'}
    return {'status':'ok','model_id':model_id or None,'guidance':'방문관리와 자가관리의 제공 범위·필터 종류와 교체 주기는 모델 및 계약 조건에 따라 다릅니다. 해당 모델 설명서와 관리 계약을 확인하세요. 개인 방문·배송 일정은 별도 동의 후 조회합니다.',
            'sources':[CARE_SOURCE],'is_demo':False,'limitations':'공개 관리 안내이며 개인 일정 변경·수질 안전 판정은 하지 않습니다.'}


def lookup_care_schedule(session_id,access_token):
    try:profile=ConsentStore().authorize(session_id,access_token,'care_info')
    except ConsentDenied as exc:return denied_result(exc)
    p=Path(__file__).parent.parent/'data/billing_v2.csv'
    try:
        with p.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
        row=next(r for r in rows if r['customer_id']==profile['demo_customer_id'])
        return {'status':'ok','model_id':profile['product_model'],'guidance':f"관리 방식: {profile['care_mode'] or '확인 필요'}. 다음 방문: {row['next_service_date'] or '확인 필요'}. 필터 일정: {row['next_filter_due'] or '확인 필요'}.",'is_demo':True,
                'sources':[{'document_id':'SYNTH-CARE-V1','title':'시연용 관리·배송 일정'}],'limitations':'가상 일정 조회이며 실제 LG 예약·일정 변경·배송 요청은 하지 않습니다.'}
    except (OSError,KeyError,StopIteration):return {'status':'error','code':'CARE_DATA_INVALID'}


def create_support_brief(session_id,access_token,topic,model_id='',symptom='',symptom_types=None):
    try:profile=ConsentStore().authorize(session_id,access_token,'care_info' if topic=='care' else 'contract_terms')
    except ConsentDenied as exc:return denied_result(exc)
    model=model_id or profile['product_model'];facts=[];missing=[];ids=[]
    summary='상담을 위한 검수 자료 요약. 실제 신청·접수·수리는 진행되지 않았습니다.'
    if topic=='care':
        result=lookup_care_schedule(session_id,access_token)
        if result['status']!='ok':return result
        facts=[result['guidance']];ids=[s['document_id'] for s in result['sources']]
    elif topic=='troubleshoot':
        result=tools.assess_symptom_next_step(model,symptom,symptom_types=symptom_types)
        if result['status']!='ok':return result
        facts=[f'사용 중인 모델: {model}',f'고객이 설명한 증상: {symptom}',*result['next_steps']];ids=result['source_ids'];missing=['증상이 계속되는지와 서비스 점검이 필요한지 확인해 주세요.']
        summary=f'{model} 사용 중 {symptom} 문제가 있어요. 안내받은 확인 사항을 기준으로 증상 지속 여부와 필요한 점검을 상담하고 싶어요.'
    elif topic=='product':
        result=tools.lookup_product_features([model])
        if not result.get('products'):return result
        p=result['products'][0];facts=[f'{k}: {v}' for k,v in p['features'].items()];ids=[s['document_id'] for s in p['sources']];missing=['최신 가격·설치 환경·구매/구독 조건']
    else:return {'status':'needs_info','missing_fields':['brief_topic']}
    sources=result.get('sources',[])
    if topic=='product':sources=p['sources']
    if topic=='troubleshoot':
        rows=tools._load_json(tools.DATA_DIR/'symptom_flows.json','flows')
        sources=[{'document_id':r['source_ids'][0],'title':'LG 정수기 증상 확인 안내','url':r['source_url'],'checked_at':r['checked_at']} for r in rows if r['source_ids']==ids]
    brief=tools.create_consultation_brief(summary,facts,missing,ids)
    if brief['status']!='ok':return brief
    try:ConsentStore().register_brief(brief['brief_id'],session_id,access_token,brief['absolute_path'])
    except Exception:
        Path(brief['absolute_path']).unlink(missing_ok=True);return {'status':'error','code':'BRIEF_REGISTER_FAILED'}
    brief.pop('absolute_path',None)
    return {**brief,'status':'ok','source_ids':ids,'is_demo':topic=='care','support_topic':topic,'sources':sources}


def explain_purchase_subscription():
    return {'status':'ok','purchase_guidance':'구매는 제품 결제금액과 별도 케어십 비용을, 구독은 계약기간 동안의 월요금과 포함 관리 범위를 함께 확인합니다. 표시 월요금만으로 유리한 선택을 단정하지 않습니다.',
            'purchase_options':[
                {'name':'일시불 구매','payment':'회원할인가·쿠폰·결제일 할인 조건을 확인합니다. 최대혜택가는 실제 결제금액과 구분합니다.','care':'현재 검수된 두 제품의 공식 구매 페이지는 케어십 가입을 필수로 안내합니다. 케어십 요금·방문주기는 제품 결제금액과 별도로 확인합니다.','period':'제품 구매 조건과 케어십 약정을 각각 확인합니다.','suitable':'제품을 구매하고 이후 관리 서비스를 별도로 선택·확인하려는 경우 검토합니다.'},
                {'name':'신규 구독','payment':'계약기간·관리 방식에 따른 월요금과 초기비용·혜택 조건을 확인합니다. 시작 월요금이 전체 기간 동안 동일하다고 가정하지 않습니다.','care':'월요금에 포함된 방문관리·필터 제공 범위를 계약별로 확인합니다.','period':'의무사용기간·전체 계약기간·종료 후 소유권·중도해지 조건을 확인합니다.','suitable':'초기 지출과 관리 서비스 포함 조건을 함께 살펴보려는 경우 검토합니다.'}],
            'sources':[{'document_id':'LG-SUB','title':'LG 가전 구독 서비스 안내','url':'https://www.lge.co.kr/home_app_subscribe/service_info','checked_at':'2026-10-07'},
                       {'document_id':'LG-PRODUCT-WD520VCT','title':'WD520VCT 공식 구매·케어십 안내','url':'https://www.lge.co.kr/product/water-purifiers/wd520vct','checked_at':'2026-10-07'},
                       {'document_id':'LG-PRODUCT-WU923AWB','title':'WU923AWB 공식 구매·케어십 안내','url':'https://www.lge.co.kr/product/water-purifiers/wu923awb','checked_at':'2026-10-07'}],
            'limitations':'개인 견적이나 총비용 계산은 아닙니다. 모델·이용 기간·구매 케어십 요금·구독 조건을 같은 기준으로 확인해야 금액을 비교할 수 있습니다.'}


def lookup_usage_manual(model_id):
    """검수된 모델 연결 설명서 주소를 조회. 원문 사용 장을 임의로 승인하지 않는다."""
    path=Path(__file__).parent.parent/'data/usage_manuals.csv'
    with path.open(encoding='utf-8-sig',newline='') as file:
        row=next((r for r in csv.DictReader(file) if r['model_id']==model_id),None)
    if not row:
        return {'status':'needs_info' if not model_id else 'unverified','missing_fields':['model_id'] if not model_id else [],'manuals':[],'message':'사용 중인 모델을 확인해야 해당 설명서를 안내할 수 있어요.'}
    return {'status':'ok','manuals':[row],'model_id':model_id,
            'sources':[{'document_id':row['document_id'],'title':row['title'],'url':row['url'],'model_id':model_id,'checked_at':row['checked_at']}],
            'limitations':'모델 연결을 확인한 공식 원문 주소입니다. 저장 시점의 판본이며 최신 여부를 보장하지 않습니다. 사용 장 전체를 검수한 답변은 아니므로 원문에 없는 버튼 순서·설정 값을 생성하지 않습니다.'}
