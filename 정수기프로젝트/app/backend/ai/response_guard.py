"""신뢰된 도구 관찰 결과로 비용·출처를 작성합니다. 도구를 선택하거나 호출하지 않습니다."""
from copy import deepcopy
from 정수기프로젝트.app.rag.retriever import documents, contextual_chunk
from .agent_adapter import ToolFailure

NOTICE = '시연용 합성 기준이며 실제 LG 계약·요금·법령 기준이 아닙니다.'
SYNTH = {'document_id': 'SYNTH-01', 'title': '시연용 합성 계약·비용 기준', 'checked_at': None}


def cost_text(result):
    items = result.get('cost_items', [])
    if not items or len(items) > 10:
        raise ToolFailure('비용 도구 결과를 확인할 수 없습니다.')
    subtotal = 0
    unknown = False
    lines = []
    for item in items:
        status, amount = item.get('status'), item.get('amount')
        if status not in {'confirmed', 'not_applicable', 'unverified'}:
            raise ToolFailure('비용 항목 상태가 올바르지 않습니다.')
        if status == 'unverified' or amount is None:
            unknown = True
            label = '미확인'
        elif type(amount) is not int or amount < 0:
            raise ToolFailure('비용 항목 금액이 올바르지 않습니다.')
        else:
            subtotal += amount
            label = '해당 없음' if status == 'not_applicable' else f'{amount:,}원'
        lines.append(f"- {item['name']}: {label}")
    total = result.get('estimated_total')
    if type(result.get('confirmed_subtotal')) is not int or subtotal != result['confirmed_subtotal']:
        raise ToolFailure('비용 항목과 소계가 일치하지 않습니다.')
    if (unknown and total is not None) or (not unknown and (type(total) is not int or total != subtotal)):
        raise ToolFailure('비용 항목과 총액이 일치하지 않습니다.')
    period = result['period_summary']
    heading = f"{period['exit_date']} 검토 기준 "
    heading += f'확인된 소계는 {subtotal:,}원이며 전체 예상 비용은 미확정입니다.' if total is None else f'예상 비용은 {total:,}원입니다.'
    return '\n'.join([heading, *lines,
        f"의무사용 종료일: {period['mandatory_end']}", f"전체 계약 종료일: {period['contract_end']}"])


