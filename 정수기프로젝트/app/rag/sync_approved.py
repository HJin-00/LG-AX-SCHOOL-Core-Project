"""n8n 수집 결과의 승인 스냅샷을 검증·반영. 서버를 멈춘 뒤 --apply 사용."""
import argparse, hashlib, json, re, shutil, tempfile
from pathlib import Path
import yaml
from .approved_loader import ROOT, ApprovedSourceError, load_approved_documents


def checked_bytes(source,path,expected):
    target=(source/path).resolve()
    if not target.is_relative_to(source) or not target.is_file():raise ApprovedSourceError('수신 파일 경로/존재 오류')
    payload=target.read_bytes()
    if not expected or hashlib.sha256(payload).hexdigest()!=expected:raise ApprovedSourceError('수신 파일 해시 불일치')
    return payload


def prepare_snapshot(source,stage,previous=ROOT):
    source=Path(source).resolve();stage=Path(stage)
    current=json.loads((source/'수집관리/자동화상태/approval_state.json').read_text())['current']
    candidates=json.loads((source/'수집관리/자동화상태/index_candidates.json').read_text())['documents']
    known={r['document_id']:r for r in load_approved_documents(previous)}
    rows=[];(stage/'documents').mkdir(parents=True,exist_ok=True)
    for ident,a in current.items():
        if a.get('approval_status')!='approved' or a.get('enabled') is not True:continue
        if not re.fullmatch(r'[A-Za-z0-9_-]+',ident):raise ApprovedSourceError('문서 ID 형식 오류')
        c=candidates.get(ident,{})
        for key in ['document_id','version_id','approval_id','search_path','search_sha256','body_sha256']:
            if not a.get(key) or a.get(key)!=c.get(key):raise ApprovedSourceError('승인/인덱스 후보 불일치')
        checked_bytes(source,a['raw_path'],a['raw_sha256']);checked_bytes(source,a['body_path'],a['body_sha256'])
        payload=checked_bytes(source,a['search_path'],a['search_sha256'])
        try:m=yaml.safe_load(payload.decode('utf-8-sig').split('---',2)[1])
        except (ValueError,IndexError,yaml.YAMLError) as exc:raise ApprovedSourceError('검색 메타데이터 오류') from exc
        if not isinstance(m,dict) or m.get('approval_status')!='approved' or m.get('enabled') is not True or m.get('document_id')!=ident or m.get('approval_id')!=a['approval_id']:raise ApprovedSourceError('검색 문서 승인 불일치')
        old=known.get(ident,{});same=old.get('approval_id')==a['approval_id']
        row={'document_id':ident,'approval_id':a['approval_id'],'version_id':a['version_id'],'file':'documents/'+ident+'.md','sha256':a['search_sha256'],'source_url':m.get('source_url'),'title':m.get('title',ident),'checked_at':m.get('checked_at'),'approval_scope':m.get('approval_scope') or (old.get('approval_scope') if same else None) or '승인된 저장 본문에 한정','models':old.get('models',[]) if same else [],'category':m.get('category',''),'retrieval_purposes':old.get('retrieval_purposes',['consultation_reference']) if same else ['consultation_reference'],'prohibited_uses':old.get('prohibited_uses',[]) if same else ['LG_contract_calculation','current_legal_determination'],'raw_sha256':a['raw_sha256'],'body_sha256':a['body_sha256'],'model_limit':m.get('model_applicability_evidence','모델별 적용 범위 추가 검토 필요'),'document_version':m.get('document_version'),'effective_from':m.get('effective_from')}
        (stage/row['file']).write_bytes(payload);rows.append(row)
    if not rows:raise ApprovedSourceError('반영할 승인 검색 문서가 없습니다.')
    (stage/'manifest.json').write_text(json.dumps({'documents':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    load_approved_documents(stage);return len(rows)


def sync(source,apply=False,destination=ROOT):
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.rag-update-',dir=destination.parent) as folder:
        stage=Path(folder)/'next';backup=Path(folder)/'previous';count=prepare_snapshot(source,stage,destination)
        if apply:
            if destination.exists():destination.rename(backup)
            try:stage.rename(destination);load_approved_documents(destination)
            except Exception:
                if destination.exists():shutil.rmtree(destination)
                if backup.exists():backup.rename(destination)
                raise
        return {'documents':count,'applied':apply,'restart_required':apply,'vector_rebuild_required':apply}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,help='압축 해제한 03_지식문서 폴더')
    parser.add_argument('--apply',action='store_true',help='서버를 중지한 상태에서 적용')
    args=parser.parse_args();print(json.dumps(sync(args.source,args.apply),ensure_ascii=False))

if __name__=='__main__':main()
