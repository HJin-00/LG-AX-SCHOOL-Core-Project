"""계약 상담 FastMCP: 조회·정산·시점 비교·상담 준비와 공식 채널 연결."""
import sys
from pathlib import Path
from typing import Annotated, Literal
from pydantic import Field, BaseModel, ConfigDict
from fastmcp import FastMCP
try:
    from 정수기프로젝트.app.mcp.contracts import protected_tools
except ImportError:
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from 정수기프로젝트.app.mcp.contracts import protected_tools
from 정수기프로젝트.app.mcp import tools
from 정수기프로젝트.app.mcp.contracts import contract_documents
from 정수기프로젝트.app.rag.retriever import search_contract_knowledge as search_knowledge
mcp=FastMCP("water-contract-consultation",instructions="본인 계약의 기간·정산·날짜별 부담을 확인하는 상담 도구. 선택은 LLM, 동의 검증은 서버. 실제 해지·결제·예약·LG 고객조회는 수행하지 않습니다.")

class InstallationConditions(BaseModel):
    """고객이 확인한 설치 환경만 입력한다. 미확인은 unknown이다."""
    model_config=ConfigDict(extra='forbid')
    drilling_needed: Literal['yes','no','unknown']=Field(default='unknown', description='상판 타공 필요 여부. 고객이 모르면 unknown.')
    pump_needed: Literal['yes','no','unknown']=Field(default='unknown', description='추가 펌프 필요 여부. 고객이 모르면 unknown.')
    breaker_needed: Literal['yes','no','unknown']=Field(default='unknown', description='차단기 필요 여부. 고객이 모르면 unknown.')
    outlet_needed: Literal['yes','no','unknown']=Field(default='unknown', description='전기 콘센트 추가 필요 여부. 고객이 모르면 unknown.')
    external_outlet_drilling: Literal['yes','no','unknown']=Field(default='unknown', description='외부 출수구 타공 필요 여부. 고객이 모르면 unknown.')
    external_water_drilling: Literal['yes','no','unknown']=Field(default='unknown', description='외부 급수 타공 필요 여부. 고객이 모르면 unknown.')
    thick_sink: Literal['yes','no','unknown']=Field(default='unknown', description='두꺼운 상판 조건 여부. 고객이 모르면 unknown.')
    surface_material: Literal['artificial','natural','ceramic','unknown']=Field(default='unknown',description='상판 재질: 인조석/천연석/세라믹/미확인.')


def _conditions(value):
    return value.model_dump(exclude_unset=True) if isinstance(value,InstallationConditions) else value




@mcp.tool
def search_contract_knowledge(query: Annotated[str, Field(description='고객의 현재 질문과 필요한 근거. 사용법 검색은 대상 모델을 포함합니다.')], limit: Annotated[int, Field(description='검색할 근거 수.')] = 3, purpose: Annotated[str, Field(description='검수 문서 적용 목적. 서버가 검색 범위에 맞게 설정.')] = 'consultation_reference', model_id: Annotated[str, Field(description='현재 문의 대상 모델. 내 제품과 신규 선택 모델을 구분합니다.')] = '') -> dict:
    """호출: 공개 계약·관리 약정·신규 구독 조건 근거를 찾을 때.
    제외: 개인 계약 조회·요금 계산은 해당 계약 도구 사용.
    입력: query에 질문 목적·모델을 포함, limit은 검색 수.
    결과: 승인 문서 청크·출처·적용 범위. 공개 자료는 키워드와 로컬 벡터 검색을 함께 사용.
    제한: 동의 불필요. 사양을 버튼 사용법으로 해석하거나 공개 요율을 합성 계산에 적용하지 않음.
    """
    return search_knowledge(query, limit, purpose, model_id)


