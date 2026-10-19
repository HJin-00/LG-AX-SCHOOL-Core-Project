"""기본 청구할인과 등록·실제 혜택 기간을 분리한 조건부 카드 계산."""
import csv,calendar
from pathlib import Path
from datetime import date

def add_months(day,n):
    y,m=divmod(day.year*12+day.month-1+n,12);m+=1
    return date(y,m,min(day.day,calendar.monthrange(y,m)[1]))

def load_cards():
    cards={}
    with (Path(__file__).parent.parent/'data/official_subscription_cards.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            ident=row['id']
            if ident not in cards:
                cards[ident]={k:row[k] for k in ('id','name','promotion_start','promotion_end','conditions','source_url')}|{'annual_fee':int(row['annual_fee']),'months':int(row['months']),'tiers':[],
                  'promotion_service_start':row.get('promotion_service_start') or None,'promotion_service_end':row.get('promotion_service_end') or None,
                  'base_duration_note':'기본 할인은 매월 실적·자동납부 등 카드 조건 충족 가정. 추가 할인 기간 종료를 기본 할인 종료로 보지 않으며 카드사 변경 가능성 별도.'}
            cards[ident]['tiers'].append({k:int(row[k]) for k in ('spend','base','promotion')})
    return list(cards.values())

def card_scenario(card,charges,application_date,spend,eligibility):
    registered=card['promotion_start']<=application_date<=card['promotion_end']
    tiers=sorted(card['tiers'],key=lambda t:t['spend'],reverse=True)
    tier=next((t for t in tiers if spend is not None and spend>=t['spend']),None)
    used=0;items=[]
    for index,row in enumerate(charges,1):
        bill=row.get('charge_date') or add_months(date.fromisoformat(application_date),index-1).isoformat()
        service_ok=(not card['promotion_service_start'] or bill>=card['promotion_service_start']) and (not card['promotion_service_end'] or bill<=card['promotion_service_end'])
        base=tier['base'] if tier and eligibility in {'base','promotion'} else 0
        promo_eligible=bool(tier and eligibility=='promotion' and registered and service_ok and used<card['months'])
        extra=tier['promotion'] if promo_eligible else 0
        if promo_eligible:used+=1
        applied=min(row['amount'],base+extra)
        items.append({'month':index,'charge_date':bill,'before':row['amount'],'base_discount':min(row['amount'],base),'promotion_discount':max(0,applied-min(row['amount'],base)),
                      'card_discount':applied,'after':row['amount']-applied,'promotion_month':used if promo_eligible else None})
    return {'card_id':card['id'],'card_name':card['name'],'required_spend':tier['spend'] if tier else None,'recognized_spend':spend,'eligibility':eligibility,
            'annual_fee':card['annual_fee'],'benefit_months':card['months'],'subscription_after':sum(i['after']for i in items),'card_saving':sum(i['card_discount']for i in items),
            'monthly_items':items,'promotion_in_period':registered,'conditions':card['conditions'],'source_url':card['source_url'],'base_duration_note':card['base_duration_note']}

def maximum_card_scenario(charges,application_date):
    scenarios=[]
    for card in load_cards():
        tier=max(card['tiers'],key=lambda x:x['base']+x['promotion'])
        scenarios.append(card_scenario(card,charges,application_date,tier['spend'],'promotion'))
    best=min(scenarios,key=lambda x:(x['subscription_after'],x['required_spend'] or 0)) if scenarios else None
    return {'application_date':application_date,'best':best,'cards':scenarios,'note':'각 카드 최고 실적·브랜드·등록·자동납부를 충족하는 별도 참고 가정. 기본 할인과 추가 행사 기간을 분리하고 청구일별로 계산합니다. 포인트·연회비 별도, 다른 할인 가정과 합산하지 않습니다.'}

def selected_card_scenario(charges,application_date,card_id='none',spend=None,eligibility='unconfirmed'):
    if eligibility not in {'unconfirmed','base','promotion'}:raise ValueError('카드 자격 상태')
    if spend is not None and (type(spend)is not int or spend<0):raise ValueError('카드 실적')
    if card_id in {'','none'}:
        return {'card_id':'none','card_name':'카드 미사용','card_saving':0,'subscription_after':sum(r['amount']for r in charges),'monthly_items':[],
                'recognized_spend':spend,'eligibility':'unconfirmed','annual_fee':0,'note':'할인 전 금액입니다.'}
    card=next((c for c in load_cards() if c['id']==card_id),None)
    if not card:raise ValueError('카드 ID')
    result=card_scenario(card,charges,application_date,spend,eligibility)
    result['note']='선택한 카드·전월 인정실적·자격을 충족하는 가정입니다. 자격 미확인은 차감하지 않고, 기본 조건만 확인했으면 추가 행사 할인을 제외합니다. 연회비·포인트 별도.'
    return result
