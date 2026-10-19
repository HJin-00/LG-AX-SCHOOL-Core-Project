"""명확한 분쟁 신호에 대한 계산 범위 제한. 도구 선택은 LLM이 수행합니다."""
import json
import re

FINANCIAL_TOOLS={'assess_exit_costs','assess_contract_document_costs','compare_contract_options','compare_retention_renewal','create_renewal_brief'}
REASONS={'personal','feature_upgrade','service_dispute'}


def consultation_reason(context):
    entries=[h.get('content','') for h in context.get('history',[]) if h.get('role')=='user']+[context.get('turn_message','')]
    reason='unspecified'
    for text in entries:
        compact=re.sub(r'\s+','',text).lower()
        explicit=None
        if '{' in text:
            try:explicit=json.loads(text[text.index('{'):]).get('exit_reason')
            except (ValueError,TypeError,AttributeError):pass
        dispute=bool(re.search(r'관리.{0,12}(?:안해|안돼|못받|미이행|지연|늦|안왔)|방문.{0,12}(?:안와|안왔|지연|늦)|필터.{0,12}(?:지연|안해|못받)|(?:고장|하자).{0,10}(?:반복|계속)|수리.{0,12}(?:반복|받았.*또|지연)|(?:as|a/s).{0,10}(?:지연|늦|못받|안돼)',compact))
        if dispute:reason='service_dispute'
        elif explicit in REASONS:reason=explicit
        elif re.search(r'문제.{0,5}해결|관리.{0,5}정상|분쟁.{0,6}별개',compact):reason='feature_upgrade' if re.search(r'기능|얼음|교체',compact) else 'personal'
        elif reason!='service_dispute' and '해지' in compact and re.search(r'말고|원해|원하지|비용|정산|계산',compact):reason='cancellation_requested'
        elif reason!='service_dispute':
            if re.search(r'(?:온수|냉수|물).{0,8}(?:안나|나오지|미지근|안돼)|누수|이상한냄새|소음',compact):
                reason='usage_discomfort'
                continue
            if re.search(r'개인사정|경제적|부담돼|해외이주',compact):reason='personal'
            elif re.search(r'얼음.{0,8}(?:필요|원해)|기능.{0,8}(?:부족|추가)|더작은|공간',compact):reason='feature_upgrade'
            elif re.search(r'(?:불편|고장).{0,15}(?:해지|교체|바꾸)',compact):reason='needs_reason'
            elif reason=='unspecified' and re.search(r'(?:바꾸|바꿀|교체|재구독).{0,16}(?:고민|싶|하려|예정)|다른정수기로바꾸',compact):reason='needs_reason'
    return reason


def restricted_result(reason):
    if reason=='needs_reason':
        return {'status':'needs_info','missing_fields':['exit_reason'],'message':'현재 정수기의 사용·관리에 불편이 있어서인지, 원하는 기능이나 비용 조건 때문에 바꾸려는 것인지 알려주시겠어요?'}
    return {'status':'needs_info','missing_fields':['service_history'],'message':'관리 미이행·반복 고장은 서비스 이행과 계약 조건 확인이 먼저 필요합니다. 일반 해지 계산으로 최종 비용이나 위약금 면제를 확정할 수 없습니다. 약정 관리 주기와 최근 요청·방문·수리 이력을 알려주세요.'}


def reason_response_override(context):
    reason=consultation_reason(context)
    if reason!='service_dispute':return None
    message=context.get('turn_message','')
    selected_reason=False
    if '{' in message:
        try:selected_reason=json.loads(message[message.index('{'):]).get('exit_reason')=='service_dispute'
        except (ValueError,TypeError,AttributeError):pass
    if not selected_reason and not re.search(r'비용|위약금|면제|해지|바꾸|바꿀|교체|service_history',message):return None
    has_history=False
    for entry in [*context.get('history',[]),{'role':'user','content':message}]:
        content=entry.get('content','')
        if entry.get('role')!='user' or '{' not in content:continue
        try:
            supplied=json.loads(content[content.index('{'):]).get('service_history')
            if isinstance(supplied,str) and supplied.strip():has_history=True
        except (ValueError,TypeError,AttributeError):pass
    if not has_history:return restricted_result(reason)
    return {'status':'answered','missing_fields':[],'message':'관리·수리 이력은 확인했습니다. 다만 이 정보만으로 사업자 책임이나 위약금 면제를 확정할 수 없습니다. 약정 관리 주기와 실제 요청·방문·수리 기록, 증상 지속 여부, 계약서를 함께 준비해 공식 상담에서 확인하세요. 일반 개인 사정 해지 계산을 최종 부담으로 적용하지 않겠습니다.'}