@mcp.tool
def lookup_product_features(model_ids: Annotated[list[str], Field(min_length=1,max_length=8,description="조회할 서로 다른 모델 ID 1~8개. 보유 모델과 신규 후보를 구분합니다.")], feature_query: Annotated[str, Field(description='고객의 현재 질문과 필요한 근거. 사용법 검색은 대상 모델을 포함합니다.')] = "") -> dict:
    """호출: 지정한 모델의 사양·가격·혜택을 조회하거나 비교할 때.
    제외: 사용법은 search_contract_knowledge, 오류는 assess_symptom_next_step.
    입력: model_ids는 중복 없는 1~8개 모델, feature_query는 관심 기능.
    결과: 모델별 기능·이미지·가격·조건부 혜택·출처.
    제한: 미등록 모델 추정 금지. 조작 순서·점검 절차는 제공하지 않음.
    """
    return tools.lookup_product_features(model_ids, feature_query)


@mcp.tool
def lookup_contract_document(session_id: Annotated[str, Field(description='서버가 주입하는 세션. 모델 입력에서 제외.')] = '', access_token: Annotated[str, Field(description='서버가 주입하는 권한. 모델 입력에서 제외.')] = '') -> dict:
    """호출: 본인 계약 시작·의무사용 종료·전체 종료·조건을 확인할 때.
    제외: 단일 정산은 assess_contract_document_costs, 두 날짜 부담은 compare_contract_options.
    입력: 세션·권한은 서버가 연결한 고객 값.
    결과: 모델·기간. 비용 동의가 있으면 월요금·정산 조건 추가.
    제한: contract_terms 동의 필요. 개인정보·원문 제외. 구독이 없으면 not_applicable.
    """
    return contract_documents.lookup_contract_document(session_id, access_token)


@mcp.tool
def assess_contract_document_costs(session_id: Annotated[str, Field(description='서버가 주입하는 세션. 모델 입력에서 제외.')] = '', access_token: Annotated[str, Field(description='서버가 주입하는 권한. 모델 입력에서 제외.')] = '', exit_date: Annotated[str, Field(description='고객이 지정한 단일 해지 검토일 YYYY-MM-DD.')] = '') -> dict:
    """호출: 고객이 지정한 한 날짜의 해지 정산을 확인할 때.
    제외: 두 날짜 추가 부담은 compare_contract_options, 신규 모델 교체는 compare_retention_renewal.
    입력: exit_date는 고객의 YYYY-MM-DD. 없으면 질문, 권한은 서버 주입.
    결과: 위약금·수거비·할인반환금·미납의 정산 예상액.
    제한: 계약기간+비용 동의 필요. 날짜까지 추가 구독료는 포함하지 않음. 일반 구매 적용 제외, 종료 후 미납도 정산.
    """
    return contract_documents.assess_contract_document_costs(session_id, access_token, exit_date)


@mcp.tool
def compare_contract_options(session_id: Annotated[str, Field(description='서버가 주입하는 세션. 모델 입력에서 제외.')] = '', access_token: Annotated[str, Field(description='서버가 주입하는 권한. 모델 입력에서 제외.')] = '', exit_date_a: Annotated[str, Field(description='고객이 비교하려는 첫 번째 해지일 YYYY-MM-DD.')] = '', exit_date_b: Annotated[str, Field(description='고객이 비교하려는 두 번째 해지일 YYYY-MM-DD.')] = '', comparison_date: Annotated[str, Field(description='비교 기준일. 미지정이면 빈 문자열로 서버 청구 기준일 사용.')] = '') -> dict:
    """호출: 두 해지 날짜 중 추가 부담을 비교할 때.
    제외: 신규 상품 교체는 compare_retention_renewal. 단일 정산 도구 두 번으로 대체하지 않음.
    입력: exit_date_a/b는 고객 날짜, comparison_date를 비우면 청구 기준일 사용.
    결과: 날짜까지 추가 구독료+각 해지 정산, 부담 차이.
    제한: 비용 동의 필요. 이미 납부한 당월 요금 제외. 납부 미확인 시 확정 금지.
    """
    return contract_documents.compare_contract_options(session_id, access_token, exit_date_a, exit_date_b, comparison_date)


