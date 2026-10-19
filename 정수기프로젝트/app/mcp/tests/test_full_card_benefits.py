from 정수기프로젝트.app.mcp.subscription.card_benefits import load_cards,maximum_card_scenario

def test_all_ten_cards_and_no_point_as_cash():
    cards=load_cards();assert len(cards)==10
    assert max(t['base']+t['promotion'] for c in cards for t in c['tiers'])==42000
    shinhan=next(c for c in cards if c['id']=='shinhan')
    assert max(t['base']+t['promotion'] for t in shinhan['tiers'])==20000

def test_amount_cap_and_post_promotion_rate_segments():
    charges=[{'amount':24900}]*12+[{'amount':49900}]*24
    r=maximum_card_scenario(charges,'2026-10-14');best=r['best']
    assert best['card_id']=='woori_platinum'
    assert best['subscription_after']==24*7900
    assert all(i['after']==0 for i in best['monthly_items'][:12])
    assert best['required_spend']==2000000

def test_registration_outside_event_and_term_limit():
    r=maximum_card_scenario([{'amount':49900}]*73,'2026-12-01')
    platinum=next(c for c in r['cards'] if c['card_id']=='woori_platinum')
    assert platinum['monthly_items'][0]['card_discount']==40000
    assert platinum['monthly_items'][-1]['card_discount']==40000
    assert platinum['promotion_in_period'] is False


def test_kb_actual_service_start_and_36_37_boundary():
 from datetime import date
 from 정수기프로젝트.app.mcp.subscription.card_benefits import card_scenario,add_months
 kb=next(c for c in load_cards() if c['id']=='kb')
 before=card_scenario(kb,[{'charge_date':'2026-10-14','amount':49900},{'charge_date':'2026-11-14','amount':49900}],'2026-10-14',800000,'promotion')
 assert [i['card_discount'] for i in before['monthly_items']]==[15000,20000]
 charges=[{'charge_date':add_months(date(2026,11,1),i).isoformat(),'amount':49900} for i in range(37)]
 result=card_scenario(kb,charges,'2026-10-14',800000,'promotion')
 assert result['monthly_items'][35]['card_discount']==20000
 assert result['monthly_items'][36]['card_discount']==15000


def test_card_selection_no_card_unknown_spend_and_cap():
 from 정수기프로젝트.app.mcp.subscription.card_benefits import selected_card_scenario
 charges=[{'charge_date':'2026-11-01','amount':10900}]
 assert selected_card_scenario(charges,'2026-10-14')['card_saving']==0
 assert selected_card_scenario(charges,'2026-10-14','kb',800000,'unconfirmed')['card_saving']==0
 assert selected_card_scenario(charges,'2026-10-14','kb',299999,'promotion')['card_saving']==0
 assert selected_card_scenario(charges,'2026-10-14','kb',800000,'promotion')['card_saving']==10900
 assert selected_card_scenario(charges,'2026-12-01','kb',800000,'promotion')['card_saving']==10900
