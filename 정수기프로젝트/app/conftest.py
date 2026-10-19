"""기존 계산 회귀 검사는 변경 전 계약 fixture를 고정해 비교한다.
실제 새 계약 검증은 test_live_contract_dates.py에서 원본 PDF를 사용한다.
"""
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def offline_retrieval_by_default(monkeypatch):
    # 회귀 검사는 API 비용/네트워크에 의존하지 않는다. 하이브리드 전용
    # 검사는 명시적으로 재설정하며 실제 임베딩 검증은 별도 평가 스크립트로 실행한다.
    monkeypatch.setenv('RAG_SEARCH_MODE', 'keyword')
    monkeypatch.setenv('RAG_RERANK', 'false')

@pytest.fixture(autouse=True)
def historical_contract_fixture(request,monkeypatch):
    if request.node.path.name in {'test_live_contract_dates.py', 'test_mentor_contract_cases.py'}:return
    from 정수기프로젝트.app.mcp.contracts import contract_pdf
    monkeypatch.setattr(contract_pdf,'PDF_ROOT',Path(__file__).parent/'mcp/tests/fixtures/legacy_contracts')
