"""수업 PyPDFLoader로 가상 계약 PDF를 읽고 계산용 항목만 추출합니다.

현재 팀의 표 형식 계약서 전용 파서입니다. 임의 계약서/OCR 지원으로 표현하지 않습니다.
추출값은 함수의 메모리 객체로만 사용하고 JSON·원문 대화 기록을 생성하지 않습니다.
"""
import re
from pathlib import Path

PDF_ROOT=Path(__file__).resolve().parents[3] / '04_Agent설계' / '제출자료' / '가상계약서'
ALLOWED={'DEMO-U01','DEMO-U02','DEMO-U03','DEMO-U04'}


def _match(pattern,text):
    m=re.search(pattern,text,re.M)
    if not m:raise ValueError('계약서 필수 항목을 추출할 수 없습니다.')
    return m


def _amounts(line):
    return [int(x.replace(',',''))for x in re.findall(r'([\d,]+)원',line)]


def load_contract(customer_id):
    from langchain_community.document_loaders import PyPDFLoader
    if customer_id not in ALLOWED:raise ValueError('허용하지 않은 고객')
    paths=list(PDF_ROOT.glob(customer_id+'_*.pdf'))
    if len(paths)!=1:raise ValueError('고객 계약서가 없거나 중복입니다.')
    from pypdf.errors import PdfReadError
    if paths[0].stat().st_size>10_000_000:raise ValueError('계약서 크기 제한')
    try:
        pages=PyPDFLoader(str(paths[0]),extraction_mode='layout').load()
    except (PdfReadError,OSError) as exc:
        raise ValueError('계약서 PDF 읽기 실패') from None
    text='\n'.join(p.page_content for p in pages)
    document_id=_match(r'^\s*계약 번호\s+(SYNTH-DOC-DEMO-U\d+)',text).group(1)
    if document_id!='SYNTH-DOC-'+customer_id or 'SYNTH-CONTRACT-V2'not in text:
        raise ValueError('문서 고객·규칙이 일치하지 않습니다.')
    if '가전 구매 확인서'in text:
        return {'customer_id':customer_id,'document_id':document_id,'document_type':'purchase_confirmation','is_demo':True,'rule_id':'SYNTH-CONTRACT-V2'}
    start=_match(r'계약일\s+(\d{4}-\d{2}-\d{2})',text).group(1)
    product=_match(r'^\s*정수기\s+(W[DU]\w+)\s+(.+?)\s+(\d{4}-\d{2}-\d{2})\s+(\d{4}-\d{2}-\d{2})\s*$',text)
    fee_line=_match(r'^\s*금액\s+(.+)$',text).group(1);fees=_amounts(fee_line)
    if len(fees)!=6:raise ValueError('연차별 요금표 확인 필요')
    monthly=_amounts(_match(r'^\s*할인 종류 / 기간\s+(.+)$',text).group(1))[-1]
    billing=_match(r'^\s*청구일 / 주기\s+(.+)$',text).group(1)
    day=int(_match(r'매월\s+(\d+)일',billing).group(1))
    if not all(x in billing for x in ['당월 달력 월','일할 없음','당월 납부금 반환 없음']):raise ValueError('지원하지 않는 정산 방식')
    if '다음 달 1일 이용 시 해당 월 전액 발생'not in text:raise ValueError('추가 월 요금 조건 확인 필요')
    penalty_values=_amounts(re.split(r'\s{3,}',_match(r'^\s*위약금\s+(.+)$',text).group(1).strip())[-1])
    cost_values=_amounts(_match(r'^\s*수거비·할인반환금\s+(.+)$',text).group(1))
    if len(penalty_values)!=2 or len(cost_values)!=2:raise ValueError('해지 비용 조건 확인 필요')
    if '종료 후 위약금·수거비·할인반환금 0원'not in text:
        raise ValueError('종료 후 비용 조건 확인 필요')
    rule={'penalty_before_or_on_mandatory_end':penalty_values[0],'penalty_after_mandatory_end':penalty_values[1],'collection_before_or_on_contract_end':cost_values[0],'discount_return_before_or_on_contract_end':cost_values[1],'post_contract_exit_fees':0}
    if '계약 종료 후에도 정산'not in text:raise ValueError('미납 정산 조건 확인 필요')
    return_policy=_match(r'^\s*기기 반환·소유권\s+(.+?)\s{3,}종료 후',text).group(1)
    return {'customer_id':customer_id,'document_id':document_id,'document_type':'subscription_contract','is_demo':True,'rule_id':'SYNTH-CONTRACT-V2','contract_start':start,'mandatory_end':product.group(3),'contract_end':product.group(4),'model':product.group(1),'monthly_fee':monthly,'annual_monthly_fees':{str(i+1):value for i,value in enumerate(fees)},'billing_day':day,'settlement_policy':{'proration':False,'charge_on_first_day':True,'full_month_due_if_used_on_first_day':True,'already_paid_current_month_not_refunded':True},'discount':{'discount_return':cost_values[1]},'exit_rules':rule,'return_policy':return_policy,'extraction_method':'PyPDFLoader + 팀 가상 계약서 표 항목 추출. JSON 저장 없음.'}
