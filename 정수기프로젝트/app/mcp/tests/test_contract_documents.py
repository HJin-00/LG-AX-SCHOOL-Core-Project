import asyncio
import json
import csv
from copy import deepcopy
import pytest
from 정수기프로젝트.app.consent import ConsentStore
from 정수기프로젝트.app.mcp.contracts import contract_documents as v2
from 정수기프로젝트.app.mcp.client_adapter import call_tool,get_tool_specs,MCPToolError

def read_billing(path):
    with path.open(encoding='utf-8-sig',newline='') as file:
        return {'records':list(csv.DictReader(file))}


def write_billing(path,payload):
    rows=payload['records']
    with path.open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('CONSENT_BACKEND','sqlite')
    monkeypatch.setenv('CONSENT_DB',str(tmp_path/'consent.sqlite3'))
    contracts={'contracts':[v2.load_contract('DEMO-U0'+str(i)) for i in range(1,5)]}
    with v2.BILLING_PATH.open(encoding='utf-8-sig',newline='') as file:
        billing={'records':list(csv.DictReader(file))}
    cp=tmp_path/'contracts.json';bp=tmp_path/'billing.csv'
    cp.write_text(json.dumps(contracts));write_billing(bp,billing)
    def read_contract(customer):
        return next(c for c in json.loads(cp.read_text())['contracts'] if c['customer_id']==customer)
    monkeypatch.setattr(v2,'load_contract',read_contract);monkeypatch.setattr(v2,'BILLING_PATH',bp)
    store=ConsentStore()
    def grant(customer='DEMO-U01',scopes=None):
        session=store.create(customer)
        g=store.event(session['session_id'],session['session_key'],'grant',scopes or ['contract_terms','contract_costs'])
        return session,g['tool_access_token']
    return store,grant,cp,bp


def test_no_consent():
    assert v2.lookup_contract_document('','')['status']=='forbidden'
    assert v2.assess_contract_document_costs('','','2026-10-06')['status']=='forbidden'
    assert v2.compare_contract_options('','','2026-10-31','2026-11-01','2026-10-06')['status']=='forbidden'


def test_period_scope_and_privacy(setup):
    _,grant,_,_=setup;s,t=grant(scopes=['contract_terms'])
    r=v2.lookup_contract_document(s['session_id'],t)
    assert set(r['terms'])=={'id','contract_start','mandatory_end','contract_end'}
    denied=v2.assess_contract_document_costs(s['session_id'],t,'2026-10-06')
    assert denied['code']=='CONSENT_SCOPE_REQUIRED'
    assert denied['required_scope']=='contract_costs'


def test_full_scope_privacy(setup):
    _,grant,_,_=setup;s,t=grant()
    r=v2.lookup_contract_document(s['session_id'],t)
    assert r['terms']['monthly_fee']==29900
    text=json.dumps(r,ensure_ascii=False)
    for secret in ['이서연','1991-04-12','010-0000','example.invalid','DEMO-BANK','access_token','customer']:
        assert secret not in text
    assert r['document_id']=='SYNTH-DOC-DEMO-U01'


@pytest.mark.parametrize('day,total',[('2026-08-30',170000),('2026-08-31',170000),('2026-09-01',70000),('2028-08-31',70000),('2028-09-01',0)])
def test_boundaries(setup,day,total):
    _,grant,_,_=setup;s,t=grant();r=v2.assess_contract_document_costs(s['session_id'],t,day)
    assert r['estimated_total']==total
    assert sum(i['amount']for i in r['cost_items'])==total


def test_arrears_after_contract(setup):
    _,grant,_,_=setup;s,t=grant('DEMO-U04')
    assert v2.assess_contract_document_costs(s['session_id'],t,'2028-09-01')['estimated_total']==30000


@pytest.mark.parametrize('day',['2026-02-30','bad','2023-08-31'])
def test_invalid_date(setup,day):
    _,grant,_,_=setup;s,t=grant()
    assert v2.assess_contract_document_costs(s['session_id'],t,day)['status']=='error'


def test_missing_date(setup):
    _,grant,_,_=setup;s,t=grant()
    assert v2.assess_contract_document_costs(s['session_id'],t,'')['missing_fields']==['exit_date']


def test_purchase(setup):
    _,grant,_,_=setup;s,t=grant('DEMO-U03')
    assert v2.lookup_contract_document(s['session_id'],t)['status']=='not_applicable'
    assert v2.assess_contract_document_costs(s['session_id'],t,'2026-10-06')['status']=='not_applicable'