@mcp.tool
def create_contract_document_brief(session_id: Annotated[str, Field(description='서버가 주입하는 세션. 모델 입력에서 제외.')] = '', access_token: Annotated[str, Field(description='서버가 주입하는 권한. 모델 입력에서 제외.')] = '', exit_date: Annotated[str, Field(description='고객이 지정한 단일 해지 검토일 YYYY-MM-DD.')] = '', exit_date_a: Annotated[str, Field(description='고객이 비교하려는 첫 번째 해지일 YYYY-MM-DD.')] = '', exit_date_b: Annotated[str, Field(description='고객이 비교하려는 두 번째 해지일 YYYY-MM-DD.')] = '', comparison_date: Annotated[str, Field(description='비교 기준일. 미지정이면 빈 문자열로 서버 청구 기준일 사용.')] = '') -> dict:
    """호출: 고객이 기간·해지 정산·두 날짜 비교를 파일로 요청할 때.
    제외: 신규 비교 파일은 create_renewal_brief, 제품·관리·오류는 create_support_brief.
    입력: 기간만이면 날짜 생략. 단일 exit_date 또는 두 날짜+comparison_date 중 한 범위.
    결과: 결과 재검증 후 고객용 파일·등록 ID.
    제한: 명시적 생성 요청·해당 조회 동의 필요. 실제 접수·해지·결제 아님.
    """
    return contract_documents.create_contract_document_brief(session_id, access_token, exit_date, exit_date_a, exit_date_b, comparison_date)


@mcp.tool
def compare_retention_renewal(session_id: Annotated[str, Field(description='서버가 주입하는 세션. 모델 입력에서 제외.')] = '', access_token: Annotated[str, Field(description='서버가 주입하는 권한. 모델 입력에서 제외.')] = '', offer_id: Annotated[str, Field(description='고객이 선택한 상품 ID. 임의 생성 금지.')] = '', comparison_date: Annotated[str, Field(description='비교 기준일. 미지정이면 빈 문자열로 서버 청구 기준일 사용.')] = '', comparison_months: Annotated[int, Field(description='동일 기준 비교 기간(개월). 기본 36은 참고 비교.')] = 36, maintenance_monthly_fee: Annotated[int | None, Field(description='고객이 실제 확인한 종료 후 월 관리비만 입력. 미확인을 0으로 추정하지 않음.')] = None, installation_conditions: Annotated[InstallationConditions | None, Field(description='고객이 확인한 설치 조건만 입력. 모르면 생략 또는 unknown.')] = None, planned_start_date: Annotated[str, Field(description='신규 구독 전환 예정일 YYYY-MM-DD. 미정이면 빈 문자열.')] = '', card_id: Annotated[str, Field(description='고객이 선택한 카드 ID. 선택하지 않았다면 none. 최고 할인 카드를 임의로 선택하지 않음.')] = 'none', card_spend: Annotated[int | None, Field(description='고객이 입력한 전월 인정실적(원). 미입력은 None. 최고 실적을 추정하지 않음.')] = None, card_eligibility: Annotated[Literal['unconfirmed','base','promotion'], Field(description='고객이 확인한 자격. 미확인은 unconfirmed, 기본 조건 충족 base, 행사 조건까지 충족 promotion. 미확인은 할인을 확정하지 않음.')] = 'unconfirmed', card_application_date: Annotated[str, Field(description='카드 행사 신청 검토일 YYYY-MM-DD. 미지정은 전환 검토일. 행사 혜택 제공 시작일과 구분.')] = '') -> dict:
    """호출: 현재 제품 유지와 선택한 신규 구독 교체를 같은 기간 비교할 때.
    제외: 단순 후보는 lookup_subscription_offers, 두 해지 날짜만 비교하면 compare_contract_options.
    입력: offer_id는 고객 선택, planned_start_date는 전환일, comparison_months는 기간. 시점 미정이면 서버 기준 오늘. 비교 기간은 오늘부터 시작하며 고객이 지정한 전환일만 우선. offer_id 미선택은 새 후보를 확인하고 고객 선택을 기다림. 같은 모델 기본 선택 금지.
    결과: 기존 해지 정산+신규 구독·초기비 포함 비교와 월 부담.
    제한: 비용 동의 필요. 이벤트 자동 적용 없음. 설치·가입 조건 미확인은 총액 미확정, 임의 최적 상품 선정 금지.
    """
    from 정수기프로젝트.app.mcp.subscription.renewal_comparison import compare_retention_renewal as compare
    if not offer_id:return {'status':'needs_info','missing_fields':['offer_id'],'message':'먼저 원하는 기능과 관리 방식에 맞는 새 모델을 선택해 주세요.'}
    return compare(session_id,access_token,offer_id,comparison_date,comparison_months,maintenance_monthly_fee,_conditions(installation_conditions),planned_start_date,card_id,card_spend,card_eligibility,card_application_date)


