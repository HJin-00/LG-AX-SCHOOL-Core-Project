"""신규 구독 조건 카탈로그. 공용 상품 조건만 읽으며 개인 계약과 혜택은 포함하지 않습니다."""
import csv
import re
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DATA_ROOT = Path(__file__).parent.parent / 'data'
OFFER_PATH = DATA_ROOT / 'subscription_offers.csv'
RATE_PATH = DATA_ROOT / 'subscription_offer_rates.csv'
Money = Annotated[int, Field(strict=True, ge=0)]
Positive = Annotated[int, Field(strict=True, ge=1)]


class RatePeriod(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start_month: Positive
    end_month: Positive
    monthly_fee: Money

    @model_validator(mode='after')
    def ordered(self):
        if self.end_month < self.start_month:
            raise ValueError('요금 적용 기간 순서')
        return self


class SubscriptionOffer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    offer_id: str = Field(pattern=r'^[A-Z0-9_-]+$')
    model_id: str = Field(min_length=1)
    care_mode: Literal['visit', 'self']
    care_details: str = Field(min_length=1)
    contract_months: Positive
    mandatory_months: Positive
    ownership_rule: Literal['transfer_at_contract_end', 'not_transferred', 'requires_confirmation']
    ownership_condition: str = Field(min_length=1)
    registration_fee: Money | None
    installation_fee: Money | None
    other_initial_fee: Money | None
    installation_fee_source_id: str | None = None
    installation_fee_source_url: str | None = None
    fee_conditions: str = Field(min_length=1)
    available_from: date
    available_until: date
    source_kind: Literal['synthetic', 'official']
    source_id: str = Field(min_length=1)
    source_url: str | None
    source_section: str = Field(min_length=1)
    source_checked_at: date
    review_status: Literal['demo_validated', 'pending', 'verified']
    rates: list[RatePeriod] = Field(min_length=1)

    @model_validator(mode='after')
    def consistent(self):
        if self.mandatory_months > self.contract_months:
            raise ValueError('의무기간이 전체기간보다 김')
        if self.available_until < self.available_from:
            raise ValueError('판매 기간 순서')
        if self.source_kind == 'synthetic':
            if self.review_status != 'demo_validated' or self.source_url is not None or not self.source_id.startswith('SYNTH-'):
                raise ValueError('합성 조건의 출처 표시')
        elif self.review_status == 'demo_validated' or not self.source_url or not self.source_url.startswith('https://'):
            raise ValueError('공식 출처·검수 상태')
        expected = 1
        for rate in self.rates:
            if rate.start_month != expected:
                raise ValueError('요금표 누락·중복 또는 순서 오류')
            expected = rate.end_month + 1
        if expected != self.contract_months + 1:
            raise ValueError('전체 계약기간의 요금표 필요')
        return self


def _integer(value, nullable=False):
    if value == '' and nullable:
        return None
    if not isinstance(value, str) or not value.isdecimal():
        raise ValueError('CSV 정수 형식')
    return int(value)


def load_offers():
    """CSV 공란 비용은 미확인으로 유지. 카탈로그 전체의 오류는 닫힌 실패로 처리합니다."""
    with OFFER_PATH.open(encoding='utf-8-sig', newline='') as f:
        records = list(csv.DictReader(f))
    with RATE_PATH.open(encoding='utf-8-sig', newline='') as f:
        rates = list(csv.DictReader(f))
    ids = [r['offer_id'] for r in records]
    if not records or len(ids) != len(set(ids)):
        raise ValueError('빈 목록 또는 중복 offer_id')
    if any(r['offer_id'] not in ids for r in rates):
        raise ValueError('연결되지 않은 요금표')
    result = []
    for row in records:
        row = dict(row)
        for k in ('contract_months', 'mandatory_months'):
            row[k] = _integer(row[k])
        for k in ('registration_fee', 'installation_fee', 'other_initial_fee'):
            row[k] = _integer(row[k], nullable=True)
        row['source_url'] = row['source_url'] or None
        row['rates'] = [
            {k: _integer(r[k]) for k in ('start_month', 'end_month', 'monthly_fee')}
            for r in rates if r['offer_id'] == row['offer_id']
        ]
        result.append(SubscriptionOffer.model_validate(row))
    return result


def official_snapshots(model_id='',offer_id=''):
    """공식 페이지 선택 조건 스냅샷. 개인 가입 조건/미래 견적이 아닌 탐색 자료."""
    from 정수기프로젝트.app.mcp import tools
    products=tools._load_json(tools.DATA_DIR/'products.json','products')
    path=DATA_ROOT/'official_subscription_snapshots.csv'
    with path.open(encoding='utf-8-sig',newline='') as f:rows={r['model_id']:r for r in csv.DictReader(f)}
    result=[]
    available_models=tools.candidate_model_ids()
    for product in products:
        model=product['model_id'];ident='LG-SNAPSHOT-'+model
        if model not in available_models:continue
        if model in {'WD520VCT','WU923AWB'} or (model_id and model!=model_id) or (offer_id and offer_id!=ident):continue
        row=rows.get(model);known=bool(row) and row['purchasable']=='True'
        source=product['sources'][0]
        rate=int(row['standard_monthly_fee']) if known else None
        months=int(row['contract_months']) if known else None
        rates=[{'start_month':1,'end_month':months,'monthly_fee':rate}] if known else []
        if known:
            # 명시된 할인 회차만 적용합니다. 카드/쿠폰 자격이나 미래 적용 여부는 확정하지 않습니다.
            notice=row.get('price_notice','')
            span=re.search(r'1\s*[~～]\s*(\d+)\s*회차',notice)
            first=re.search(r'1회차.*2회차부터',notice)
            discounted=int(row['display_monthly_fee'])
            discount_months=int(span.group(1)) if span else 1 if first else 0
            if 0<discount_months<months and discounted<rate:
                rates=[{'start_month':1,'end_month':discount_months,'monthly_fee':discounted},
                       {'start_month':discount_months+1,'end_month':months,'monthly_fee':rate}]
        result.append({'offer_id':ident,'model_id':model,'care_mode':row['care_mode'] if known and '확인 필요' not in row['care_details'] else 'unknown',
            'care_details':row['care_details'] if known else '관리 조건 확인 필요',
            'contract_months':months,'mandatory_months':None,'ownership_rule':'requires_confirmation',
            'ownership_condition':'개인 신규 계약에서 확인','registration_fee':None,'installation_fee':None,'other_initial_fee':None,
            'installation_fee_source_id':None,'installation_fee_source_url':None,
            'fee_conditions':'등록비·설치비·기타 초기비·의무기간·가입 자격·미래 적용 요금 확인 필요',
            'rates':rates,
            'source_kind':'official','source_id':'LG-SUB-SNAPSHOT-'+model,'source_url':row['source_url'] if known else source['url'],
            'source_section':'선택 계약기간·관리주기·기본 월요금 / 할인 조건은 별도',
            'source_checked_at':'2026-10-08','review_status':'verified_snapshot','is_demo':False,
            'display_monthly_fee':int(row['display_monthly_fee']) if known else None,
            'rate_note':row['rate_note'].replace('$undefined','별도 할인기간 미표시') if known else '현재 해당 모델의 판매 가능한 구독 요금 조건을 확인하지 못했습니다.',
            'price_is_snapshot':True,'unverified_fields':['registration_fee','installation_fee','other_initial_fee','mandatory_months','ownership_rule','future_price'],
            'benefits_included':False,'selection_reason':'공식 모델별 기능으로 비교할 수 있는 후보입니다. 신규 가입 조건은 개인 견적에서 확인합니다.'})
    return result

def lookup_subscription_offers(model_id='', planned_start_date='', offer_id='', required_features=None, installation_type='any', care_mode='any', exclude_model_id='', sort_by='default'):
    """날짜 미정은 현재 카탈로그 후보 안내, 날짜 지정은 해당 시점 조건 조회."""
    catalog_only = not planned_start_date
    if catalog_only:
        from 정수기프로젝트.app.backend.ai.server_context import reference_date
        planned_start_date = reference_date()
    try:
        start = date.fromisoformat(planned_start_date)
        if start.isoformat() != planned_start_date:
            raise ValueError('날짜 형식')
    except (ValueError, TypeError):
        return {'status': 'needs_info', 'missing_fields': ['planned_start_date'], 'offers': []}
    try:
        all_offers = load_offers()
    except (OSError, ValueError, KeyError, TypeError):
        return {'status': 'error', 'code': 'OFFER_DATA_INVALID', 'offers': []}
    from 정수기프로젝트.app.mcp import tools
    available_models=tools.candidate_model_ids()
    hits = [o for o in all_offers
            if o.model_id in available_models
            and (not model_id or o.model_id == model_id)
            and (not offer_id or o.offer_id == offer_id)
            and o.available_from <= start <= o.available_until
            and o.review_status in ('demo_validated', 'verified')]
    output = []
    for offer in hits:
        row = offer.model_dump(mode='json')
        row['is_demo'] = offer.source_kind == 'synthetic'
        row['unverified_fields'] = [k for k in ('registration_fee', 'installation_fee', 'other_initial_fee') if row[k] is None]
        row['benefits_included'] = False
        from 정수기프로젝트.app.mcp.subscription.renewal_comparison import _product
        row['product'] = _product(offer.model_id)
        row['selection_reason'] = '현재 검수된 모델의 신규 구독 조건입니다. 고객이 기능·관리 방식으로 선택하며 자동 추천 순위가 아닙니다.'
        from 정수기프로젝트.app.mcp.installation.installation_fees import lookup_installation_fee_rules
        row['installation_reference'] = lookup_installation_fee_rules(offer.model_id)
        output.append(row)
    for row in official_snapshots(model_id,offer_id):
        if not row.get("rates"):continue  # 판매 불가/요금 미수집 상품은 비교 선택 후보에서 제외
        from 정수기프로젝트.app.mcp.subscription.renewal_comparison import _product
        row['product']=_product(row['model_id']);output.append(row)
    wanted=required_features or []
    if any(v not in {'냉수','정수','온수','얼음'} for v in wanted) or installation_type not in {'any','desk','built_in','stand'} or care_mode not in {'any','visit','self'}:
        return {'status':'error','code':'INVALID_OFFER_FILTER','offers':[]}
    forms={'desk':'데스크형','built_in':'언더싱크형','stand':'스탠드형'}
    output=[o for o in output if o['model_id']!=exclude_model_id
        and all((o.get('product') or {}).get('features',{}).get(v) is True for v in wanted)
        and (installation_type=='any' or (o.get('product') or {}).get('features',{}).get('설치 유형')==forms[installation_type])
        and (care_mode=='any' or o.get('care_mode')==care_mode)]
    if sort_by not in {'default','monthly_fee'}:return {'status':'error','code':'INVALID_OFFER_SORT','offers':[]}
    if sort_by=='monthly_fee':output.sort(key=lambda o:o.get('display_monthly_fee') if o.get('display_monthly_fee') is not None else o['rates'][0]['monthly_fee'])
    for o in output:
        o['selection_reason']='고객이 선택한 기능·설치·관리 조건에 맞는 후보입니다.'+(' 현재 보유 모델은 제외했습니다.' if exclude_model_id else '')+(' 시작 월요금이 낮은 순이며 할인 종료 후 요금·정산 포함 최종 부담 순위는 아닙니다.' if sort_by=='monthly_fee' else '')
    return {'status': 'ok' if output else 'unverified', 'offers': output,
            'sort_by':sort_by,'catalog_only':catalog_only,'checked_for_date':planned_start_date,
            'source_ids': sorted({o['source_id'] for o in output}),
            'limitations': ('날짜 미정: 현재 기준의 후보 목록이며 실제 시작일에는 다시 확인해야 합니다. ' if catalog_only else '')+'합성 조건과 공식 선택 조건 스냅샷을 구분합니다. 공식 표시 요금은 확인일의 계약기간·관리 주기 조건이며 개인 가입 자격·미래 적용 금액을 보장하지 않습니다. 이벤트·혜택은 계산에서 제외합니다. 신규 계약의 날짜와 유지/재구독 비교 총액은 별도 도구에서 검증해야 합니다.'}


def comparison_ready_model_ids():
    """초기비·요금표·약정·소유권 조건이 모두 검증된 모델만 시연 비교 대상으로 사용."""
    return {o.model_id for o in load_offers()
            if o.review_status in {'demo_validated','verified'}
            and all(v is not None for v in (o.registration_fee,o.installation_fee,o.other_initial_fee))
            and o.ownership_rule!='requires_confirmation'}


def demo_catalog_model_ids():
    """합성 조건과 판매 가능한 공식 요금표 후보. 미확인 관리 방식은 별도 표시."""
    ready=comparison_ready_model_ids()
    with (DATA_ROOT/'official_subscription_snapshots.csv').open(encoding='utf-8-sig',newline='') as f:
        rows={r['model_id']:r for r in csv.DictReader(f)}
    for model in rows:
        row=rows.get(model,{})
        if row.get('purchasable')=='True' and row.get('standard_monthly_fee','').isdecimal() and row.get('contract_months','').isdecimal():
            ready.add(model)
    return ready
