"""LLM이 선택한 검색 요청에 공개 검수 자료의 키워드·벡터 검색을 수행한다."""
import json
import os
import re
from datetime import date
from copy import deepcopy
from pathlib import Path

CATALOG = Path(__file__).parent / 'contract_documents.json'


def documents():
    return json.loads(CATALOG.read_text(encoding='utf-8'))['chunks']


def public_corpus():
    """인덱스 입력 경로를 공개 검수 자료 두 곳으로 한정한다."""
    from .approved_loader import approved_chunks
    approved, _ = approved_chunks()
    return [row for row in documents() if row['review_status'] == 'verified'] + approved


def keyword_ranking(query, chunks):
    normalized = re.sub(r'\s+', '', query.lower())
    terms = [t for t in re.findall(r'[가-힣A-Za-z0-9]+', query.lower())
             if len(t) >= 2 and not re.fullmatch(r'w[dsu][a-z0-9]+', t)
             and t not in {'알려줘', '알려주세요', '무엇인가요', '어떻게', '현재', '정수기', '관련', '확인'}]
    scored = []
    for chunk in chunks:
        if 'keywords' in chunk:
            score = 4 * sum(len(term) for term in chunk['keywords'] if term in normalized)
        else:
            body = re.sub(r'\s+', '', chunk['content'].lower())
            score = sum(len(term) for term in terms if term in body)
        if score:
            scored.append((score, chunk['chunk_id']))
    return sorted(scored, key=lambda row: (-row[0], row[1]))


def hybrid_ranking(keyword, semantic, curated_ids=(), *, reranked=False):
    """키워드 근거를 유지하면서 의미 검색 후보를 함께 순위화한다."""
    lexical = {ident: score / keyword[0][0] for score, ident in keyword} if keyword else {}
    vector = {ident: score / semantic[0][1] for ident, score in semantic} if semantic else {}
    if reranked:
        # 적합성을 다시 확인한 후보 밖의 일반 단어 일치가 상위로 복귀하지 않게 한다.
        return [ident for ident, _ in semantic]
    # 명시적인 검수 키워드 근거가 충분하면 기존 정확 일치를 우선한다.
    strong = bool(keyword and keyword[0][0] >= 8 and keyword[0][1] in curated_ids)
    weight = .75 if strong else .15
    scores = {ident: weight * lexical.get(ident, 0) + (1 - weight) * vector.get(ident, 0)
              for ident in lexical.keys() | vector.keys()}
    return sorted(scores, key=lambda ident: (-scores[ident], ident))


def contextual_chunk(chunk):
    """검색과 응답 검증에서 동일하게 행사 기간을 확인합니다."""
    row=deepcopy(chunk)
    if row.get('valid_until'):
        from 정수기프로젝트.app.backend.ai.server_context import reference_date
        day=date.fromisoformat(reference_date())
        if day>date.fromisoformat(row['valid_until']):
            row['content']='[신청기간 종료 — 과거 참고] '+row['content']
            row['interpretation']='새 신청의 현재 혜택으로 안내하거나 과거 행사로 신규 혜택 수령을 약속하지 않습니다. 기존 신청 고객의 지급 여부는 별도 확인이 필요합니다. '+row['interpretation']
        elif day<date.fromisoformat(row['valid_from']):
            row['content']='[신청기간 시작 전] '+row['content']
            row['interpretation']='현재 즉시 적용 가능한 혜택으로 안내하지 않습니다. '+row['interpretation']
        else:
            row['interpretation']='조회 기준일은 신청기간 안이지만 잔여 인원·개인 자격·행사 유지 여부는 확인되지 않았습니다. '+row['interpretation']
    return row


def search_contract_knowledge(query: str, limit: int = 3, purpose: str = 'consultation_reference', model_id: str = '', *, contract_only: bool = False) -> dict:
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        return {'status': 'needs_info', 'missing_fields': ['question'], 'documents': []}
    if type(limit) is not int or not 1 <= limit <= 4:
        return {'status': 'error', 'code': 'INVALID_LIMIT', 'documents': []}
    if purpose not in {'consultation_reference','evaluation','LG_contract_calculation','current_legal_determination'} or not isinstance(model_id,str) or len(model_id)>120:
        return {'status':'error','code':'INVALID_RETRIEVAL_SCOPE','documents':[]}
    candidates = [chunk for chunk in documents() if chunk['review_status'] == 'verified'
                  and not (contract_only and chunk['chunk_id'] == 'LG-SWITCH-conditions')]
    from .approved_loader import approved_chunks, ApprovedSourceError
    warning = None
    excluded = []
    try:
        extra, excluded = approved_chunks(purpose,model_id)
        for chunk in extra:
            if contract_only and not (chunk['document_id']=='LG-SUB' or chunk['document_id'].startswith(('KCA-RENTAL','KCA-QA','KCA-CAUTION','LAW-'))):continue
            candidates.append(chunk)
    except (ApprovedSourceError,OSError,KeyError,ValueError) as exc:
        warning='새 승인 자료 검증 실패로 기존 검색만 사용합니다: '+type(exc).__name__
    keyword = keyword_ranking(query, candidates)
    ranked = [ident for _, ident in keyword]
    by_id = {row['chunk_id']: row for row in candidates}
    mode, vector_warning = 'keyword', None
    reranked = False
    if os.environ.get('RAG_SEARCH_MODE', 'hybrid') == 'hybrid':
        try:
            from .vector_index import semantic_search
            semantic = semantic_search(query, public_corpus(), set(by_id))
            reranked = getattr(semantic, 'reranked', False)
            semantic = [(ident, score) for ident, score in semantic if ident in by_id]
            ranked = hybrid_ranking(keyword, semantic, {r['chunk_id'] for r in candidates if 'keywords' in r}, reranked=reranked)
            mode = 'hybrid'
        except Exception as exc:
            # 검색 장애가 계약 계산이나 상담 전체를 실패시키지 않게 한다.
            # 예외 메시지에는 요청/키가 섞일 수 있어 원문은 반환하지 않는다.
            from .vector_index import VectorIndexError
            vector_warning = str(exc) if isinstance(exc, VectorIndexError) else type(exc).__name__
    hits = [{key: value for key, value in contextual_chunk(by_id[ident]).items() if key not in {'keywords', 'review_status'}}
            for ident in ranked[:limit]]
    diagnostics = {'mode': mode, 'vector_warning': vector_warning}
    if mode == 'hybrid':
        diagnostics['reranked'] = reranked
    return {'status': 'ok' if hits else 'unverified', 'documents': hits,
            'retrieval': diagnostics,
            'limitations': '공개 안내의 일반 정보이며 개별 계약·최종 청구액을 확정하지 않습니다.', 'approved_update_warning':warning, 'oversized_sections_excluded':excluded,
            'usage_procedure_coverage':{'model_id':model_id,'complete':False,'notice':'현재 승인된 WD520/WU923 자료의 사용하기·문제해결 장 전체는 확인되지 않았습니다. 검색된 스펙·안전·관리·설치 문장을 버튼 조작 순서로 바꾸지 마세요. 다른 도구로 미수집 조작법을 확정할 수 없습니다.'} if model_id in {'WD520VCT','WU923AWB'} else None}
