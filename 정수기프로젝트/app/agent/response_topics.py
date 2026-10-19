"""도구 선택에 관여하지 않는다. 실제 실행 결과를 화면 주제로 표시한다."""
import re
def customer_question(message):
    body=re.sub(r'^\[상담 (?:주제|시작): [^\]]+\]\s*','',message)
    return body


def response_route(message,reply,observations):
    observations=[o for o in observations if o.get('status')!='tool_selection_required']
    if reply.status=='needs_info' and 'exit_date' in reply.missing_fields:return 'cancel'
    cards={c.type for c in reply.cards}
    if cards&{'renewal_catalog','renewal_comparison','renewal_timing'}:return 'renewal'
    if cards&{'comparison'}:return 'cancel'
    for observation in reversed(observations):
        name=observation.get('_tool_name')
        route={'lookup_contract_document':'contract','assess_contract_document_costs':'cancel','compare_contract_options':'cancel','create_renewal_brief':'renewal','create_contract_document_brief':'contract'}.get(name)
        if route:return route
        if name=='lookup_product_features':
            question=customer_question(message)
            if re.search(r'가격|얼마|혜택|할인|쿠폰',question):return 'product_information'
            return 'features'
    if reply.topic=='troubleshoot':return 'troubleshoot'
    if reply.topic=='contract':return 'cancel' if re.search(r'비용|위약금|해지',customer_question(message)) else 'contract'
    if reply.topic=='care_subscription':return 'care'
    return None
