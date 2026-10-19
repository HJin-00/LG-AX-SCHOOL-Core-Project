"""프로젝트 루트: python -m 정수기프로젝트.app.run api|mcp|check"""
import argparse
import os
import runpy
import sys
from pathlib import Path
from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('target', choices=['api', 'mcp', 'check', 'seed-account', 'setup-local', 'rag-index', 'rag-status'])
    args = parser.parse_args()
    settings = Path(os.environ.get('WATER_CONFIG_PATH', str(Path(__file__).parent / 'config/app.env')))
    if not settings.is_file():
        parser.error('config/app.env 설정 파일이 필요합니다.')
    load_dotenv(settings, override=True)
    backend=os.environ.setdefault('CONSENT_BACKEND','mysql')
    if backend=='mysql':
        os.environ.pop('CONSENT_DB',None)
    if args.target in {'rag-index', 'rag-status'}:
        import json
        from .rag.retriever import public_corpus
        from .rag.vector_index import build_index, status
        result = (build_index if args.target == 'rag-index' else status)(public_corpus())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result['status'] != 'ready':
            sys.exit(1)
    elif args.target == 'setup-local':
        if backend != 'sqlite':
            parser.error('setup-local은 로컬 SQLite에서만 실행합니다. CONSENT_BACKEND=sqlite를 확인하세요.')
        sys.path.insert(0,str(Path(__file__).parent/'backend'))
        from ai.login_store import LoginStore
        from .consent import ConsentStore
        store=ConsentStore()
        logins=LoginStore(store)
        with store.connect() as db:
            existing={row[0]:row[1] for row in db.execute('SELECT username,customer FROM demo_accounts').fetchall() if row[0] in {'test1','test2','test3','test4'}}
        if existing and existing != {f'test{i}':f'DEMO-U0{i}' for i in range(1,5)}:
            parser.error('부분 등록/다른 고객 연결이 있어 자동 변경하지 않습니다. 로컬 테스트 DB를 확인하세요.')
        if not existing:logins.seed_fixture_accounts()
        print('로컬 가상 계정 준비 완료: test1~test4 / 비밀번호 1234. 실제 고객 계정이 아닙니다.')
    elif args.target == 'seed-account':
        from getpass import getpass
        sys.path.insert(0,str(Path(__file__).parent/'backend'))
        from ai.login_store import LoginStore
        from .consent import ConsentStore
        username=input('테스트 계정 아이디: ').strip()
        customer=input('가상 고객 ID [DEMO-U01]: ').strip() or 'DEMO-U01'
        password=getpass('비밀번호(12자 이상): ')
        if password!=getpass('비밀번호 확인: '):parser.error('비밀번호 확인 불일치')
        try:LoginStore(ConsentStore()).seed(username,password,customer)
        except ValueError as exc:parser.error(str(exc))
        print('테스트 계정 등록 완료. 비밀번호 원문은 저장하지 않습니다.')
    elif args.target == 'check':
        from .consent import ConsentStore
        store = ConsentStore()
        with store.connect() as db:
            assert db.execute('SELECT 1').fetchone()[0] == 1
        print('MySQL 연결·동의 테이블 준비 완료')
    elif args.target == 'api':
        import uvicorn
        sys.path.insert(0, str(Path(__file__).parent / 'backend'))
        uvicorn.run('ai.main:app', host='127.0.0.1', port=8000, workers=1, access_log=False)
    else:
        runpy.run_module('정수기프로젝트.app.mcp.server', run_name='__main__')


if __name__ == '__main__':
    main()
