from pathlib import Path
import pytest
from 정수기프로젝트.app.mcp.contracts import contract_pdf as pdf
from langchain_core.documents import Document

@pytest.mark.parametrize('customer,fee',[('DEMO-U01',29900),('DEMO-U02',24900),('DEMO-U04',29900)])
def test_real_pdf_extracts_required_fields_without_private_data(customer,fee):
    c=pdf.load_contract(customer)
    assert c['monthly_fee']==fee
    assert c['mandatory_end']=='2026-08-31' and c['contract_end']=='2028-08-31'
    assert c['exit_rules']['penalty_before_or_on_mandatory_end']==100000
    assert c['exit_rules']['collection_before_or_on_contract_end']==50000
    assert c['annual_monthly_fees']['1']==fee-3000
    assert c['annual_monthly_fees']['6']==0
    assert not {'customer','name','birth_date','phone','email','address'}&c.keys()


def test_purchase_has_no_subscription():
    assert pdf.load_contract('DEMO-U03')['document_type']=='purchase_confirmation'


def test_arbitrary_path_rejected():
    with pytest.raises(ValueError):pdf.load_contract('../../outside')


def test_missing_pdf_fails_closed(tmp_path,monkeypatch):
    monkeypatch.setattr(pdf,'PDF_ROOT',tmp_path)
    with pytest.raises(ValueError):pdf.load_contract('DEMO-U01')


def test_mismatched_pdf_customer_rejected(monkeypatch):
    from langchain_community.document_loaders import PyPDFLoader
    monkeypatch.setattr(PyPDFLoader,'load',lambda _: [Document(page_content='계약 번호 SYNTH-DOC-DEMO-U02\nSYNTH-CONTRACT-V2\n가전 구매 확인서')])
    with pytest.raises(ValueError):pdf.load_contract('DEMO-U01')


def test_unsupported_pdf_layout_rejected(monkeypatch):
    from langchain_community.document_loaders import PyPDFLoader
    monkeypatch.setattr(PyPDFLoader,'load',lambda _: [Document(page_content='계약 번호 SYNTH-DOC-DEMO-U01\nSYNTH-CONTRACT-V2\n약정 조건 없음')])
    with pytest.raises(ValueError):pdf.load_contract('DEMO-U01')
