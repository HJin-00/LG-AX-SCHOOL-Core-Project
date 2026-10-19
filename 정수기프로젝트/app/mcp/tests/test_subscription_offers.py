from copy import deepcopy
import csv
import pytest
from 정수기프로젝트.app.mcp.subscription import subscription_offers as offers


def test_loaded_rate_changes_and_unknown_fee():
    rows = offers.load_offers()
    assert len(rows) == 3
    assert [(r.start_month, r.end_month, r.monthly_fee) for r in rows[0].rates] == [(1,12,24900),(13,60,29900)]
    result = offers.lookup_subscription_offers('WD520VCT', '2028-09-01')
    assert len(result['offers']) == 2
    assert result['offers'][0]['installation_fee']==0
    assert result['offers'][0]['installation_fee_source_url'].startswith('https://www.lge.co.kr/')
    assert result['offers'][0]['installation_reference']['estimated_total'] is None
    assert result['offers'][1]['installation_fee']==0
    assert result['offers'][1]['unverified_fields']==[]
    assert all(r['is_demo'] and not r['benefits_included'] and r['source_url'] is None for r in result['offers'])


@pytest.mark.parametrize('day', ['2026-02-30', '2026-1-1'])
def test_missing_or_invalid_date(day):
    result = offers.lookup_subscription_offers(planned_start_date=day)
    assert result['status'] == 'needs_info'
    assert result['missing_fields'] == ['planned_start_date']


@pytest.mark.parametrize('day', ['2026-09-30','2031-01-01'])
def test_outside_offer_window(day):
    result=offers.lookup_subscription_offers(planned_start_date=day)
    assert all(o.get('price_is_snapshot') for o in result['offers'])  # Snapshot preview does not promise date eligibility.


def test_unknown_model_not_substituted():
    assert offers.lookup_subscription_offers('UNKNOWN','2026-10-07')['offers'] == []


@pytest.mark.parametrize('mutation', ['gap', 'overlap', 'short', 'mandatory', 'negative', 'demo_url'])
def test_invalid_conditions_rejected(mutation):
    row=deepcopy(offers.load_offers()[0].model_dump())
    if mutation == 'gap': row['rates'][1]['start_month']=14
    if mutation == 'overlap': row['rates'][1]['start_month']=12
    if mutation == 'short': row['rates'][1]['end_month']=59
    if mutation == 'mandatory': row['mandatory_months']=61
    if mutation == 'negative': row['registration_fee']=-1
    if mutation == 'demo_url': row['source_url']='https://www.lge.co.kr/'
    with pytest.raises(ValueError): offers.SubscriptionOffer.model_validate(row)


def test_official_pending_not_exposed(monkeypatch):
    row=offers.load_offers()[0].model_dump()
    row.update(source_kind='official',source_id='TEST-OFFICIAL',source_url='https://www.lge.co.kr/',review_status='pending')
    fixture=offers.SubscriptionOffer.model_validate(row)
    monkeypatch.setattr(offers,'load_offers',lambda:[fixture])
    assert all(o['source_id']!='TEST-OFFICIAL' for o in offers.lookup_subscription_offers(planned_start_date='2026-10-07')['offers'])


def test_csv_duplicate_and_orphan_fail_closed(tmp_path,monkeypatch):
    for kind in ('duplicate','orphan'):
        target=tmp_path/'offers.csv';rate=tmp_path/'rates.csv'
        target.write_bytes(offers.OFFER_PATH.read_bytes());rate.write_bytes(offers.RATE_PATH.read_bytes())
        if kind=='duplicate':
            rows=list(csv.DictReader(target.open(encoding='utf-8-sig')));rows.append(rows[0])
            with target.open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        else:
            with rate.open('a',encoding='utf-8',newline='') as f:csv.writer(f).writerow(['ORPHAN',1,60,100])
        with monkeypatch.context() as m:
            m.setattr(offers,'OFFER_PATH',target);m.setattr(offers,'RATE_PATH',rate)
            assert offers.lookup_subscription_offers(planned_start_date='2026-10-07')['code']=='OFFER_DATA_INVALID'


def test_official_installation_rules_separate_from_demo_price():
    from 정수기프로젝트.app.mcp.installation.installation_fees import lookup_installation_fee_rules
    desk=lookup_installation_fee_rules('WD520VCT')
    built=lookup_installation_fee_rules('WU923AWB')
    assert next(r for r in desk['items'] if r['work_type']=='drill_natural')['amount']==50000
    assert next(r for r in built['items'] if r['work_type']=='drill_natural')['amount']==100000
    ceramic=next(r for r in built['items'] if r['work_type']=='drill_ceramic')
    assert ceramic['amount'] is None and ceramic['status']=='unverified'
    assert all(r['source_kind']=='official' for r in desk['items'])
    assert lookup_installation_fee_rules('UNKNOWN')['items']==[]


def test_invalid_installation_data_fails_closed(tmp_path,monkeypatch):
    from 정수기프로젝트.app.mcp.installation import installation_fees
    p=tmp_path/'fees.csv'
    p.write_text('model_id,amount,review_status\nWD520VCT,-1,verified\n')
    monkeypatch.setattr(installation_fees,'RULE_PATH',p)
    assert installation_fees.lookup_installation_fee_rules('WD520VCT')['status']=='error'


def test_unscheduled_catalog_does_not_force_date(monkeypatch):
    monkeypatch.setenv('EVALUATION_REFERENCE_DATE','2026-10-07')
    result=offers.lookup_subscription_offers()
    assert result['status']=='ok' and result['catalog_only'] is True
    assert result['checked_for_date']=='2026-10-07'
    assert '날짜 미정' in result['limitations']


def test_low_monthly_fee_sort_and_shared_card_coverage():
    from 정수기프로젝트.app.mcp.subscription.subscription_offers import lookup_subscription_offers
    result=lookup_subscription_offers(sort_by='monthly_fee',exclude_model_id='WD520VCT')
    assert result['status']=='ok'
    offers=result['offers']
    fees=[o.get('display_monthly_fee') if o.get('display_monthly_fee') is not None else o['rates'][0]['monthly_fee'] for o in offers]
    assert fees==sorted(fees)
    assert all(o['model_id']!='WD520VCT' for o in offers)
    assert all(o['product']['card_benefits'] for o in offers)
