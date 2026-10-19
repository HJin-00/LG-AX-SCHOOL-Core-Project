"""공개 MCP의 개인 계약 경로. 평가용 fixture 직접 함수는 tools.py에만 둡니다."""
from 정수기프로젝트.app.consent import ConsentStore, ConsentDenied
from 정수기프로젝트.app.mcp import tools


def denied_result(exc, **fields):
    messages = {
        'CONSENT_REQUIRED': '현재 활성 동의 권한이 없습니다. 동의 상태를 확인해 주세요.',
        'INVALID_TOOL_TOKEN': '전달된 조회 권한을 확인할 수 없습니다. 연결 설정 또는 최신 동의 권한을 확인해 주세요.',
        'SESSION_EXPIRED': '시연 세션이 만료되었습니다. 새 세션에서 다시 동의해 주세요.',
        'CONSENT_SCOPE_REQUIRED': '요청한 정보의 조회 범위에 추가 동의가 필요합니다.',
    }
    result = {'status': 'forbidden', 'code': exc.code, 'message': messages.get(exc.code, messages['CONSENT_REQUIRED']), **fields}
    if exc.required_scope:
        result['required_scope'] = exc.required_scope
    return result


def lookup_contract_terms(session_id: str, access_token: str) -> dict:
    try:
        profile = ConsentStore().authorize(session_id, access_token, 'contract_terms')
    except ConsentDenied as exc:
        return denied_result(exc, terms={})
    fixture = profile['contract_fixture_id']
    if fixture is None:
        return {'status':'not_applicable','is_demo':True,'terms':{},'message':'선택한 가상 고객은 구독 계약이 없습니다.'}
    result = tools.lookup_contract_terms(demo_fixture_id=fixture)
    if result.get('terms'):
        # 고정 평가일을 실제 대화의 오늘/검토일로 오해하지 않도록 제외합니다.
        result['terms'].pop('exit_date', None)
        try:
            ConsentStore().authorize(session_id, access_token, 'contract_costs')
        except ConsentDenied:
            for field in ('arrears', 'discount_return'):
                result['terms'].pop(field, None)
    return result


def assess_exit_costs(session_id: str, access_token: str, exit_date: str) -> dict:
    try:
        profile = ConsentStore().authorize(session_id, access_token, 'contract_costs')
    except ConsentDenied as exc:
        return denied_result(exc, estimated_total=None)
    if not profile['contract_fixture_id']:
        return {'status':'not_applicable','is_demo':True,'estimated_total':None}
    if not exit_date:
        return {'status':'needs_info','missing_fields':['exit_date'],'estimated_total':None}
    # 프로필·종료일·요율·미납을 LLM 인자로 덮어쓸 수 없습니다.
    return tools.assess_exit_costs(demo_fixture_id=profile['contract_fixture_id'],exit_date=exit_date)


def create_consultation_brief(session_id: str, access_token: str, exit_date: str = '') -> dict:
    """본문 사실은 모델 요약을 신뢰하지 않고 승인된 도구 결과로 작성합니다."""
    lookup = lookup_contract_terms(session_id, access_token)
    if lookup['status'] != 'ok':
        return lookup
    facts = []
    terms = lookup['terms']
    for key, label in (('mandatory_end', '의무사용 종료일'), ('contract_end', '전체 계약 종료일')):
        facts.append(f'{label}: {terms[key]}')
    questions = []
    if exit_date:
        cost = assess_exit_costs(session_id, access_token, exit_date)
        if cost['status'] not in {'ok', 'unverified'} or 'cost_items' not in cost:
            return cost
        facts.append(f'해지 검토일: {exit_date}')
        for item in cost['cost_items']:
            if item['status'] == 'unverified' or item['amount'] is None:
                questions.append(f"{item['name']}: 확인 필요")
            else:
                facts.append(f"{item['name']}: {item['amount']:,}원")
        facts.append(f"확인된 소계: {cost['confirmed_subtotal']:,}원")
        if cost['estimated_total'] is None:
            questions.append('전체 예상 비용: 미확인 항목이 있어 확정 불가')
        else:
            facts.append(f"예상 총액: {cost['estimated_total']:,}원")
    else:
        questions.append('비용 검토를 원하면 해지 검토일과 비용 조회 동의 확인 필요')
    result = tools.create_consultation_brief(
        '시연용 가상 계약의 기간·해지 검토 정보. 실제 LG 계약·요금·법령 기준이 아닙니다.',
        facts, questions, ['SYNTH-01'])
    if result['status'] != 'ok':
        return result
    try:
        ConsentStore().register_brief(result['brief_id'], session_id, access_token, result['absolute_path'])
    except Exception:
        from pathlib import Path
        Path(result['absolute_path']).unlink(missing_ok=True)
        return {'status': 'error', 'code': 'BRIEF_REGISTER_FAILED'}
    result.pop('absolute_path', None)
    result['download_path'] = '/briefs/' + result['brief_id']
    result['is_demo'] = True
    return result
