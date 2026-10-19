"""V2 가상 문서의 허용 필드 조회·계산. 원문 PDF OCR은 아직 하지 않습니다.

개인 문서를 공용 RAG로 넣지 않고, 서버가 선택한 고객의 구조화 데이터만 읽습니다.
"""
import csv
from datetime import date
from pathlib import Path
from 정수기프로젝트.app.consent import ConsentStore, ConsentDenied
from 정수기프로젝트.app.mcp.contracts.protected_tools import denied_result
from 정수기프로젝트.app.mcp.contracts.contract_pdf import load_contract

ROOT = Path(__file__).resolve().parent.parent / 'data'
BILLING_PATH = ROOT / 'billing_v2.csv'
SOURCE = 'SYNTH-CONTRACT-V2'
LIMIT = '시연용 합성 계약·계산이며 실제 LG 계약·요금 기준이 아닙니다.'


def _load(session_id, access_token, scope):
    try:
        profile = ConsentStore().authorize(session_id, access_token, scope)
    except ConsentDenied as exc:
        return None, None, denied_result(exc)
    try:
        contract=load_contract(profile['demo_customer_id'])
        with BILLING_PATH.open(encoding='utf-8-sig',newline='') as file:
            records=list(csv.DictReader(file))
        billing=next(b for b in records if b['customer_id']==profile['demo_customer_id'])
        for key in ('arrears','current_month_paid','current_month_invoice'):
            billing[key]=int(billing[key])
        if contract['rule_id'] != SOURCE or contract['is_demo'] is not True:
            raise ValueError('잘못된 가상 자료')
        if contract['document_type'] != 'subscription_contract':
            return None, None, {'status':'not_applicable','is_demo':True,'source_ids':[], 'message':'선택한 가상 고객은 구독 계약이 없습니다.'}
        # 조회 전에 필수 필드·날짜·금액을 검증해 누락값을 예외로 노출하지 않습니다.
        start, mandatory, end = (_day(contract[k]) for k in ('contract_start','mandatory_end','contract_end'))
        if not start <= mandatory <= end:
            raise ValueError('기간 순서')
        _day(billing['as_of'])
        for key in ('monthly_fee','billing_day'):
            _amount(contract[key])
        for key in ('arrears','current_month_paid','current_month_invoice'):
            _amount(billing[key])
        for amount in contract['annual_monthly_fees'].values():
            _amount(amount)
        for key in ('penalty_before_or_on_mandatory_end','penalty_after_mandatory_end','collection_before_or_on_contract_end','discount_return_before_or_on_contract_end','post_contract_exit_fees'):
            _amount(contract['exit_rules'][key])
        for key in ('proration','charge_on_first_day','full_month_due_if_used_on_first_day','already_paid_current_month_not_refunded'):
            if type(contract['settlement_policy'][key]) is not bool:
                raise ValueError('청구 규칙 형식')
        if not isinstance(contract['discount'],dict) or not isinstance(contract['return_policy'],str):
            raise ValueError('조건 형식')
        return contract, billing, None
    except (OSError, ValueError, KeyError, StopIteration, TypeError):
        return None, None, {'status':'error','code':'CONTRACT_DATA_INVALID'}