@mcp.tool
def lookup_subscription_offers(model_id: Annotated[str, Field(description='현재 문의 대상 모델. 내 제품과 신규 선택 모델을 구분합니다.')] = '', planned_start_date: Annotated[str, Field(description='신규 구독 전환 예정일 YYYY-MM-DD. 미정이면 빈 문자열.')] = '', offer_id: Annotated[str, Field(description='고객이 선택한 상품 ID. 임의 생성 금지.')] = '', required_features: Annotated[list[Literal['냉수','정수','온수','얼음']] | None, Field(description='고객이 필요한 물 기능. 미정이면 빈 목록.')] = None, installation_type: Literal['any','desk','built_in','stand']='any', care_mode: Literal['any','visit','self']='any', exclude_owned_model: Annotated[bool,Field(description='고객이 다른 모델을 원하면 True. 보유 모델 ID는 서버가 주입.')] = False, exclude_model_id: str='', sort_by: Literal['default','monthly_fee']='default') -> dict:
    """호출: 신규 구독·교체 상품의 모델·요금·관리·계약 조건 후보를 볼 때.
    제외: 개인 비용 계산은 compare_retention_renewal. 필요한 기능·설치·관리 필터를 이 조회에 사용.
    입력: 목록 요청이면 model_id·offer_id 비움. 지정한 모델·상품만 상세 조회.
    결과: 공식 선택 조건 스냅샷과 합성 상품을 구분한 후보.
    제한: 개인 가입 견적·혜택 적용 확정 금지. 보유 모델을 전체 목록 필터로 자동 사용하지 않음.
    """
    from 정수기프로젝트.app.mcp.subscription.subscription_offers import lookup_subscription_offers as lookup
    return lookup(model_id,planned_start_date,offer_id,required_features,installation_type,care_mode,exclude_model_id,sort_by)


@mcp.tool
def create_renewal_brief(session_id: Annotated[str, Field(description='서버가 주입하는 세션. 모델 입력에서 제외.')] = '', access_token: Annotated[str, Field(description='서버가 주입하는 권한. 모델 입력에서 제외.')] = '', offer_id: Annotated[str, Field(description='고객이 선택한 상품 ID. 임의 생성 금지.')] = '', comparison_date: Annotated[str, Field(description='비교 기준일. 미지정이면 빈 문자열로 서버 청구 기준일 사용.')] = '', comparison_months: Annotated[int, Field(description='동일 기준 비교 기간(개월). 기본 36은 참고 비교.')] = 36, maintenance_monthly_fee: Annotated[int | None, Field(description='고객이 실제 확인한 종료 후 월 관리비만 입력. 미확인을 0으로 추정하지 않음.')] = None, installation_conditions: Annotated[InstallationConditions | None, Field(description='고객이 확인한 설치 조건만 입력. 모르면 생략 또는 unknown.')] = None, planned_start_date: Annotated[str, Field(description='신규 구독 전환 예정일 YYYY-MM-DD. 미정이면 빈 문자열.')] = '', card_id: Annotated[str, Field(description='고객이 선택한 카드 ID. 선택하지 않았다면 none. 최고 할인 카드를 임의로 선택하지 않음.')] = 'none', card_spend: Annotated[int | None, Field(description='고객이 입력한 전월 인정실적(원). 미입력은 None. 최고 실적을 추정하지 않음.')] = None, card_eligibility: Annotated[Literal['unconfirmed','base','promotion'], Field(description='고객이 확인한 자격. 미확인은 unconfirmed, 기본 조건 충족 base, 행사 조건까지 충족 promotion. 미확인은 할인을 확정하지 않음.')] = 'unconfirmed', card_application_date: Annotated[str, Field(description='카드 행사 신청 검토일 YYYY-MM-DD. 미지정은 전환 검토일. 행사 혜택 제공 시작일과 구분.')] = '') -> dict:
    """호출: 고객이 유지·신규 교체 비교를 파일로 요청할 때.
    제외: 기간·해지 파일은 create_contract_document_brief, 제품·오류는 create_support_brief.
    입력: 고객이 선택한 offer_id·전환일·비교 기간·확인된 설치 조건.
    결과: 동일 조건 재계산 후 비교 파일·등록 ID.
    제한: 명시적 요청·비용 동의 필요. 미확인 비용·남은 약정 표시. 가입·해지 신청 아님.
    """
    from 정수기프로젝트.app.mcp.subscription.renewal_comparison import create_renewal_brief as create
    if not offer_id:return {'status':'needs_info','missing_fields':['offer_id'],'message':'먼저 원하는 기능과 관리 방식에 맞는 새 모델을 선택해 주세요.'}
    return create(session_id,access_token,offer_id,comparison_date,comparison_months,maintenance_monthly_fee,_conditions(installation_conditions),planned_start_date,card_id,card_spend,card_eligibility,card_application_date)


