"""현재 배포 PDF를 사용한 멘토링 사례 검증. 역사적 fixture로 대체하지 않는다."""
import csv
import json
from pathlib import Path
import pytest
from pypdf import PdfReader
from 정수기프로젝트.app.consent import ConsentStore
from 정수기프로젝트.app.mcp.contracts import contract_pdf as pdf, contract_documents as tools

@pytest.fixture
def sessions(tmp_path, monkeypatch):
    monkeypatch.setenv('CONSENT_BACKEND','sqlite')
    monkeypatch.setenv('CONSENT_DB',str(tmp_path/'consent.db'))
    store=ConsentStore()
    def grant(customer, scopes=None):
        s=store.create(customer)
        r=store.event(s['session_id'],s['session_key'],'grant',scopes or ['contract_terms','contract_costs'])
        return s['session_id'],r['tool_access_token']
    return store,grant

@pytest.mark.parametrize('customer,total',[('DEMO-U01',70000),('DEMO-U02',70000),('DEMO-U04',300000)])
def test_normal_case_current_costs(sessions,customer,total):
    _,grant=sessions; sid,token=grant(customer)
    r=tools.assess_contract_document_costs(sid,token,'2026-10-06')
    assert r['status']=='ok'
    assert r['estimated_total']==total==sum(i['amount'] for i in r['cost_items'])
    assert r['period_summary']['id']=='SYNTH-DOC-'+customer

def test_normal_purchase_is_not_subscription(sessions):
    _,grant=sessions;sid,token=grant('DEMO-U03')
    assert tools.assess_contract_document_costs(sid,token,'2026-10-06')['status']=='not_applicable'

def test_normal_mandatory_boundary_includes_extra_month_fee(sessions):
    _,grant=sessions;sid,token=grant('DEMO-U04')
    r=tools.compare_contract_options(sid,token,'2026-10-31','2026-11-01','')
    assert r['status']=='ok'
    assert r['comparison_date']=='2026-10-06'
    assert [o['exit_costs']['estimated_total'] for o in r['options']]==[300000,120000]
    assert [o['additional_total'] for o in r['options']]==[300000,149900]
    assert r['difference']==150100 and r['lower_cost_date']=='2026-11-01'

def test_normal_arrears_survive_contract_end(sessions):
    _,grant=sessions;sid,token=grant('DEMO-U04')
    r=tools.assess_contract_document_costs(sid,token,'2028-11-01')
    assert r['estimated_total']==30000
    assert [i['amount'] for i in r['cost_items']]==[0,0,0,30000]

def test_ambiguous_missing_date_requests_input(sessions):
    _,grant=sessions;sid,token=grant('DEMO-U04')
    assert tools.assess_contract_document_costs(sid,token,'')['missing_fields']==['exit_date']

def test_ambiguous_unpaid_current_month_cannot_compare(sessions,tmp_path,monkeypatch):
    _,grant=sessions;sid,token=grant('DEMO-U04')
    with tools.BILLING_PATH.open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    next(r for r in rows if r['customer_id']=='DEMO-U04')['current_month_paid']='0'
    path=tmp_path/'billing.csv'
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    monkeypatch.setattr(tools,'BILLING_PATH',path)
    r=tools.compare_contract_options(sid,token,'2026-10-31','2026-11-01','')
    assert r['status']=='needs_info' and r['missing_fields']==['current_month_payment']

def test_risk_invalid_date_never_calculates(sessions):
    _,grant=sessions;sid,token=grant('DEMO-U04')
    r=tools.assess_contract_document_costs(sid,token,'2026-02-30')
    assert r['status']=='error' and r['estimated_total'] is None

def test_risk_other_session_token_denied(sessions):
    _,grant=sessions;a,ta=grant('DEMO-U01');b,tb=grant('DEMO-U04')
    assert tools.lookup_contract_document(a,tb)['status']=='forbidden'

@pytest.mark.parametrize('customer',['DEMO-U01','DEMO-U02','DEMO-U03','DEMO-U04'])
def test_pdfs_mask_nonessential_personal_data(customer):
    path=next(pdf.PDF_ROOT.glob(customer+'_*.pdf'))
    text='\\n'.join(p.extract_text() for p in PdfReader(path).pages)
    assert 'DEMO-BANK-****' in text and '010-****-****' in text
    assert '****-**-**' in text and 'd***@example.invalid' in text
    c=pdf.load_contract(customer)
    assert not {'name','birth_date','phone','email','address','bank_account'}&c.keys()

def test_u01_u04_are_different_business_cases():
    one=pdf.load_contract('DEMO-U01');four=pdf.load_contract('DEMO-U04')
    assert one['mandatory_end']<'2026-10-06'<four['mandatory_end']
    assert one['exit_rules']!=four['exit_rules']
    assert one['contract_start']!=four['contract_start']

def test_terms_scope_omits_cost_and_pii(sessions):
    _,grant=sessions;sid,token=grant('DEMO-U04',['contract_terms'])
    r=tools.lookup_contract_document(sid,token)
    assert set(r['terms'])=={'id','contract_start','mandatory_end','contract_end'}
    assert '정민수' not in json.dumps(r,ensure_ascii=False)
    assert tools.assess_contract_document_costs(sid,token,'2026-10-06')['code']=='CONSENT_SCOPE_REQUIRED'


def test_purchase_no_contract_result_not_overwritten_by_public_rag():
    from ai.response_guard import guard_response
    from 정수기프로젝트.app.rag.retriever import documents
    chunk=documents()[0]
    raw={'reply':{'status':'answered','topic':'contract','answer':'일반 안내','sources':[],'cards':[],'missing_fields':[]},
         'tool_results':[{'status':'not_applicable','source_ids':[],'message':'구독 계약이 없습니다.','_tool_name':'assess_contract_document_costs'},
                         {'status':'ok','documents':[{'chunk_id':chunk['chunk_id']}],'_tool_name':'search_contract_knowledge'}]}
    result=guard_response(raw)['reply']
    assert '구독 계약이 없습니다' in result['answer']
    assert result['sources']==[] and result['cards']==[]
