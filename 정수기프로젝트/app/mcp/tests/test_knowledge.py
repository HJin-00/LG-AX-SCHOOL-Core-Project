import asyncio
from 정수기프로젝트.app.rag.retriever import search_contract_knowledge
from 정수기프로젝트.app.mcp.client_adapter import call_tool


def test_general_contract_questions_retrieve_relevant_verified_chunks():
    expectations = [('의무기간이랑 전체 계약기간 차이가 뭐야?', 'LG-SUB-period'),
                    ('해지 전에 확인할 계약 항목은?', 'LG-SUB-checklist'),
                    ('월요금만 알면 위약금 계산되지?', 'LG-SUB-checklist'),
                    ('공식 해지 상담 고객센터', 'LG-SUB-channel')]
    for query, expected in expectations:
        result=search_contract_knowledge(query)
        assert result['status']=='ok'
        assert expected in [d['chunk_id'] for d in result['documents']]
        assert next(d for d in result['documents'] if d['chunk_id']==expected)['checked_at']=='2026-10-03'
    assert search_contract_knowledge('달 여행')['status']=='unverified'


def test_search_available_over_mcp_without_customer_auth():
    result=asyncio.run(call_tool('search_contract_knowledge', {'query':'의무기간 전체기간 차이'}))
    assert result['status']=='ok' and result['documents']


def test_end_of_contract_checklist_is_retrieved():
    result=search_contract_knowledge('구독 계약 종료 전에 확인할 항목')
    assert result['documents'][0]['chunk_id']=='LG-SUB-checklist'
