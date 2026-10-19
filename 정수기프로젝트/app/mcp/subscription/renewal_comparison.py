"""동일 기간의 유지 vs 기존 계약 정산 후 신규 구독 비교. 개인 조건은 권한 검증."""
import calendar
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import csv
from pathlib import Path
from datetime import date,timedelta
from 정수기프로젝트.app.mcp.contracts.contract_documents import _load, _day, _amount, compare_contract_options, SOURCE
from 정수기프로젝트.app.mcp.subscription.subscription_offers import lookup_subscription_offers
from 정수기프로젝트.app.mcp.installation.installation_fees import estimate_installation_fee


def _product(model_id):
    from 정수기프로젝트.app.mcp.tools import lookup_product_features
    rows=lookup_product_features([model_id]).get('products',[])
    if not rows:return None
    row=rows[0]
    from 정수기프로젝트.app.mcp.subscription.card_benefits import load_cards
    row['card_benefits']=load_cards()
    return {k:row.get(k) for k in ('model_id','display_name','image_url','features','sources','product_url','family_id','color_name','color_hex','card_benefits')}


CONTEXT_PATH=Path(__file__).parent.parent/'data/renewal_context.csv'


def profile_context(customer):
    if not CONTEXT_PATH.exists():return None
    with CONTEXT_PATH.open(encoding='utf-8-sig',newline='') as f:
        matches=[r for r in csv.DictReader(f) if r['customer_id']==customer]
    if not matches:return None
    if len(matches)!=1:raise ValueError('중복 비교 환경')
    row=matches[0]
    if row['source_id']!='SYNTH-RENEWAL-CONTEXT-V1':raise ValueError('환경 출처')
    if not row['maintenance_monthly_fee'].isdecimal():raise ValueError('관리비')
    row['maintenance_monthly_fee']=int(row['maintenance_monthly_fee'])
    return row


def add_months(day,months):
    n=day.year*12+day.month-1+months
    y,m=divmod(n,12);m+=1
    return date(y,m,min(day.day,calendar.monthrange(y,m)[1]))


def review_today():
    fixed=os.environ.get('EVALUATION_REFERENCE_DATE')
    return _day(fixed) if fixed else datetime.now(ZoneInfo('Asia/Seoul')).date()


