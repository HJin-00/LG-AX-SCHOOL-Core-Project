"""LLM이 판단한 현재 과제와 완료 결과에 맞는 다음 행동. 도구 선택은 하지 않는다."""
def answer_actions(purpose,reply,cancellation_intent="none"):
    if reply.status!='answered' or reply.missing_fields:
        return []
    if cancellation_intent in {'considering','problem'}:
        return ['exit_cost','official_support'] if cancellation_intent=='problem' else ['exit_cost','contract_fees','official_support']
    if cancellation_intent=='decided':
        return ['contract_terms','official_support']
    # 후보·계산 카드는 자체 선택/재계산 버튼이 있으므로 같은 행동을 중복하지 않는다.
    if any(c.type in {'renewal_catalog','renewal_comparison','renewal_timing','product'} for c in reply.cards):
        return []
    return {
        'contract_fees':['compare_new','exit_cost','contract_terms'],
        'contract_terms':['compare_new','exit_cost','contract_fees'],
        'contract_reference':['compare_new','exit_cost','contract_fees'],
        'exit_cost':['compare_new','contract_fees'],
        'date_comparison':['compare_new','contract_terms'],
    }.get(purpose,[])