def _day(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError('날짜 형식')
    result = date.fromisoformat(value)
    if result.isoformat() != value:
        raise ValueError('날짜 형식')
    return result


def _amount(value):
    if type(value) is not int or value < 0:
        raise ValueError('금액')
    return value


def _terms(c):
    return {'id':c['document_id'],'contract_start':c['contract_start'],
            'mandatory_end':c['mandatory_end'],'contract_end':c['contract_end']}


def lookup_contract_document(session_id, access_token):
    """기간 조회 동의로 기간 필드만 반환. 비용 동의가 있을 때만 요금·조건 추가."""
    c, b, failure = _load(session_id, access_token, 'contract_terms')
    if failure:
        return failure
    terms = _terms(c)
    locations = {k:'계약 기본 정보' if k=='contract_start' else '2. 상품 및 요금' for k in terms if k!='id'}
    try:
        ConsentStore().authorize(session_id, access_token, 'contract_costs')
    except ConsentDenied:
        pass
    else:
        for key in ('monthly_fee','annual_monthly_fees','billing_day','settlement_policy','discount','exit_rules','return_policy'):
            terms[key] = c[key]
            locations[key] = '4. 해지·반환 및 별도 정산' if key in {'exit_rules','return_policy'} else '2. 상품 및 요금 / 3. 할인 및 청구 조건'
    return {'status':'ok','is_demo':True,'rule_id':SOURCE,'terms':terms,
            'model_id':c['model'],'document_id':c['document_id'],'field_locations':locations,
            'source_ids':[SOURCE],'limitations':LIMIT,
            'extraction_method':c['extraction_method'],
            'financial_fields_available':'monthly_fee' in terms,
            'withheld_fields':[] if 'monthly_fee' in terms else ['monthly_fee','settlement_policy','exit_rules']}


def _calculate(c,b,exit_date):
    try:
        exit_day = _day(exit_date)
        start, mandatory, end = (_day(c[k]) for k in ('contract_start','mandatory_end','contract_end'))
        if not start <= mandatory <= end or exit_day < start:
            raise ValueError('기간')
        r = c['exit_rules']
        penalty = _amount(r['penalty_before_or_on_mandatory_end']) if exit_day <= mandatory else _amount(r['penalty_after_mandatory_end'])
        collection = _amount(r['collection_before_or_on_contract_end']) if exit_day <= end else 0
        discount = _amount(r['discount_return_before_or_on_contract_end']) if exit_day <= end else 0
        arrears = _amount(b['arrears'])  # 기간 종료 후에도 미납금은 정산합니다.
    except (KeyError,TypeError,ValueError):
        return {'status':'error','code':'INVALID_CONTRACT_INPUT','estimated_total':None}
    items = [{'name':name,'status':'confirmed','amount':value,'source_ids':[SOURCE]} for name,value in
             [('위약금(합성 규칙)',penalty),('수거비(합성 규칙)',collection),('할인반환금(합성 규칙)',discount),('미납금(가상 청구 내역)',arrears)]]
    total = sum(i['amount'] for i in items)
    return {'status':'ok','is_demo':True,'rule_id':SOURCE,'period_summary':{**_terms(c),'exit_date':exit_date},
            'cost_items':items,'confirmed_subtotal':total,'estimated_total':total,
            'source_ids':[SOURCE],'limitations':LIMIT}


def assess_contract_document_costs(session_id, access_token, exit_date):
    c,b,failure = _load(session_id,access_token,'contract_costs')
    if failure:
        return failure
    if not exit_date:
        return {'status':'needs_info','missing_fields':['exit_date'],'estimated_total':None}
    return _calculate(c,b,exit_date)


def compare_contract_options(session_id, access_token, exit_date_a, exit_date_b, comparison_date):
    """청구 내역 기준일부터 각 해지일까지 추가 월요금+해지비용 비교. 과거 납부액 제외."""
    c,b,failure = _load(session_id,access_token,'contract_costs')
    if failure:
        return failure
    try:
        comparison_date=comparison_date or b['as_of']
        base = _day(comparison_date)
        days = [_day(exit_date_a),_day(exit_date_b)]
        if base != _day(b['as_of']):
            return {'status':'needs_info','missing_fields':['billing_reference_date'],
                    'message':'청구 내역 기준일과 비교 기준일을 맞춰야 합니다.','available_reference_date':b['as_of']}
        if min(days) < base:
            raise ValueError('비교일이 기준일 이전')
        policy = c['settlement_policy']
        if policy['proration'] is not False or c['billing_day'] != 1 or not policy['charge_on_first_day'] or not policy['full_month_due_if_used_on_first_day'] or not policy['already_paid_current_month_not_refunded']:
            raise ValueError('지원하지 않는 청구 조건')
        end,start = _day(c['contract_end']),_day(c['contract_start'])
        if base < start:
            raise ValueError('계약 시작 전 기준일')
        base_year=(base.year-start.year)-((base.month,base.day)<(start.month,start.day))+1
        expected_invoice = 0 if base > end else _amount(c['annual_monthly_fees'][str(base_year)])
        if b['current_month_paid'] != b['current_month_invoice'] or b['current_month_invoice'] != expected_invoice:
            return {'status':'needs_info','missing_fields':['current_month_payment'],'message':'당월 납부 내역 확인이 필요합니다.'}
        options=[]
        for day in days:
            costs=_calculate(c,b,day.isoformat())
            if costs['status']!='ok':
                return costs
            year,month=base.year,base.month
            months=[]
            while True:
                if month==12: year,month=year+1,1
                else: month+=1
                charge=date(year,month,1)
                if charge>day or charge>end: break
                contract_year=(charge.year-start.year)-((charge.month,charge.day)<(start.month,start.day))+1
                fee=_amount(c['annual_monthly_fees'][str(contract_year)])
                months.append({'charge_date':charge.isoformat(),'amount':fee})
            extra=sum(m['amount'] for m in months)
            options.append({'exit_date':day.isoformat(),'additional_subscription_fee':extra,'charge_items':months,
                            'exit_costs':costs,'additional_total':extra+costs['estimated_total']})
        difference=abs(options[0]['additional_total']-options[1]['additional_total'])
        lower=min(options,key=lambda o:o['additional_total'])['exit_date'] if difference else None
        return {'status':'ok','is_demo':True,'rule_id':SOURCE,'comparison_date':comparison_date,
                'options':options,'difference':difference,'lower_cost_date':lower,
                'source_ids':[SOURCE],'limitations':LIMIT+' 동일 기준일 이후 추가 부담이며 이미 납부한 당월 요금은 제외합니다.'}
    except (KeyError,TypeError,ValueError):
        return {'status':'error','code':'INVALID_COMPARISON_INPUT'}


def create_contract_document_brief(session_id, access_token, exit_date='', exit_date_a='', exit_date_b='', comparison_date=''):
    """V2 기간·비용 결과로 준비서 생성. 모델의 요약을 파일 사실로 사용하지 않음."""
    from 정수기프로젝트.app.mcp import tools
    comparison_requested=any((exit_date_a,exit_date_b,comparison_date))
    if comparison_requested and exit_date:
        return {'status':'needs_info','missing_fields':['brief_scope'],'message':'한 날짜 비용 또는 두 날짜 비교 중 준비서 범위를 확인해 주세요.'}
    c,b,failure=_load(session_id,access_token,'contract_costs' if exit_date or comparison_requested else 'contract_terms')
    if failure:
        return failure
    facts=[f"의무사용 종료일: {c['mandatory_end']}",f"전체 계약 종료일: {c['contract_end']}"]
    if comparison_requested:
        if not comparison_date:comparison_date=b['as_of']
        missing=[k for k,v in [('exit_date_a',exit_date_a),('exit_date_b',exit_date_b),('comparison_date',comparison_date)] if not v]
        if missing:return {'status':'needs_info','missing_fields':missing}
        compared=compare_contract_options(session_id,access_token,exit_date_a,exit_date_b,comparison_date)
        if compared['status']!='ok':return compared
        facts.append(f'비교 기준일: {comparison_date}')
        for option in compared['options']:
            facts.append(f"{option['exit_date']}: 추가 구독료 {option['additional_subscription_fee']:,}원 + 해지 비용 {option['exit_costs']['estimated_total']:,}원 = 추가 부담 {option['additional_total']:,}원")
            facts.extend(f"{option['exit_date']} {item['name']}: {item['amount']:,}원" for item in option['exit_costs']['cost_items'])
        facts.append(f"추가 부담 차이: {compared['difference']:,}원")
        facts.append('이미 납부한 당월 요금은 공통 비용으로 제외합니다. 고객의 유지·해지 선택을 대신하지 않습니다.')
    elif exit_date:
        costs=_calculate(c,b,exit_date)
        if costs['status']!='ok':return costs
        facts.append(f'해지 검토일: {exit_date}')
        facts.extend(f"{i['name']}: {i['amount']:,}원" for i in costs['cost_items'])
        facts.append(f"예상 총액: {costs['estimated_total']:,}원")
    if exit_date:
        summary=f'정수기 구독 해지를 검토하고 있습니다. {exit_date} 기준 예상 정산 내역을 확인했으며 실제 최종 비용과 제품 반납·해지 절차를 상담에서 확인하고 싶습니다.'
    elif comparison_requested:
        summary=f'{exit_date_a}와 {exit_date_b} 해지 시 추가 부담을 비교했습니다. 실제 정산 조건과 반납 일정을 확인한 뒤 날짜를 결정하고 싶습니다.'
    else:
        summary=f'내 정수기 구독의 의무사용 종료일은 {c["mandatory_end"]}, 전체 계약 종료일은 {c["contract_end"]}로 확인했습니다. 두 기간의 차이와 계약 변경 시 확인할 조건을 상담하고 싶습니다.'
    questions=['안내받은 예상 정산과 실제 최종 청구액이 같은가요? 추가되거나 달라지는 항목을 알려주세요.','해지를 결정하면 신청·제품 반납은 어떻게 진행하며, 마지막 요금은 언제 정산하나요?'] if exit_date or comparison_requested else ['의무사용 종료와 전체 계약 종료에서 각각 달라지는 조건은 무엇인가요?','해지 비용을 확인하려면 어떤 검토 날짜와 계약 조건을 준비해야 하나요?']
    result=tools.create_consultation_brief(summary,facts,questions,[SOURCE])
    if result['status']!='ok':return result
    try:
        ConsentStore().register_brief(result['brief_id'],session_id,access_token,result['absolute_path'])
    except Exception:
        Path(result['absolute_path']).unlink(missing_ok=True)
        return {'status':'error','code':'BRIEF_REGISTER_FAILED'}
    result.pop('absolute_path',None)
    result.update(is_demo=True,rule_id=SOURCE,source_ids=[SOURCE],download_path='/briefs/'+result['brief_id'])
    return result
