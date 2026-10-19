import json
import shutil
import pytest
from 정수기프로젝트.app.rag.approved_loader import ROOT, ApprovedSourceError, load_approved_documents, approved_chunks, sections
from 정수기프로젝트.app.rag.retriever import search_contract_knowledge

def test_approved_snapshot_has_58_hash_verified_sources():
    docs=load_approved_documents()
    assert len(docs)==58
    assert len({d['document_id'] for d in docs})==58

def test_kca_qa_keeps_43_question_answer_records():
    doc=next(d for d in load_approved_documents() if d['document_id']=='KCA-QA-20250725')
    records=sections(doc['body'])
    assert len(records)==43
    assert all('### 질문' in r and '### 답변' in r for r in records)

def test_kca_does_not_become_contract_or_current_law_rule():
    for purpose in ['LG_contract_calculation','current_legal_determination']:
        chunks,_=approved_chunks(purpose)
        assert not chunks

def test_unknown_model_does_not_borrow_other_manual_or_common_button_steps():
    chunks,_=approved_chunks(model_id='WU923AWB')
    assert not any(c['document_id'].startswith('LG-WD520') for c in chunks)
    assert not any(c['document_id']=='LG-HOT' for c in chunks)
    own,_=approved_chunks(model_id='WD520VCT')
    assert any(c['document_id']=='LG-WD520-MANUAL-CURRENT' for c in own)

def test_html_and_cell_json_are_not_split():
    table='<table>'+('rowspan="2" cell\n\n'*200)+'</table>'
    structured='```json\n{"rows": [["조건", "예외"]]}\n```'
    pieces=sections('머리말\n\n'+table+'\n\n'+structured)
    assert any(table in p for p in pieces)
    assert any(structured in p for p in pieces)

def test_tampered_snapshot_fails_closed(tmp_path):
    shutil.copytree(ROOT,tmp_path/'approved')
    manifest=json.loads((tmp_path/'approved/manifest.json').read_text())
    p=tmp_path/'approved'/manifest['documents'][0]['file']
    p.write_text(p.read_text()+'\n변경')
    with pytest.raises(ApprovedSourceError):load_approved_documents(tmp_path/'approved')

def test_new_reference_search_keeps_approval_limit_and_iso_date():
    found=search_contract_knowledge('방문판매 청약철회 서면')
    assert found['status']=='ok'
    hits=[d for d in found['documents'] if 'approval_id' in d]
    assert hits
    assert all('승인 범위' in d['interpretation'] for d in hits)
    assert all(d['checked_at'] is None or len(d['checked_at'])==10 for d in hits)


def test_structured_table_rows_are_kept_together():
    table='[TABLE_ROWS]'+('cell '*2200)+'[/TABLE_ROWS]'
    parts=sections('설명\n\n'+table+'\n\n예외와 조건')
    assert any(table in part for part in parts)

def test_approved_common_subscription_document_is_searchable():
    chunks,excluded=approved_chunks()
    assert any(c['document_id']=='LG-SUB' for c in chunks)
    assert 'LG-SUB' not in excluded


def test_invalid_update_keeps_previous_snapshot(tmp_path):
    from 정수기프로젝트.app.rag.sync_approved import sync
    destination=tmp_path/'active';destination.mkdir()
    (destination/'manifest.json').write_text('{"documents":[]}')
    before=(destination/'manifest.json').read_bytes()
    source=tmp_path/'source';state=source/'수집관리/자동화상태';state.mkdir(parents=True)
    (state/'approval_state.json').write_text('{"current":{"X":{"approval_status":"approved","enabled":true}}}')
    (state/'index_candidates.json').write_text('{"documents":{}}')
    with pytest.raises(ApprovedSourceError):sync(source,apply=True,destination=destination)
    assert (destination/'manifest.json').read_bytes()==before
