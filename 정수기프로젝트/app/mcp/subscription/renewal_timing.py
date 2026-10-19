"""계약 종료에 근거한 검토 후보일. 경제적 최적일·설치 예약을 확정하지 않습니다."""
from datetime import timedelta
from 정수기프로젝트.app.mcp.contracts.contract_documents import _load, _day, SOURCE
from 정수기프로젝트.app.backend.ai.server_context import reference_date


def suggest_renewal_timing(session_id,access_token):
    contract,billing,failure=_load(session_id,access_token,'contract_terms')
    if failure:return failure
    today=_day(reference_date());end=_day(contract['contract_end'])
    next_day=end+timedelta(days=1)
    suggested=max(today,next_day)
    ended=today> end
    return {'status':'ok','is_demo':True,'rule_id':SOURCE,'reference_date':today.isoformat(),
            'mandatory_end':contract['mandatory_end'],'contract_end':end.isoformat(),'suggested_date':suggested.isoformat(),
            'contract_already_ended':ended,
            'reason':'전체 계약이 이미 종료돼 현재 기준일의 정산 조건을 확인할 수 있습니다.' if ended else '전체 계약 종료 다음 날입니다. 이 날짜와 다른 검토일의 정산·추가 구독료를 비교할 수 있습니다.',
            'limitations':'시연용 계약의 일정 후보입니다. 의무사용 종료일과 전체 계약 종료일은 다릅니다. 가장 저렴한 날짜나 설치 가능일을 보장하지 않으며 날짜별 정산과 기다리는 동안의 추가 구독료는 비용 조회·비교로 별도 확인합니다. 날짜 확정이나 실제 예약은 하지 않습니다.',
            'source_ids':[SOURCE]}