@mcp.tool
def suggest_contract_timing(session_id: Annotated[str, Field(description='서버가 주입하는 세션. 모델 입력에서 제외.')] = '', access_token: Annotated[str, Field(description='서버가 주입하는 권한. 모델 입력에서 제외.')] = '') -> dict:
    """호출: 교체 날짜를 아직 정하지 못해 계약 기반 후보일을 원할 때.
    제외: 가장 저렴한 날짜 계산이나 설치 예약 기능이 아님.
    입력: 세션·권한은 서버 주입.
    결과: 전체 계약 종료 다음 날 후보·기간·이유.
    제한: 기간 동의 필요. 경제적 최적 시점·혜택 보장 금지.
    """
    from 정수기프로젝트.app.mcp.contracts.contract_timing import suggest_contract_timing as suggest
    return suggest(session_id,access_token)


@mcp.tool
def get_official_channel(purpose: Annotated[Literal['product','support','contract'],Field(description='product=신규 제품·구매·가격, support=사용오류·사용방법·관리, contract=실제 계약 처리·상담')]) -> dict:
    """호출: 신규 구매·사용오류·사용법 또는 실제 계약 처리가 필요한 경우 공식 페이지 안내.
    support: 온수가 미지근함, 냉수 온도, 출수 이상, 버튼·잠금·필터 사용 등 증상/조작/관리 질문. 이 Agent는 진단·자가조치를 제공하지 않으므로 본 도구로 AI Chat을 안내한다.
    제외: 기존 구독 유지·새 모델 재구독 비교는 내부 후보/비교 도구 사용.
    제외: 개인 계약 정산을 대신 조회·계산하지 않음.
    입력: 문의 목적 하나. 고객 정보·토큰·대화 내용은 외부로 전달하지 않음.
    결과: 확인된 공식 URL·이용 안내. AI Chat 자동 실행·상담 접수·대화 전달 기능이 아님.
    """
    channels={
      'product':('LG전자 정수기 제품 페이지','https://www.lge.co.kr/category/water-purifiers','제품 선택·구매 조건은 LG 공식 제품 페이지에서 확인하세요.'),
      'support':('LG전자 공식 AI Chat','https://www.lge.co.kr/ai-commerce/aiAssistant','사용방법·오류·관리 문의는 아래 LG 공식 AI Chat을 열어 상담하세요.'),
      'contract':('LG전자 공식 고객지원','https://www.lge.co.kr/support','실제 계약 변경·해지 접수와 최종 청구액은 공식 상담에서 확인하세요.')}
    title,url,message=channels[purpose]
    return {'status':'ok','channel':purpose,'message':message,'sources':[{'document_id':'LG-OFFICIAL-'+purpose.upper(),'title':title,'url':url,'checked_at':'2026-10-13'}],'limitations':'공식 페이지를 여는 연결 안내입니다. 로그인·계약·대화 정보는 자동 전달하지 않으며 AI Chat을 자동 실행하지 않습니다.'}


if __name__ == "__main__":
    mcp.run(
        transport='http',
        host='127.0.0.1',
        port=8001,
    )