def test_revoke_and_profile_change(setup):
    store,grant,_,_=setup;s,t=grant()
    store.event(s['session_id'],s['session_key'],'revoke')
    assert v2.lookup_contract_document(s['session_id'],t)['status']=='forbidden'
    s,t=grant();store.event(s['session_id'],s['session_key'],'select_profile',customer='DEMO-U02')
    assert v2.lookup_contract_document(s['session_id'],t)['status']=='forbidden'


@pytest.mark.parametrize('customer,fee',[('DEMO-U01',29900),('DEMO-U02',24900),('DEMO-U04',29900)])
def test_month_boundary_comparison(setup,customer,fee):
    _,grant,_,_=setup;s,t=grant(customer)
    r=v2.compare_contract_options(s['session_id'],t,'2026-10-31','2026-11-01','2026-10-06')
    assert r['status']=='ok';assert r['difference']==fee
    assert r['options'][0]['additional_subscription_fee']==0
    assert r['options'][1]['additional_subscription_fee']==fee
    assert r['lower_cost_date']=='2026-10-31'


def test_reference_date_and_past(setup):
    _,grant,_,_=setup;s,t=grant()
    assert v2.compare_contract_options(s['session_id'],t,'2026-10-31','2026-11-01','2026-10-07')['status']=='needs_info'
    assert v2.compare_contract_options(s['session_id'],t,'2026-10-05','2026-11-01','2026-10-06')['status']=='error'


def test_equal_options(setup):
    _,grant,_,_=setup;s,t=grant()
    r=v2.compare_contract_options(s['session_id'],t,'2026-10-30','2026-10-31','2026-10-06')
    assert r['difference']==0 and r['lower_cost_date'] is None


def test_unpaid_month(setup):
    _,grant,_,bp=setup;s,t=grant()
    payload=read_billing(bp);payload['records'][0]['current_month_paid']=0;write_billing(bp,payload)
    r=v2.compare_contract_options(s['session_id'],t,'2026-10-31','2026-11-01','2026-10-06')
    assert r['missing_fields']==['current_month_payment']


def test_missing_contract_field_returns_error(setup):
    _,grant,cp,_=setup;s,t=grant()
    p=json.loads(cp.read_text());del p['contracts'][0]['monthly_fee'];cp.write_text(json.dumps(p))
    assert v2.lookup_contract_document(s['session_id'],t)['status']=='error'


def test_mcp_protocol_and_no_auth_in_schema(setup):
    _,grant,_,_=setup;s,t=grant()
    async def run():
        specs=await get_tool_specs()
        for row in specs:
            if row['name']in {'lookup_contract_document','assess_contract_document_costs','compare_contract_options'}:
                assert 'session_id'not in row['input_schema']['properties']
                assert 'access_token'not in row['input_schema']['properties']
        auth={'session_id':s['session_id'],'access_token':t}
        r=await call_tool('compare_contract_options',{'exit_date_a':'2026-10-31','exit_date_b':'2026-11-01','comparison_date':'2026-10-06'},trusted_authorization=auth)
        assert r['difference']==29900
        with pytest.raises(MCPToolError):
            await call_tool('lookup_contract_document',{'customer_id':'DEMO-U02'},trusted_authorization=auth)
    asyncio.run(run())


def test_expired_consent(setup):
    store,grant,_,_=setup;s,t=grant()
    with store.connect() as db:
        db.execute('UPDATE sessions SET expires=0 WHERE id=?',(s['session_id'],))
    assert v2.lookup_contract_document(s['session_id'],t)['code']=='SESSION_EXPIRED'


def test_cross_session_token(setup):
    _,grant,_,_=setup;sa,ta=grant();sb,tb=grant('DEMO-U02')
    assert v2.lookup_contract_document(sa['session_id'],tb)['code']=='INVALID_TOOL_TOKEN'
    assert v2.lookup_contract_document(sb['session_id'],tb)['terms']['monthly_fee']==24900


@pytest.mark.parametrize('bad',[-1,True,'29900',None])
def test_malformed_amount_fails_closed(setup,bad):
    _,grant,cp,_=setup;s,t=grant()
    p=json.loads(cp.read_text());p['contracts'][0]['monthly_fee']=bad;cp.write_text(json.dumps(p))
    assert v2.lookup_contract_document(s['session_id'],t)['code']=='CONTRACT_DATA_INVALID'


def test_discount_expiry_changes_extra_charge(setup):
    _,grant,_,bp=setup;s,t=grant()
    p=read_billing(bp);p['records'][0].update(as_of='2024-08-15',current_month_paid=26900,current_month_invoice=26900)
    write_billing(bp,p)
    # 당시 계약 연차의 청구금액은 요금표로 확인해야 하며 현재 월요금과 같다고 가정하면 안 됩니다.
    r=v2.compare_contract_options(s['session_id'],t,'2024-08-31','2024-09-01','2024-08-15')
    assert r['status']=='ok'
    assert r['difference']==29900
