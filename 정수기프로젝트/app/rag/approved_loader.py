"""승인된 스냅샷만 읽는다. 수집 코드·AI 초안은 실행하거나 자동 승인하지 않는다."""
import fnmatch
import hashlib
import json
import re
from pathlib import Path
import yaml

ROOT = Path(__file__).parent / 'approved'

class ApprovedSourceError(ValueError):
    pass

def load_approved_documents(root=ROOT):
    root = Path(root).resolve()
    manifest = root / 'manifest.json'
    if not manifest.exists():
        return []
    rows = json.loads(manifest.read_text(encoding='utf-8'))['documents']
    seen = set()
    documents = []
    for row in rows:
        ident = row['document_id']
        target = (root / row['file']).resolve()
        if ident in seen or not target.is_relative_to(root) or not target.is_file():
            raise ApprovedSourceError('승인 문서 중복/경로/파일 오류')
        seen.add(ident)
        payload = target.read_bytes()
        if hashlib.sha256(payload).hexdigest() != row['sha256']:
            raise ApprovedSourceError('승인 검색 본문의 해시가 변경됐습니다.')
        text = payload.decode('utf-8-sig')
        try:
            _, front, body = text.split('---', 2)
            metadata = yaml.safe_load(front)
        except (ValueError, yaml.YAMLError) as exc:
            raise ApprovedSourceError('승인 메타데이터 형식 오류') from exc
        if not isinstance(metadata,dict):
            raise ApprovedSourceError('승인 메타데이터가 객체가 아닙니다.')
        if metadata.get('approval_status') != 'approved' or metadata.get('enabled', True) is not True or metadata.get('document_id') != ident or metadata.get('approval_id') != row['approval_id']:
            raise ApprovedSourceError('승인 상태/ID 불일치')
        documents.append({**row, 'body': body.strip()})
    return documents

def allowed_document(row, purpose, model_id):
    if purpose not in row.get('retrieval_purposes', ['consultation_reference']) or purpose in row.get('prohibited_uses', []):
        return False
    # 계산과 현행 법령 확정에는 새 공용 원문을 사용하지 않는다.
    if purpose in {'LG_contract_calculation', 'current_legal_determination'}:
        return False
    models = row.get('models', [])
    if model_id:
        if models:
            return any(fnmatch.fnmatchcase(model_id.upper(), pattern.upper()) for pattern in models)
        # 모델별 승인 근거가 없는 공용 오류/조작 문서를 다른 모델에 붙이지 않는다.
        if row.get('category') in {'관리_오류', '구매'} or row['document_id'].startswith(('LG-FAQ-', 'LG-HOT', 'LG-WD', 'LG-WU', 'C-WD', 'C-WU')):
            return False
    return True

def sections(body):
    # 표준답변은 질문과 답변의 레코드를 함께 보존한다.
    records = re.split(r'(?m)(?=^## CSV 레코드 )', body)
    if len(records) > 1:
        return [part for part in records if part.startswith('## CSV 레코드 ')]
    # HTML 표와 구조화된 셀 JSON/코드 블록은 쪼개지 않는다.
    pieces = re.split(r'(<table\b[\s\S]*?</table>|\[TABLE_ROWS\][\s\S]*?\[/TABLE_ROWS\]|```[\s\S]*?```)', body, flags=re.I)
    result, current = [], ''
    for piece in pieces:
        atoms = [piece] if piece.lstrip().startswith(('<table', '[TABLE_ROWS]', '```')) else re.split(r'\n\s*\n', piece)
        expanded=[]
        for atom in atoms:
            if len(atom)>10000 and not atom.lstrip().startswith(('<table','[TABLE_ROWS]','```')):
                expanded.extend(atom.splitlines())
            else:expanded.append(atom)
        for atom in expanded:
            if not atom.strip():
                continue
            if current and len(current) + len(atom) > 10000:
                result.append(current.strip())
                current = ''
            current += '\n\n' + atom
    if current:
        result.append(current.strip())
    return result

def approved_chunks(purpose='consultation_reference', model_id='', root=ROOT):
    chunks = []
    excluded = []
    for row in load_approved_documents(root):
        if not allowed_document(row, purpose, model_id):
            continue
        for number, body in enumerate(sections(row['body'])):
            if len(body) > 24000:
                excluded.append(row['document_id'])
                continue  # 큰 표를 잘라 잘못된 기준으로 사용하지 않는다.
            interpretation = '승인 범위: ' + row['approval_scope'] + '. 모델/조건/예외/안전 비고를 함께 확인하며 개인 계약 금액·현재 법령을 확정하지 않습니다. '
            if row['document_id'].startswith(('KCA', 'LAW')):
                interpretation += '일반 상담 참고입니다. LG 개별 해약금 계산 및 현행 법령 확정 판단에 사용하지 않습니다. '
            interpretation += row.get('model_limit', '')
            chunks.append({'document_id': row['document_id'], 'chunk_id': row['document_id'] + '-approved-' + str(number), 'title': row['title'], 'url': row['source_url'], 'section': body.split('\n')[0][:100], 'checked_at': row.get('checked_at').split('T')[0] if row.get('checked_at') else None, 'document_version': row.get('document_version'), 'effective_from': row.get('effective_from'), 'approval_id': row['approval_id'], 'approval_scope': row['approval_scope'], 'content': body, 'interpretation': interpretation, 'review_status': 'verified'})
    return chunks, sorted(set(excluded))
