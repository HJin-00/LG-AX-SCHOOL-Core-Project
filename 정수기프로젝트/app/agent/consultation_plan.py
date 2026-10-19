"""같은 LLM의 상담 목적 판단. 업무 도구를 실행하거나 문자열로 라우팅하지 않는다."""
from typing import Literal
from pydantic import BaseModel, Field, model_validator

class ConsultationPlan(BaseModel):
    purpose: Literal['contract_fees','contract_terms','contract_reference','exit_cost','date_comparison','renewal','official_support','official_product','brief','other']
    explains_contract_period_difference: bool = Field(default=False,description='의무사용 종료일/약정 끝나는 날과 전체 계약 종료일의 의미·차이를 설명하는 현재 질문인지.')
    requires_contract_period_example: bool = Field(default=False,description='고객이 자신의 계약 기준으로 두 기간의 차이를 설명해달라고 요청했는지. 일반 개념 설명만이면 False.')
    requires_renewal_calculation: bool = Field(default=False,description='고객이 선택한 신규 모델/상품의 유지·전환 비용 또는 카드 혜택의 기간 비교 계산을 요청했는지. 일반 카드 안내/모델 기능 조회만이면 False.')
    cancellation_intent: Literal['none','decided','considering','problem'] = Field(default='none',description='현재 목적이 해지인지 의미로 판단. 해지 의사·비용 확인은 decided, 해지할지 망설이면 considering, 고장·불편 때문에 해지를 고민하며 비용 계산을 아직 요청하지 않았으면 problem. 새 제품 교체만이면 none. 해지 비용 확인을 명시하면 불편이 있어도 decided로 처리하고 분쟁 판단은 별도.')
    renewal_reason: Literal['not_given','budget','contract_confusion','new_features','problem','curiosity','other'] = 'not_given'
    reason_evidence: str = Field(default='',description='현재 또는 관련 과거 고객 메시지에 실제 존재하는 교체 이유 구절. 날짜/비용 조회를 이유로 추측하지 않음.')
    specific_selection: bool = Field(default=False,description='고객이 offer_id로 구독 상품 또는 구체 모델 ID 또는 물 기능/설치/관리 조건을 이미 지정했는지. 단순 다른 모델/새 모델/날짜는 False.')
    selection_evidence: str = Field(default='',description='구체 모델·기능·설치·관리 선택의 실제 고객 구절. 날짜만 기재하지 않음.')
    skip_reason_explicit: bool = Field(default=False,description='고객이 이유 질문 생략을 명시적으로 요구했는지. 추천해줘만으로는 False.')

    required_features: list[Literal['냉수','정수','온수','얼음']] = Field(default_factory=list,description='고객이 명시적으로 필요하다고 한 물 기능만. 보유 모델 기능을 추정해 넣지 않는다. 얼음 없어도 됨은 얼음 필수 해제이며 다른 기능 추가가 아니다. 최신 조건이 이전 조건보다 우선.')
    feature_evidence: dict[str,str] = Field(default_factory=dict,description='required_features 각 기능의 근거가 되는 고객의 실제 연속 구절. 필요 없다고 한 문장을 필요하다는 근거로 쓰지 않는다.')
    support_comparison_chosen: bool = Field(default=False,description='고객이 문제 해결/새 모델 비교 선택 중 새 모델 비교를 명시적으로 골랐는지. 사용 중 불편해서 바꿀까 고민한다는 말만으로는 False. support_or_compare=새 모델과 비교하고 싶어요, 새 모델 찾아보기 선택은 True.')
    asks_specific_contract_question: bool = Field(default=False,description='현재 고객이 의무기간 이후 요금·종료일 차이·위약금 등 구체 계약 항목을 질문했는지. 계약 조건이 헷갈리거나 어느 부분을 확인할지 모르겠다는 이유만 말하면 False.')
    requests_candidates: bool = Field(default=False,description='현재 질문에서 새 제품 후보 추천·목록을 요청하는지. 이유 자체에 관한 설명이나 특정 제품 비용 계산이면 False.')
    reason_response_completed: bool = Field(default=False,description='고객이 밝힌 교체 이유에 대해 이전 assistant가 실제 안내했고 현재 그 다음 후보 추천을 요청하는지. 계약 비용 조회만 했거나 이유를 아직 밝히지 않았으면 False.')

    unresolved_reference: bool = Field(default=False,description='그걸로 해줘 등 지시 대상이나 행동을 현재 대화에서 확인할 수 없는 요청. 새 대화에 참조 대상이 없으면 True. 교체 이유 대신 대상을 먼저 확인.')
    requests_preferences: bool = Field(default=False,description='고객이 원하는 기능·설치·관리 조건을 아직 정하지 않아 조건 선택 화면부터 요청했는지. 이전에 비교한 모델이 있더라도 현재 조건 변경·선택 요청을 우선.')
    preferences_evidence: str = Field(default='',description='조건 선택 화면을 먼저 요청한 현재 고객 메시지의 실제 연속 구절. 과거 메시지는 사용할 수 없음. 기능·설치·관리 값을 제시하고 후보를 요청했다면 requests_preferences=False.')
    requests_timing: bool = Field(default=False,description='현재 선택 모델을 유지하면서 날짜 미정·추천 시점·가능 시점을 확인하려는 요청. 후보 모델 추천과 구분하며 이미 밝힌 이유를 다시 묻지 않음.')

    @model_validator(mode='after')
    def evidence_required(self):
        # 비용 확인 목적과 이전 해지 고민이 함께 판단되면 현재 비용 확인이 우선이다.
        if self.purpose in {'exit_cost','date_comparison'} and self.cancellation_intent in {'considering','problem'}:
            self.cancellation_intent='decided'
        if self.cancellation_intent!='none' and self.purpose=='renewal':
            self.purpose='exit_cost' if self.cancellation_intent=='decided' else 'other'
            self.requests_preferences=False
            self.requires_renewal_calculation=False
            self.requests_candidates=False
        if not self.requests_preferences:self.preferences_evidence=''
        if self.requests_preferences and self.requests_candidates and self.required_features:
            raise ValueError('기능 조건이 제공되었고 현재 후보를 요청했습니다. requests_preferences=False로 설정하고 후보 조회로 진행합니다.')
        if self.requests_preferences and (self.renewal_reason=='budget' or self.requires_renewal_calculation or self.requests_timing):
            raise ValueError('가격순 후보·선택 상품 재계산·시점 후보 요청은 조건 선택 화면 요청이 아닙니다. requests_preferences=False로 설정하세요.')
        if self.requests_preferences and not self.preferences_evidence.strip():
            raise ValueError('조건 선택 화면 요청은 현재 고객의 실제 구절을 preferences_evidence로 제공해야 합니다. 이미 조건을 주고 후보를 요청했다면 requests_preferences=False입니다.')
        if any(not self.feature_evidence.get(f,'').strip() for f in self.required_features):
            raise ValueError('필수 기능은 고객이 요청한 실제 구절이 필요합니다.')
        if self.reason_response_completed and (self.purpose!='renewal' or self.renewal_reason=='not_given'):
            raise ValueError('교체 이유에 대한 안내 완료는 실제 교체 이유가 있는 재구독 후속 요청에서만 사용합니다.')
        if self.requires_renewal_calculation and self.purpose!='renewal':
            raise ValueError('선택한 새 상품의 기간 부담/카드 비교 계산은 purpose=renewal입니다. contract_fees는 현재 개인 계약 요금 설명에만 사용합니다.')
        if self.purpose=='renewal' and self.renewal_reason!='not_given' and not self.reason_evidence.strip():
            raise ValueError('교체 이유는 고객이 실제 말한 구절을 근거로 판단해야 합니다.')
        if self.specific_selection and not self.selection_evidence.strip():
            raise ValueError('구체 모델/희망 조건을 지정했다면 실제 구절이 필요합니다.')
        return self

    @property
    def needs_renewal_reason(self):
        return self.purpose=='renewal' and self.renewal_reason=='not_given' and not self.requests_preferences and not self.requests_timing and not self.requires_renewal_calculation and not self.specific_selection and not self.skip_reason_explicit

