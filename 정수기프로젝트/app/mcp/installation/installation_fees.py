"""공식 설치 작업 단가 조회. 전체 설치 견적·해지 수거비가 아닙니다."""
import csv
from pathlib import Path

RULE_PATH = Path(__file__).parent.parent / 'data/installation_fee_rules.csv'


def lookup_installation_fee_rules(model_id):
    try:
        with RULE_PATH.open(encoding='utf-8-sig', newline='') as f:
            all_rows = list(csv.DictReader(f))
        items = []
        for row in all_rows:
            if row['model_id'] != model_id:
                continue
            amount = row['amount']
            if amount and not amount.isdecimal():
                raise ValueError('설치 단가 형식')
            amount = int(amount) if amount else None
            if row['review_status'] == 'verified' and amount is None:
                raise ValueError('확인 단가 누락')
            if row['review_status'] not in ('verified', 'needs_confirmation'):
                raise ValueError('검수 상태')
            items.append({**row, 'amount': amount, 'source_kind': 'official',
                          'status': 'confirmed' if row['review_status'] == 'verified' else 'unverified'})
        return {'status': 'ok' if items else 'unverified', 'items': items,
                'estimated_total': None,
                'limitations': '2026-10-07 확인한 공식 작업별 단가입니다. 필요한 작업·현장 조건·향후 가격 확인 전 전체 설치비를 확정하지 않습니다. 이전 설치·철거·운송·계약 해지 수거비는 별도입니다.'}
    except (OSError, KeyError, ValueError):
        return {'status': 'error', 'code': 'INSTALLATION_DATA_INVALID', 'items': [], 'estimated_total': None}


def estimate_installation_fee(model_id, conditions):
    """고객 답변에 해당하는 추가 작업 단가 합산. 원문·계약·기본 설치비와 분리."""
    allowed = {'drilling_needed','pump_needed','breaker_needed','outlet_needed','external_outlet_drilling','external_water_drilling','thick_sink','surface_material'}
    if not isinstance(conditions, dict) or set(conditions)-allowed:
        return {'status':'error','code':'INVALID_INSTALLATION_INPUT'}
    for k,v in conditions.items():
        values = ('artificial','natural','ceramic','unknown') if k=='surface_material' else ('yes','no','unknown')
        if v not in values: return {'status':'error','code':'INVALID_INSTALLATION_INPUT'}
    catalog = lookup_installation_fee_rules(model_id)
    if catalog['status'] != 'ok': return catalog
    rules = {r['work_type']: r for r in catalog['items']}
    built = model_id == 'WU923AWB'
    fields = ['drilling_needed', 'pump_needed', 'breaker_needed']
    if built: fields += ['outlet_needed', 'external_outlet_drilling', 'external_water_drilling', 'thick_sink']
    missing = [k for k in fields if conditions.get(k, 'unknown') == 'unknown']
    selected = []
    def choose(name):
        r = rules.get(name)
        if not r: missing.append(name)
        else: selected.append(r)
    if conditions.get('drilling_needed') == 'yes':
        material = conditions.get('surface_material', 'unknown')
        if material == 'unknown': missing.append('surface_material')
        elif material in ('artificial', 'natural', 'ceramic'): choose('drill_'+material)
        else: missing.append('surface_material')
    for field, work in [('pump_needed','pump'),('breaker_needed','breaker'),('outlet_needed','new_outlet')]:
        if field in fields and conditions.get(field) == 'yes': choose(work)
    if built:
        for field, work in [('external_outlet_drilling','drill_natural_outlet'),('external_water_drilling','drill_natural_water')]:
            if conditions.get(field) == 'yes':
                if conditions.get('surface_material') == 'natural': choose(work)
                else: missing.append(field+'_quote')
        if conditions.get('thick_sink') == 'yes':
            # 상판 출수구 타공과 싱크볼 타공의 중복 합산 방지
            if conditions.get('drilling_needed') == 'yes': missing.append('drilling_target')
            else: choose('thick_sink')
    unknown_items=[r['work_type'] for r in selected if r['amount'] is None]
    missing=sorted(set(missing+unknown_items))
    subtotal=sum(r['amount'] for r in selected if r['amount'] is not None)
    return {'status': 'needs_info' if missing else 'ok', 'model_id': model_id,
            'work_items': selected, 'confirmed_subtotal': subtotal,
            'estimated_additional_installation_fee': None if missing else subtotal,
            'estimated_total': None, 'missing_fields': missing,
            'source_ids': sorted({r['source_id'] for r in selected}),
            'limitations': '고객 답변에 따른 확인된 추가 설치 작업만 계산합니다. 현장 견적·기본 설치비·추가 미발견 작업·철거/운송·혜택은 제외하며 전체 설치 총액은 확정하지 않습니다. 현재 단가로 미래 비용을 보장하지 않습니다.'}
