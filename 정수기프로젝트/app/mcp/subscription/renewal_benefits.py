"""공식 최대 재구독 혜택의 날짜 조건과 별도 참고 시나리오. 확정 견적과 분리."""
from datetime import date, timedelta
SOURCE_ID='LG-RENEWAL-BENEFIT-20261013'
SOURCE_URL='https://www.lge.co.kr/home_app_subscribe/service_info'

def assess_renewal_benefit(contract_end, start, contract_months, charges, source_kind):
    end=date.fromisoformat(contract_end);day=date.fromisoformat(start)
    opens=end-timedelta(days=124)
    closes=end.replace(year=end.year+1,day=min(end.day,28)) if end.month==2 and end.day==29 else end.replace(year=end.year+1)
    eligible=opens<=day<=closes
    maximum=5 if eligible and contract_months==72 and source_kind=='official' else None
    saving=sum(row['amount']*5//100 for row in charges) if maximum else None
    return {'status':'conditional' if eligible else 'not_applicable','window_start':opens.isoformat(),'window_end':closes.isoformat(),'assessment_date':start,'assessment_basis':'전환일을 신규 청약일로 가정','days_to_contract_end':(end-day).days,'maximum_rate_percent':maximum,'confirmed_rate_percent':None,'maximum_scenario_saving':saving,'source':{'document_id':SOURCE_ID,'title':'LG 공식 재구독 할인 조건','url':SOURCE_URL,'checked_at':'2026-10-13'},'note':('재구독 대상 기간에 해당합니다. 6년 공식 상품의 최대 5% 적용을 가정한 별도 참고값이며 실제 요율·청약일·할인 기준금액·반값 행사 중복·원단위 처리·개인 가입 자격은 확정되지 않았습니다. 기본 비교 금액에서 다시 차감하지 않습니다.' if eligible else '전환일을 청약일로 가정하면 재구독 대상 기간 밖입니다. 기존 해지 정산은 별도이며 할인으로 면제되지 않습니다.')}