def compare_retention_renewal(session_id,access_token,offer_id,comparison_date,comparison_months,
                              maintenance_monthly_fee=None,installation_conditions=None,planned_start_date="",card_id="none",card_spend=None,card_eligibility="unconfirmed",card_application_date=""):
    c,b,failure=_load(session_id,access_token,'contract_costs')
    if failure:return failure
    try:
        comparison_date=comparison_date or b['as_of']
        base=_day(comparison_date)
        if type(comparison_months)is not int or not 1<=comparison_months<=120:raise ValueError('비교기간')
        if maintenance_monthly_fee is not None:_amount(maintenance_monthly_fee)
        if base!=_day(b['as_of']):
            return {'status':'needs_info','missing_fields':['billing_reference_date'],'available_reference_date':b['as_of']}
        end=_day(c['contract_end'])
        today=review_today()
        try:start=_day(planned_start_date) if planned_start_date else today
        except (ValueError,TypeError):
            return {'status':'needs_info','missing_fields':['planned_start_date'],'message':'전환일을 유효한 YYYY-MM-DD 날짜로 선택해 주세요.'}
        if start<max(base,today):
            return {'status':'needs_info','missing_fields':['planned_start_date'],'message':'전환 검토일은 오늘 이후의 날짜로 선택해 주세요.'}
        # 종료일과 신규 시작일은 같은 날로 모델링. 일할 계산 없이 양쪽 당월 요금이 발생할 수 있습니다.
        if base>end:
            return {'status':'needs_info','missing_fields':['active_contract'],'message':'청구 자료 기준일에 현재 계약이 진행 중이어야 유지·전환 비교를 지원합니다. 종료된 계약은 신규 조건을 확인해 주세요.'}
        if '소유권 이전' not in c['return_policy']:
            return {'status':'needs_info','missing_fields':['ownership_and_billing_policy']}
        horizon_start=today
        next_horizon=add_months(horizon_start,comparison_months)
        horizon_end=next_horizon-timedelta(days=1)
        if horizon_end<start:
            return {'status':'needs_info','missing_fields':['comparison_months'],'message':'재구독 시작 이후를 포함하는 비교 기간이 필요합니다.'}
        settle_on=start.isoformat()
        current=compare_contract_options(session_id,access_token,(end+timedelta(days=1)).isoformat(),settle_on,comparison_date)
        if current['status']!='ok':return current
        keep_charges=[i for i in current['options'][0]['charge_items'] if _day(i['charge_date'])<=horizon_end]
        common=sum(i['amount'] for i in keep_charges)+b['arrears']
        exit_option=current['options'][1]
        transition_contract_cost=exit_option['additional_total']
        context=profile_context(c['customer_id'])
        default_offer_used=not offer_id
        if not offer_id and context:offer_id=context['default_offer_id']
        found=lookup_subscription_offers(planned_start_date=start.isoformat(),offer_id=offer_id)
        if found['status']!='ok':return found
        if len(found['offers'])!=1:return {'status':'needs_info','missing_fields':['offer_id']}
        offer=found['offers'][0]
        if not offer.get('rates') or not offer.get('contract_months'):
            return {'status':'needs_info','missing_fields':['new_subscription_terms'],'message':'선택 모델의 기능은 비교할 수 있지만 현재 가입 가능한 요금·계약기간이 확인되지 않았습니다. 공식 구독 조건 확인 또는 다른 후보 선택이 필요합니다.'}
        new_months=0
        while add_months(start,new_months)<=horizon_end:new_months+=1
        if new_months>offer['contract_months']:
            return {'status':'needs_info','missing_fields':['comparison_months'],'message':'신규 계약 이후 기간의 조건은 없어 지원하지 않습니다.'}
        charges=[]
        for month in range(1,new_months+1):
            rate=next(r for r in offer['rates'] if r['start_month']<=month<=r['end_month'])
            charges.append({'month':month,'charge_date':add_months(start,month-1).isoformat(),'amount':rate['monthly_fee']})
        from 정수기프로젝트.app.mcp.subscription.renewal_benefits import assess_renewal_benefit
        benefit=assess_renewal_benefit(c['contract_end'],start.isoformat(),offer['contract_months'],charges,offer['source_kind'])
        context=profile_context(c['customer_id'])
        assumptions=['신규 조건: 현재 모델 기준의 등록된 시연 상품'] if default_offer_used and context else []
        if maintenance_monthly_fee is None and context:
            maintenance_monthly_fee=context['maintenance_monthly_fee']
            assumptions.append('종료 후 유지비: 가상 고객에게 설정한 월평균 가정이며 LG 확정 청구액이 아님')
        if (installation_conditions is None or installation_conditions=={}) and context and context['installation_model_id']==offer['model_id']:
            installation_conditions={k:context[k] for k in ('surface_material','drilling_needed','pump_needed','breaker_needed','outlet_needed','external_outlet_drilling','external_water_drilling','thick_sink')}
            assumptions.append('설치 환경: 동일 모델·기본 설치 가능으로 등록된 시연 환경')
        installation=estimate_installation_fee(offer['model_id'],installation_conditions or {})
        if installation['status']=='error':return installation
        # 미확인 초기비와 추가 작업은 0원으로 확정하지 않습니다.
        known_extra=installation.get('confirmed_subtotal',0)
        fees=[offer[k] for k in ('registration_fee','installation_fee','other_initial_fee')]
        keep_missing=[] if maintenance_monthly_fee is not None else ['maintenance_monthly_fee']
        renewal_missing=[k for k in ('registration_fee','installation_fee','other_initial_fee') if offer[k]is None]
        renewal_missing+=installation.get('missing_fields',[])
        maintenance_dates=[]
        due=add_months(date(end.year,end.month,1),1)
        while due<=horizon_end:
            if due>=horizon_start:maintenance_dates.append(due)
            due=add_months(due,1)
        maintenance_months=len(maintenance_dates)
        upkeep=maintenance_monthly_fee*maintenance_months if maintenance_monthly_fee is not None else None
        if maintenance_months==0:keep_missing=[];upkeep=0
        keep_sub=common+(upkeep or 0)
        gap_months=sum(day<start for day in maintenance_dates)
        gap_cost=gap_months*maintenance_monthly_fee if maintenance_monthly_fee is not None else None
        if gap_months and gap_cost is None:renewal_missing.append('maintenance_monthly_fee')
        new_sub=transition_contract_cost+(gap_cost or 0)+sum(r['amount']for r in charges)+sum(v for v in fees if v is not None)+known_extra
        from 정수기프로젝트.app.mcp.subscription.card_benefits import maximum_card_scenario
        from 정수기프로젝트.app.mcp.subscription.card_benefits import selected_card_scenario
        registration=card_application_date or start.isoformat()
        date.fromisoformat(registration)
        max_card=maximum_card_scenario(charges,registration)
        selected_card=selected_card_scenario(charges,registration,card_id,card_spend,card_eligibility)
        selected_card_total=new_sub-selected_card["card_saving"]
        max_card_total=new_sub-max_card['best']['card_saving'] if max_card['best'] else None
        scenario_total=new_sub if offer.get('price_is_snapshot') else None
        if offer.get('price_is_snapshot'):
            renewal_missing+=['new_subscription_terms','future_price']
            # 스냅샷 월요금의 가정 합계를 확인된 금액으로 위장하지 않습니다.
            new_sub-=sum(r['amount'] for r in charges)
        totals=[None if keep_missing else keep_sub,None if renewal_missing else new_sub]
        choice=None;saving=None;basis='needs_key_info'
        if all(t is not None for t in totals):
            choice='keep' if totals[0]<totals[1] else 'renew' if totals[1]<totals[0] else 'equal'
            saving=abs(totals[0]-totals[1]);basis='exact_modeled_cost'
        elif not offer.get('price_is_snapshot') and totals[0] is not None and totals[0]<new_sub:
            choice='keep';saving=new_sub-totals[0];basis='nonnegative_missing_cost_bound'
        elif not offer.get('price_is_snapshot') and totals[1] is not None and totals[1]<keep_sub:
            choice='renew';saving=keep_sub-totals[1];basis='nonnegative_missing_cost_bound'
        return {'status':'ok' if all(t is not None for t in totals) else 'unverified',
                'decision':{'lower_cost_choice':choice,'minimum_saving':saving,'basis':basis,
                            'maintenance_break_even_monthly':(new_sub-common)/maintenance_months if maintenance_months and not offer.get('price_is_snapshot') else None},
                'assumptions':assumptions,
                'base_installation_source':({'document_id':offer.get('installation_fee_source_id') or offer['source_id'],'title':'LG 기본 설치 안내(환경별 조건)','url':offer.get('installation_fee_source_url'),'model_id':offer['model_id'],'checked_at':'2026-10-07'} if offer.get('installation_fee_source_id') else None),
                'is_demo':True,'rule_id':SOURCE,'offer_source_kind':offer['source_kind'],
                'offer_source':{'document_id':offer['source_id'],'title':'LG 공식 구독 선택 조건' if offer['source_kind']=='official' else '시연용 신규 구독 조건','url':offer.get('source_url'),'model_id':offer['model_id'],'checked_at':offer.get('source_checked_at')},
                'comparison_request':{'planned_start_date':start.isoformat(),'offer_id':offer_id,'comparison_date':comparison_date,'comparison_months':comparison_months,'maintenance_monthly_fee':maintenance_monthly_fee,'installation_conditions':installation_conditions or {},'card_id':card_id,'card_spend':card_spend,'card_eligibility':card_eligibility,'card_application_date':registration},
                'comparison_date':comparison_date,'comparison_start':horizon_start.isoformat(),
                'comparison_end':horizon_end.isoformat(),'comparison_months':comparison_months,
                'renewal_start':start.isoformat(),'common_current_contract_cost':common,'transition_kind':'early_switch' if start<=end else 'after_contract',
                'billing_reference_date':b['as_of'],
                'renewal_options':[
                    {'choice':'keep','confirmed_subtotal':keep_sub,'estimated_total':totals[0],
                     'maintenance_months':maintenance_months,'maintenance_cost':upkeep,'existing_subscription_cost':sum(i['amount'] for i in keep_charges),'arrears':b['arrears'],'model_id':c['model'],'product':_product(c['model']),'missing_fields':keep_missing},
                    {'choice':'renew','offer_id':offer_id,'model_id':offer['model_id'],
                     'confirmed_subtotal':new_sub,'estimated_total':totals[1],
                     'subscription_cost':None if offer.get('price_is_snapshot') else sum(r['amount']for r in charges),'subscription_scenario_cost':sum(r['amount']for r in charges) if offer.get('price_is_snapshot') else None,'scenario_total':scenario_total,'price_note':offer.get('rate_note'),'subscription_months':new_months,'rate_segments':offer['rates'],'charge_items':charges,'product':_product(offer['model_id']),'care_details':offer['care_details'],
                     'existing_subscription_cost':exit_option['additional_subscription_fee'],'exit_cost_total':exit_option['exit_costs']['estimated_total'],'exit_cost_items':exit_option['exit_costs']['cost_items'],'initial_cost':sum(v for v in fees if v is not None)+known_extra,'maintenance_cost':gap_cost if gap_months else 0,
                     'installation':installation,'missing_fields':sorted(set(renewal_missing)),
                     'selected_card_benefit':selected_card,'selected_card_scenario_total':selected_card_total,'maximum_card_benefit':max_card,'maximum_card_scenario_total':max_card_total,'renewal_benefit':benefit,'maximum_benefit_scenario_total':(scenario_total if scenario_total is not None else new_sub)-benefit['maximum_scenario_saving'] if benefit['maximum_scenario_saving'] is not None else None,
                     'remaining_contract_months':offer['contract_months']-new_months,
                     'remaining_mandatory_months':max(0,offer['mandatory_months']-new_months) if offer['mandatory_months'] is not None else None}],
                'difference':abs(totals[0]-totals[1]) if all(t is not None for t in totals) else None,
                'source_ids':list(dict.fromkeys([SOURCE,offer['source_id']]+([context['source_id']] if assumptions else [])+([offer['installation_fee_source_id']] if offer.get('installation_fee_source_id') else [])+installation.get('source_ids',[]))),
                'limitations':'기존 계약은 가상 조건이며 신규 요금은 합성 조건 또는 공식 선택 조건 스냅샷입니다. 스냅샷 요금은 명시된 할인 회차와 이후 기본 요금을 반영한 참고이며 미래 신규 청구액으로 확정하지 않습니다. 설치 추가 단가는 공식 참고입니다. 동일 비교기간의 추가 지출을 비교하며 이미 납부한 당월 기존 요금은 제외합니다. 전환일에 기존 계약을 정산하고 신규 구독을 시작하는 가정입니다. 기존 추가 요금·위약금·수거비·할인반환금·미납금과 신규 요금·초기비를 포함합니다. 일할 계산 없이 같은 달 양쪽 요금이 발생할 수 있습니다. 혜택·비교기간 이후 부담·미래 요금 변동·가입 자격은 제외하며 미확인 총액은 확정하지 않습니다. 기능과 관리 선호에 따라 선택은 달라집니다.'}
    except (OSError,ValueError,TypeError,KeyError,StopIteration):
        return {'status':'error','code':'INVALID_RENEWAL_COMPARISON'}