def guard_response(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get('reply'), dict):
        return raw  # Pydantic이 원래 형식 오류를 보고합니다.
    result = deepcopy(raw)
    observations = result.pop('tool_results', None)
    if observations is None:
        return result  # 도구 관찰 없는 응답은 기본 스키마 검증으로 전달.
    if not isinstance(observations, list) or len(observations) > 30:
        raise ToolFailure('도구 실행 증거 형식이 올바르지 않습니다.')
    if any(not isinstance(item, dict) for item in observations):
        raise ToolFailure('도구 실행 증거 형식이 올바르지 않습니다.')
    reply = result['reply']
    costs = [item for item in observations if 'cost_items' in item and item.get('status') in {'ok', 'unverified'}]
    briefs = [item for item in observations if item.get('status') == 'ok' and item.get('brief_id')]
    terms = [item for item in observations if item.get('status') == 'ok' and item.get('terms')]
    synthetic = bool(costs or briefs or terms)
    if reply.get('status') == 'brief_created':
        matches = [item for item in briefs if item['brief_id'] == reply.get('brief_id')]
        if not matches:
            raise ToolFailure('준비서 생성 증거가 없습니다.')
        reply['answer'] = f"상담 준비서를 생성했습니다. 실제 상담 접수나 해지 신청은 진행되지 않았습니다. {NOTICE}"
    elif costs and reply.get('status') == 'answered':
        # 같은 날짜의 중복 관찰은 한 번만 표시합니다.
        unique = {item['period_summary']['exit_date']: item for item in costs}
        texts = [cost_text(item) for item in unique.values()]
        if len(texts) > 3:
            raise ToolFailure('한 응답에 비교할 날짜가 너무 많습니다.')
        if len(texts) > 1:
            texts.append('날짜 사이의 이용요금 등 별도 정산은 확인되지 않아 실제 총부담 차이를 확정할 수 없습니다.')
        reply['answer'] = '\n\n'.join([*texts, NOTICE])
    elif terms and reply.get('status') == 'answered':
        # 계약 조회는 근거이며 답변 주제를 기간 조회로 강제하지 않는다.
        # 비용 총액·권한·파일 검증은 각 전용 분기에서 유지한다.
        if not str(reply.get('answer','')).strip():
            raise ToolFailure('계약 질문에 대한 설명이 없습니다.')
    elif any(item.get('status') == 'not_applicable' for item in observations):
        reply.update(status='answered', topic='contract', missing_fields=[], brief_id=None,
                     answer='선택된 가상 고객에게 구독 계약이 없습니다. 이 시연은 실제 LG 고객 계약과 연동되지 않았습니다.')
        # 개인 구독 적용 제외를 일반 RAG 안내가 덮어쓰지 않는다.
        reply['sources'] = []
        reply['cards'] = []
        return result
    elif any(item.get('status') == 'forbidden' for item in observations):
        denied = next(item for item in reversed(observations) if item.get('status') == 'forbidden')
        message = denied.get('message', '동의 화면에서 필요한 조회 권한을 확인해 주세요.')
        if denied.get('code') == 'CONSENT_SCOPE_REQUIRED':
            message = ({'contract_costs':'비용 정보','care_info':'관리 일정 정보'}.get(denied.get('required_scope'),'계약기간 정보')) + ' 조회 범위에 추가 동의가 필요합니다. 동의 화면에서 확인해 주세요.'
        reply.update(status='needs_info', topic='contract', answer=message, missing_fields=['consent'], brief_id=None)
    # 모델이 생성한 확인일·URL을 사용하지 않고 검색된 청크의 로컬 메타데이터로 재구성합니다.
    catalog = {item['chunk_id']: item for item in documents()}
    from 정수기프로젝트.app.rag.approved_loader import approved_chunks
    try:
        approved,_=approved_chunks()
        catalog.update({item['chunk_id']:item for item in approved})
    except (ValueError,OSError,KeyError):
        if any('-approved-' in h.get('chunk_id','') for o in observations for h in o.get('documents',[])):
            raise ToolFailure('검색된 승인 자료를 다시 확인할 수 없습니다.')
    approved_retrieved=False
    official = []
    retrieved = []
    for observation in observations:
        for hit in observation.get('documents', []):
            chunk = catalog.get(hit.get('chunk_id'))
            if chunk:chunk=contextual_chunk(chunk)
            if chunk:
                approved_retrieved=approved_retrieved or '-approved-' in chunk['chunk_id']
                if chunk not in retrieved:
                    retrieved.append(chunk)
                source = {key: chunk.get(key) for key in ('document_id', 'title', 'url', 'section', 'model_id', 'checked_at')}
                if source not in official:
                    official.append(source)
    # 기간 개념은 모델이 고객 질문에 맞춰 설명한다. 내부 interpretation을 답변으로 붙이지 않는다.
    period_concept=any(chunk['chunk_id']=='LG-SUB-period' for chunk in retrieved)
    if retrieved and not period_concept and '-approved-' not in retrieved[0]['chunk_id'] and not synthetic and reply.get('status') == 'answered':
        reply['answer'] = '\n\n'.join(chunk['content'] + '\n' + chunk['interpretation'] for chunk in retrieved if '-approved-' not in chunk['chunk_id'])
        reply['topic'] = 'contract'
    # 승인된 사례도 고객 질문에 맞춘 설명을 유지한다. 해외 이주·관리 지연 등
    # 서로 다른 상황을 일괄 철회 체크리스트로 교체하지 않는다.
    if approved_retrieved and any(c['document_id'].startswith(('KCA','LAW')) and '-approved-' in c['chunk_id'] for c in retrieved) and not synthetic:
        reply['answer'] = '저장된 일반 상담 참고자료이며 현행 법령이나 개인 계약의 적용 결과를 확정한 안내가 아닙니다.\n\n' + reply['answer']
    reply['sources'] = ([dict(SYNTH)] if synthetic else []) + official
    if not synthetic and not any(item.get('status') == 'not_applicable' for item in observations) and any(source.get('document_id') == 'SYNTH-01' for source in raw['reply'].get('sources', [])):
        raise ToolFailure('개인 계약 도구 실행 증거가 없습니다.')
    if synthetic:
        reply['topic'] = 'contract'
    if len(reply.get('answer', '')) > 2000:
        raise ToolFailure('응답 길이가 허용 범위를 초과했습니다.')
    return result
