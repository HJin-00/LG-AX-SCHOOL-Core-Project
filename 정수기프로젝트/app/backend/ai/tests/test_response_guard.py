from copy import deepcopy
import pytest
from ai.response_guard import guard_response
from ai.agent_adapter import ToolFailure
from 정수기프로젝트.app.mcp import tools
from 정수기프로젝트.app.rag.retriever import search_contract_knowledge


def raw(observations, answer='100,000원 + 50,000원 - 20,000원', **fields):
    reply = dict(status='answered', topic='contract', answer=answer, sources=[
        {'document_id':'SYNTH-01','title':'잘못된 제목','checked_at':'2026-10-02'}],
        cards=[], missing_fields=[], brief_id=None)
    reply.update(fields)
    return {'reply': reply, 'tool_results': observations}


def test_cost_sign_and_unverified_total_are_authoritative():
    cost = tools.assess_exit_costs(demo_fixture_id='DEMO-A', exit_date='2026-08-31')
    reply = guard_response(raw([cost]))['reply']
    assert '170,000원' in reply['answer']
    assert '할인반환금(합성 규칙): 20,000원' in reply['answer']
    assert '- 20,000원' not in reply['answer']
    assert reply['sources'][0]['checked_at'] is None
    cost = tools.assess_exit_costs(demo_fixture_id='DEMO-D', exit_date='2026-10-02')
    reply = guard_response(raw([cost]))['reply']
    assert '전체 예상 비용은 미확정' in reply['answer']
    assert '할인반환금(합성 규칙): 미확인' in reply['answer']


def test_comparison_includes_unverified_additional_charges():
    costs = [tools.assess_exit_costs(demo_fixture_id='DEMO-A', exit_date=day)
             for day in ['2026-08-31','2026-09-01']]
    reply = guard_response(raw(costs))['reply']
    assert '170,000원' in reply['answer'] and '70,000원' in reply['answer']
    assert '이용요금' in reply['answer'] and '총부담 차이를 확정할 수 없습니다' in reply['answer']


def test_inconsistent_tool_totals_rejected():
    cost = tools.assess_exit_costs(demo_fixture_id='DEMO-A', exit_date='2026-08-31')
    cost['estimated_total'] = 130000
    with pytest.raises(ToolFailure): guard_response(raw([cost]))


def test_sources_are_from_retrieved_catalog_not_model():
    observation = search_contract_knowledge('의무기간과 전체 계약기간 차이')
    data = raw([observation], '의무사용 종료일은 약정상 의무적으로 이용하는 기간의 마지막 날이고, 전체 계약 종료일은 가입한 구독 계약의 마지막 날입니다.')
    data['reply']['sources'] = [{'document_id':'LG-SUB-20261003','title':'임의','checked_at':'2026-10-02'}]
    reply = guard_response(data)['reply']
    assert {s['checked_at'] for s in reply['sources']} == {h['checked_at'] for h in observation['documents']}
    assert all(s['title']!='임의' for s in reply['sources'])
    assert reply['answer']==data['reply']['answer']
    assert '일반 개념 설명:' not in reply['answer']


def test_fake_brief_rejected_and_real_brief_has_notice():
    with pytest.raises(ToolFailure):
        guard_response(raw([], status='brief_created', brief_id='fabricated-id'))
    reply = guard_response(raw([{'status':'ok','brief_id':'verified-id','is_demo':True}],
        status='brief_created', brief_id='verified-id'))['reply']
    assert '실제 상담 접수' in reply['answer'] and '합성' in reply['answer']


def test_no_contract_has_no_synthetic_source():
    data = raw([{'status':'not_applicable','terms':{},'is_demo':True}])
    data['reply']['sources'] = [{'document_id':'SYNTH-01','title':'임의 생성 출처'}]
    reply = guard_response(data)['reply']
    assert reply['sources']==[] and '구독 계약이 없습니다' in reply['answer']


def test_new_approved_source_survives_response_with_server_metadata():
    from 정수기프로젝트.app.rag.approved_loader import approved_chunks
    chunks,_=approved_chunks()
    chunk=next(c for c in chunks if c['document_id']=='KCA-QA-20250725')
    data=raw([{'status':'ok','documents':[chunk]}],answer='저장 상담 사례에서 확인할 항목입니다.')
    data['reply']['sources']=[]
    reply=guard_response(data)['reply']
    assert reply['sources'][0]['document_id']=='KCA-QA-20250725'
    assert '현행 법령' in reply['answer']


def test_approved_case_keeps_question_specific_explanation():
    from 정수기프로젝트.app.rag.approved_loader import approved_chunks
    chunks,_=approved_chunks()
    chunk=next(c for c in chunks if c['chunk_id']=='KCA-QA-20250725-approved-23')
    text='해외 이주 상황이라면 이전 설치 가능 여부, 이주 증빙과 계약서의 철거 비용을 함께 확인하세요.'
    reply=guard_response(raw([{'status':'ok','documents':[chunk]}],answer=text,sources=[]))['reply']
    assert text in reply['answer']
    assert '판매 방식과 계약일' not in reply['answer']
    assert '현행 법령이나 개인 계약의 적용 결과를 확정한 안내가 아닙니다' in reply['answer']