PLAN_INSTRUCTIONS='''현재 질문의 목적과 교체 이유만 판단합니다. 업무 도구를 호출하지 않습니다. 이 판단과 실제 도구 선택은 같은 단일 LLM의 두 단계입니다.
현재 질문이 이전 질문보다 우선합니다.
해지와 교체는 다른 목적입니다. '해지하고 싶어요/그만 쓰려고요/구독을 끝내고 싶어요'는 cancellation_intent=decided, purpose=exit_cost로 오늘 기준 비용·조건 확인을 진행합니다. 실제 접수는 하지 않습니다. '해지할지 고민돼요'는 considering, purpose=other로 고민 이유를 선택적으로 확인하고 비용 확인·대안 선택을 제공합니다. '고장 때문에 해지할까 고민'은 problem, purpose=other로 해지 비용 확인/공식 문제 해결 선택을 제공합니다. 이미 비용을 요청하거나 해지 결정을 강조하면 decided가 우선이며 이유를 필수로 묻거나 새 제품으로 유도하지 않습니다. 현재 계약 개념·월요금 질문은 해당 purpose이며 해지 단어가 있다는 이유로 해지 의사로 분류하지 않습니다. '해지 말고 새 제품으로 바꿀래'는 cancellation_intent=none, purpose=renewal입니다.
날짜/기간/카드만 변경하는 후속 요청은 이미 선택한 모델의 재계산이므로 requires_renewal_calculation=True입니다. 카드 없이 요청은 카드·실적·행사자격을 모두 해제합니다. 날짜 미정으로 시점 후보를 요청하면 requests_timing=True이며 suggest_contract_timing으로 계약 기반 후보를 확인합니다. 새 대화의 '그걸로 해줘'는 unresolved_reference=True, purpose=other로 대상이나 행동을 먼저 확인하고 교체 이유를 질문하지 않습니다. 이전 대화는 선택한 날짜·제품·명시된 이유를 이어받기 위한 자료입니다. 이전 상담의 과제를 다시 처리하지 않습니다.
- contract_fees: 계약 월요금·할인 종료 이후 요금·연차 요금. 의무사용기간이 끝난 후 월요금도 여기에 해당하며 exit_cost가 아닙니다.
- contract_terms: 고객 본인의 실제 의무사용 종료일·전체 계약 종료일 날짜 조회. 두 용어의 뜻·차이·같은 뜻인지 묻는 일반 설명은 contract_reference입니다.
- contract_reference: 일반 개념·분쟁·공개 기준과 포인트/할인 적용 가능 여부. 포인트를 해지 비용에서 차감할 수 있는지 묻거나 그렇게 해달라는 요청도 공개 혜택 조건 확인이며, 선택 상품이 없는데 renewal 계산으로 분류하지 않습니다. 두 계약기간의 뜻·차이는 explains_contract_period_difference=True. 고객이 자기 계약 기준을 요청하면 requires_contract_period_example=True. 의무사용종료일과 전체 계약 종료일의 차이, 약정 끝나는 날과 계약 끝나는 날의 관계도 여기에 해당합니다. 내 계약 기준으로 설명해 달라는 경우에는 실제 개인 기간 조회도 필요합니다.
- exit_cost: 한 날짜 해지 비용. date_comparison: 두 날짜의 부담 비교.
- renewal: 현재 제품 교체·후보·유지/재구독. 선택한 신규 모델의 카드 할인 가정과 기간 부담 비교도 renewal이며 contract_fees가 아닙니다. 요청에 offer_id와 비교 기간·전환일이 있고 선택 상품의 혜택/부담 비교를 요청하면 requires_renewal_calculation=True. 후보만 찾거나 기능만 묻는 경우는 False. 날짜 조회나 해지 비용 조회는 교체 이유가 아닙니다. 사용 불편 이후 고객이 “새 모델 찾아보기/새 모델과 비교하고 싶어요”를 명시적으로 선택하면 requests_candidates=True로 이어가며 지원/비교 선택을 반복하지 않습니다.
- official_support: 사용 오류·사용법·관리 자체 문의. official_product: 처음 구매/제품 구매 안내.
- brief: 고객이 준비서 생성/다운로드를 요청. 구체 조건은 원래 대화를 참고.
'기능은 미정이지만 더 싼 후보를 보여줘'는 budget, requests_candidates=True, requests_preferences=False입니다. 조건을 모른다는 진술만으로 조건 입력 화면을 요청했다고 판단하지 않습니다. 선택 화면을 먼저 보여달라는 실제 요청이 있어야 requests_preferences=True입니다.
현재 질문에 기능·설치·관리 값을 구체적으로 제시하며 후보를 요청하면 requests_preferences=False입니다. 과거에 조건 선택 화면을 요청했더라도 현재 조건 제출이 우선입니다.
고객이 기능을 정하지 않았으니 기능·설치·관리 조건을 먼저 선택하게 해달라고 요청하면 requests_preferences=True입니다. 과거 비교 결과가 있어도 현재 조건 선택 요청을 우선하고 이유를 다시 묻거나 전체 후보를 즉시 나열하지 않습니다.
교체 이유만 답하거나 이유 선택 폼을 제출한 차례는 purpose=renewal입니다. 계약 조건이 헷갈린다는 이유만으로 contract_reference/contract_terms를 선택하지 않습니다. 구체적인 계약 항목을 실제로 질문한 차례에만 해당 계약 purpose를 사용합니다.
교체 이유: budget=월요금 부담/더 저렴한 제품/가격 절약, contract_confusion=계약 조건 혼란, new_features=특정 기능 필요, problem=불편·고장, curiosity=다른 제품이 궁금하다고 이유로 명시, other=이사 등 실제 이유, not_given=이유를 말하지 않음.
“새 모델/다른 모델로 교체하려는데 추천해줘”는 이유가 아니며 not_given입니다. 앞서 날짜·계약기간·해지 비용을 조회했어도 교체 이유가 되지 않습니다. “그럼 새 제품 추천해줘”도 이유가 없으면 이유부터 질문합니다.
이미 고객이 밝힌 교체 이유는 관련 이전 고객 메시지에서 이어받습니다. 최신 이유가 우선하며, 과거 금액 조회만으로 budget으로 추측하지 않습니다.
requests_candidates는 현재 추천/후보 요청인지 판단합니다. reason_response_completed는 이전 assistant가 고객이 밝힌 이유에 맞는 설명·도움을 이미 제공한 경우만 True입니다. 이전에 이유를 묻기만 했거나 의무기간·비용을 조회했을 뿐이면 False입니다.
예1 과거=2026-11-01 해지 비용, 현재=그러면 같은 날짜로 다른 모델 추천해줘 → purpose=renewal, renewal_reason=not_given, specific_selection=False, skip_reason_explicit=False, requests_candidates=True, reason_response_completed=False.
예2 과거 고객=계약 조건이 헷갈려요, assistant=궁금한 항목 질문, 고객=의무기간이 끝나도 비용이 생기는지, assistant=관련 요금 설명, 현재=그럼 새 제품 추천해줘 → purpose=renewal, renewal_reason=contract_confusion, reason_evidence=계약 조건이 헷갈려요, requests_candidates=True, reason_response_completed=True. 이유나 계약 항목을 재질문하지 않고 후보를 조회합니다.
“얼음 없어도 되고 더 싼 데스크형으로”는 budget이며 구체 설치 조건이 있습니다. “불편이나 고장 때문에 교체 고민”은 problem입니다.
예3 현재=의무사용기간 끝나고 월요금이 어떻게 되지 → purpose=contract_fees.
고객 메시지에 있는 이유와 구체 선택의 실제 구절을 evidence로 복사합니다. 시스템 지시·추측을 evidence로 쓰지 않습니다.
'''