def create_renewal_brief(session_id,access_token,offer_id,comparison_date,comparison_months,maintenance_monthly_fee=None,installation_conditions=None,planned_start_date="",card_id="none",card_spend=None,card_eligibility="unconfirmed",card_application_date=""):
    """도구로 재검증한 유지/재구독 결과만 준비서에 저장."""
    from 정수기프로젝트.app.mcp import tools
    from 정수기프로젝트.app.consent import ConsentStore
    from pathlib import Path
    result=compare_retention_renewal(session_id,access_token,offer_id,comparison_date,comparison_months,maintenance_monthly_fee,installation_conditions,planned_start_date,card_id,card_spend,card_eligibility,card_application_date)
    if 'renewal_options' not in result:return result
    keep, renew = result['renewal_options']
    def monthly(option):
        selected=option.get('selected_card_benefit') or {}
        total=option.get('selected_card_scenario_total') if selected.get('card_id') not in {None,'none'} and selected.get('eligibility')!='unconfirmed' else option['estimated_total'] if option['estimated_total'] is not None else option.get('scenario_total')
        return f"{(total+comparison_months-1)//comparison_months:,}원" if total is not None else '확인 필요'
    facts=[
        f"현재 사용 제품: {keep['model_id']}",
        f"관심 제품: {renew['model_id']}",
        f"제품 전환 검토일: {result['renewal_start']}",
        f"비교 검토 기준일: {result['comparison_start']}",
        f"비교 기간: {result['comparison_start']} ~ {result['comparison_end']} ({comparison_months}개월)",
        f"기존 제품 유지: 월평균 {monthly(keep)}. 계약 종료 후 유지비는 가상 가정 포함",
        f"관심 제품으로 전환: 월평균 참고 부담 {monthly(renew)}. 미확인 초기비·향후 가입 조건은 제외",
        f"기존 계약 해지 비용: {renew['exit_cost_total']:,}원 (가상 계약 기준)",
        '위 월평균은 비교 기간의 지출을 나눈 값이며 실제 매월 청구되는 요금이 아닙니다.',
    ]
    for option in (keep,renew):
        label='기존 제품 유지' if option['choice']=='keep' else '기존 계약 정산 후 재구독'
        total=f"{option['estimated_total']:,}원" if option['estimated_total'] is not None else '미확정'
        facts.append(f"[상세] {label} 총액: {total}")
    facts.append(f"[상세] 비교 종료 후 남는 계약/의무기간: {renew['remaining_contract_months']}개월 / "+(f"{renew['remaining_mandatory_months']}개월" if renew['remaining_mandatory_months'] is not None else '확인 필요'))
    benefit=renew.get('renewal_benefit',{})
    if renew.get('selected_card_benefit'):
        chosen=renew['selected_card_benefit']
        spend_label = f"{chosen['recognized_spend']:,}원" if chosen.get("recognized_spend") is not None else "미입력"
        eligibility_label = {"unconfirmed": "자격 미확인", "base": "기본 할인 조건 충족", "promotion": "행사 추가 할인 조건 충족"}.get(chosen.get("eligibility"), "자격 미확인")
        facts.append(f"선택 카드: {chosen['card_name']}, 인정실적 {spend_label}, {eligibility_label}. 이 조건의 참고 총액 {renew['selected_card_scenario_total']:,}원. 연회비·포인트 별도")
    if renew.get('maximum_card_benefit',{}).get('best'):
        best=renew['maximum_card_benefit']['best']
        facts.append(f"최대 카드 혜택 가정의 비교기간 총액: {renew['maximum_card_scenario_total']:,}원. 카드 {best['card_name']}, 월 인정실적 {best['required_spend']:,}원, 연회비 {best['annual_fee']:,}원 별도")
    facts.append('재구독 할인 대상 기간: '+benefit.get('window_start','')+' ~ '+benefit.get('window_end',''))
    facts.append('재구독 할인: '+benefit.get('note','확인 필요'))
    if renew.get('maximum_benefit_scenario_total') is not None:facts.append(f"최대 5% 적용 가정의 참고 총액: {renew['maximum_benefit_scenario_total']:,}원. 확정 청구액 아님")
    facts.append('[상세] '+result['limitations'])
    summary=(f"현재 {keep['model_id']}를 사용하고 있고, {renew['model_id']}로 바꾸는 것을 고민하고 있습니다. "
             f"{result['renewal_start']}에 전환하는 경우를 {comparison_months}개월 기준으로 비교했습니다. "
             "기존 계약 정산과 새 제품의 요금·설치비를 모두 포함한 최종 조건을 확인하고 싶습니다.")
    question_map={
        'future_price':'전환하려는 날짜에 실제 적용되는 월요금은 얼마인가요? 할인 종료 후 월요금도 알려주세요.',
        'installation_fee':'기본 설치비와 우리 집 설치 환경에 따른 추가 비용을 합하면 얼마인가요?',
        'registration_fee':'등록비가 있나요? 면제되는 조건이 있다면 함께 알려주세요.',
        'other_initial_fee':'설치비·등록비 외에 처음에 내야 하는 비용이 있나요?',
        'new_subscription_terms':'신규 가입이 가능한가요? 의무사용기간과 전체 계약기간, 관리 방식은 어떻게 되나요?',
        'maintenance_monthly_fee':'현재 제품을 계속 쓰면 관리·필터 비용은 얼마인가요?',
    }
    missing=[question_map[k] for k in renew['missing_fields'] if k in question_map]
    if any(k in renew['missing_fields'] for k in ('pump_needed','breaker_needed','drilling_needed','surface_material','outlet_needed','external_outlet_drilling','external_water_drilling','thick_sink','drilling_target')):
        missing.append('설치 현장을 확인했을 때 추가 작업이 필요한가요? 추가 견적을 알려주세요.')
    missing=list(dict.fromkeys(missing))
    missing.append('현재 계약을 정산하고 새 제품을 시작할 때 요금이 겹치는 기간이나 추가 정산 비용이 있나요?')
    missing.append('현재 제품 유지와 새 제품 전환의 최종 견적을 같은 기간 기준으로 받을 수 있나요?')
    brief=tools.create_consultation_brief(summary,facts,missing,result['source_ids'])
    if brief['status']!='ok':return brief
    try:ConsentStore().register_brief(brief['brief_id'],session_id,access_token,brief['absolute_path'])
    except Exception:
        Path(brief['absolute_path']).unlink(missing_ok=True)
        return {'status':'error','code':'BRIEF_REGISTER_FAILED'}
    brief.pop('absolute_path',None)
    return {**result,**brief,'status':'ok','download_path':'/briefs/'+brief['brief_id']}
