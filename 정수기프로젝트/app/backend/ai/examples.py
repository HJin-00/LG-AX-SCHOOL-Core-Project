"""Swagger UI에 표시하는 합성 요청/응답. 실제 LG 자료가 아니다."""
REQUEST_EXAMPLES = {
    "first_turn": {"summary": "첫 질문 → needs_info (고정 응답)", "value": {
        "session_id": "demo-session-001", "message": "정수기에서 온수가 안 나와요"}},
    "with_model": {"summary": "모델 입력 → answered (연결 확인만)", "value": {
        "session_id": "demo-session-001", "message": "모델명을 입력할게요", "product_model": "DEMO-P1",
        "context_input": {"symptom": "온수가 안 나옴", "lock_status": "unlocked"}}},
    "correct_date": {"summary": "날짜 정정 (이전 세션에 병합)", "value": {
        "session_id": "demo-session-002", "message": "해지 검토일을 바꿀게요",
        "context_input": {"mandatory_end": "2026-08-31", "contract_end": "2028-08-31", "exit_date": "2026-08-30"}}},
    "demo_contract": {"summary": "가상 계약 ID (금액 계산은 E 연결 후)", "value": {
        "session_id": "demo-session-003", "message": "가상 계약의 비용을 확인하고 싶어요", "demo_fixture_id": "DEMO-D"}},
    "clear_context": {"summary": "문맥 초기화 (null)", "value": {
        "session_id": "demo-session-001", "message": "다시 시작할게요", "product_model": None, "context_input": None}},
    "empty_message": {"summary": "오류 422: 공백 메시지", "value": {
        "session_id": "demo-session-001", "message": "   "}},
    "invalid_date": {"summary": "오류 422: 존재하지 않는 날짜", "value": {
        "session_id": "demo-session-001", "message": "날짜 확인", "context_input": {"exit_date": "2026-02-30"}}},
}

BASE_RESPONSE = {"status": "needs_info", "topic": "unknown",
                 "answer": "[API 연결 테스트] 실제 AI 상담은 아직 연결되지 않았습니다. 정수기 모델명을 알려주시겠어요?",
                 "sources": [], "cards": [], "missing_fields": ["product_model"], "brief_id": None,
                 "error": None, "trace_id": "0" * 32}

SUCCESS_EXAMPLES = {
    "needs_info": {"summary": "200: 정보 부족", "value": BASE_RESPONSE},
    "answered": {"summary": "200: 연결 확인", "value": {
        **BASE_RESPONSE, "status": "answered", "missing_fields": [],
        "answer": "[API 연결 테스트] 모델과 입력 형식을 확인했습니다. 실제 제품 안내·계약 계산·Tool 실행은 A/D/E 연결 후 제공됩니다."}},
    "contract_null": {"summary": "통합 후 응답 구조 예: 미확인 총액 null (고정 모드에서 계산하지 않음)", "value": {
        **BASE_RESPONSE, "topic": "contract", "answer": "합성 카드 형식 예시입니다. 반환금이 미확인이므로 최종 총액은 알 수 없습니다. 반환금 조건을 확인해 주시겠어요?",
        "missing_fields": ["discount_return"], "sources": [{"document_id": "SYNTH-01", "title": "기술평가용 합성 규칙", "url": None, "section": None, "model_id": None, "checked_at": None}],
        "cards": [{"type": "contract", "data": {
            "period_summary": {"mandatory_end": "2026-08-31", "contract_end": "2028-08-31", "exit_date": "2026-09-22"},
            "cost_items": [{"name": "회수비", "status": "confirmed", "amount": 50000, "source_ids": ["SYNTH-01"]},
                           {"name": "반환금", "status": "unverified", "amount": None, "source_ids": []}],
            "confirmed_subtotal": 50000, "estimated_total": None, "is_demo": True, "limitations": "실제 LG 계약·청구 금액이 아닙니다."}}]}},
    "brief_created": {"summary": "통합 후 응답 구조 예: E 생성·등록·검증 후에만 반환", "value": {
        **BASE_RESPONSE, "status": "brief_created", "missing_fields": [], "brief_id": "brief-demo-0001",
        "answer": "상담 준비서를 만들었습니다. 실제 상담 접수는 진행되지 않았습니다."}},
}

ERROR_SPECS = {
    404: ("BRIEF_NOT_FOUND", "준비서를 찾을 수 없습니다. 같은 대화에서 준비서를 다시 요청해 주세요.", False),
    409: ("SESSION_BUSY", "같은 대화의 이전 요청을 처리 중입니다. 완료 후 다시 요청해 주세요.", True),
    422: ("INVALID_REQUEST", "입력 형식이 올바르지 않습니다. 필수 값과 날짜를 확인해 주세요.", False),
    500: ("INTERNAL_ERROR", "API 처리 중 오류가 발생했습니다. 잠시 후 다시 요청해 주세요.", True),
    502: ("AGENT_FAILED", "Agent 처리에 실패했습니다. 잠시 후 다시 요청해 주세요.", True),
    503: ("AGENT_UNAVAILABLE", "Agent가 연결되지 않았습니다. 서버 담당자에게 연결 상태를 확인해 주세요.", True),
    504: ("AGENT_TIMEOUT", "응답 시간이 초과되었습니다. 잠시 후 다시 요청해 주세요.", True),
}


def error_example(code, answer, retryable=False, fields=None):
    return {**BASE_RESPONSE, "status": "error", "answer": answer, "missing_fields": [],
            "error": {"code": code, "retryable": retryable, "fields": fields or []}}
