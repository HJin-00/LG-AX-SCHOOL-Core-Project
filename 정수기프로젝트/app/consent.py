"""로컬 시연용 권한 저장소. FastAPI와 별도 MCP 프로세스가 설정된 DB를 공유합니다.

실제 고객 인증이 아닙니다. 불투명 키는 해시만 저장하며 선택한 가상 프로필에만 권한을 줍니다.
"""
import hashlib
import json
import csv
import os
import secrets
import sqlite3
import time
from pathlib import Path

DEFAULT_DB = Path(__file__).parent / 'backend/ai/runtime/consent.sqlite3'
CUSTOMERS = Path(__file__).parent / 'mcp/data/demo_customers.csv'
SCOPES = {'contract_terms', 'contract_costs', 'care_info'}


class ConsentDenied(Exception):
    def __init__(self, message, code='CONSENT_REQUIRED', required_scope=None):
        super().__init__(message)
        self.code = code
        self.required_scope = required_scope


def digest(value):
    if not isinstance(value, str) or not value:
        raise ConsentDenied('권한 키가 필요합니다.')
    return hashlib.sha256(value.encode()).hexdigest()


class ConsentStore:
    def __init__(self, path=None, ttl=1800, clock=time.time):
        self.backend = 'sqlite' if path is not None else os.environ.get('CONSENT_BACKEND', 'sqlite')
        if self.backend not in {'sqlite', 'mysql'}:
            raise ValueError('CONSENT_BACKEND는 sqlite 또는 mysql이어야 합니다.')
        self.path = Path(path or os.environ.get('CONSENT_DB', str(DEFAULT_DB)))
        self.ttl = ttl
        self.clock = clock
        if self.backend == 'mysql':
            with self.connect() as db:
                db.execute('CREATE TABLE IF NOT EXISTS sessions (id VARCHAR(64) PRIMARY KEY, key_hash CHAR(64) NOT NULL, customer VARCHAR(32) NOT NULL, expires DOUBLE NOT NULL, grant_hash CHAR(64), scopes TEXT NOT NULL) ENGINE=InnoDB')
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.connect() as db:
                db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, key_hash TEXT, customer TEXT, expires REAL, grant_hash TEXT, scopes TEXT)')
            os.chmod(self.path, 0o600)

        # MCP와 FastAPI가 다른 프로세스여도 준비서 소유 정보를 공유합니다.
        with self.connect() as db:
            id_type = 'VARCHAR(80)' if self.backend == 'mysql' else 'TEXT'
            db.execute(f'CREATE TABLE IF NOT EXISTS consultation_briefs (id {id_type} PRIMARY KEY, session_id TEXT NOT NULL, grant_hash TEXT NOT NULL, path TEXT NOT NULL, content_hash TEXT NOT NULL)')

    def connect(self):
        if self.backend == 'mysql':
            from .database.mysql import transaction
            return transaction()
        return sqlite3.connect(self.path, timeout=10)

    def profiles(self):
        with CUSTOMERS.open(encoding='utf-8-sig',newline='') as file:
            rows=list(csv.DictReader(file))
        for row in rows:
            row['contract_fixture_id']=row.get('contract_fixture_id') or None
            row['monthly_fee']=int(row['monthly_fee']) if row.get('monthly_fee') else None
        return rows

    def profile(self, customer):
        for row in self.profiles():
            if row['demo_customer_id'] == customer:
                return row
        raise ConsentDenied('등록된 가상 프로필이 아닙니다.')

    def create(self, customer):
        self.profile(customer)
        session_id = secrets.token_urlsafe(24)
        key = secrets.token_urlsafe(32)
        with self.connect() as db:
            # 만료 행도 보존합니다. 삭제하면 일반 세션으로 오인해 권한 검사를 건너뛸 수 있습니다.
            db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?)', (session_id, digest(key), customer, self.clock()+self.ttl, None, '[]'))
        return {'session_id': session_id, 'session_key': key, 'demo_customer_id': customer, 'is_demo': True, 'expires_in_seconds': self.ttl}

    def owned(self, session_id, key):
        with self.connect() as db:
            row = db.execute('SELECT key_hash,customer,expires,grant_hash,scopes FROM sessions WHERE id=?', (session_id,)).fetchone()
        if not row or row[2] <= self.clock() or not secrets.compare_digest(row[0], digest(key)):
            raise ConsentDenied('시연 세션 키가 없거나 만료되었습니다.')
        return row

    def exists(self, session_id):
        with self.connect() as db:
            return db.execute('SELECT 1 FROM sessions WHERE id=?', (session_id,)).fetchone() is not None

    def event(self, session_id, key, action, scopes=None, customer=None):
        # 트랜잭션에서 현재 키·만료를 다시 확인해 변경과 검증을 함께 처리합니다.
        with self.connect() as db:
            if self.backend == 'sqlite':
                db.execute('BEGIN IMMEDIATE')
            lock = ' FOR UPDATE' if self.backend == 'mysql' else ''
            row = db.execute('SELECT key_hash,customer,expires FROM sessions WHERE id=?' + lock, (session_id,)).fetchone()
            if not row or row[2] <= self.clock() or not secrets.compare_digest(row[0], digest(key)):
                raise ConsentDenied('세션을 확인할 수 없습니다.')
            selected = customer or row[1]
            self.profile(selected)
            values = scopes or []
            if action not in {'grant', 'decline', 'revoke', 'select_profile'} or not set(values) <= SCOPES:
                raise ConsentDenied('허용된 동의 이벤트가 아닙니다.')
            if action == 'grant' and (not values or selected != row[1] or ('contract_costs' in values and 'contract_terms' not in values)):
                raise ConsentDenied('프로필 선택 후 다시 동의해야 합니다.')
            token = secrets.token_urlsafe(32) if action == 'grant' else None
            db.execute('UPDATE sessions SET customer=?,grant_hash=?,scopes=? WHERE id=?', (selected,digest(token) if token else None,json.dumps(values if token else []),session_id))
        return {'session_id':session_id,'demo_customer_id':selected,'consent_state':'granted' if token else action,'scopes':values if token else [],'tool_access_token':token,'is_demo':True}

    def authorize(self, session_id, token, scope):
        with self.connect() as db:
            row = db.execute('SELECT customer,expires,grant_hash,scopes FROM sessions WHERE id=?', (session_id,)).fetchone()
        if not row or not isinstance(token, str) or not token:
            raise ConsentDenied('동의 권한을 확인할 수 없습니다.')
        if not row[2]:
            raise ConsentDenied('현재 활성 동의가 없습니다.')
        if not secrets.compare_digest(row[2], digest(token)):
            raise ConsentDenied('권한 토큰을 확인할 수 없습니다.', 'INVALID_TOOL_TOKEN')
        # 올바른 토큰인 경우에만 만료·범위 상태를 구체적으로 반환합니다.
        if row[1] <= self.clock():
            raise ConsentDenied('시연 세션이 만료되었습니다.', 'SESSION_EXPIRED')
        if scope not in json.loads(row[3]):
            raise ConsentDenied('해당 조회 범위에 동의가 필요합니다.', 'CONSENT_SCOPE_REQUIRED', scope)
        return self.profile(row[0])

    def authorize_active(self,session_id,token):
        """등록/다운로드 소유 검증. 내용별 범위 검증은 각 생성 도구가 수행한다."""
        with self.connect() as db:
            row=db.execute('SELECT scopes FROM sessions WHERE id=?',(session_id,)).fetchone()
        values=json.loads(row[0]) if row else []
        scope=next((s for s in values if s in SCOPES),None)
        if scope is None:raise ConsentDenied('현재 활성 동의가 없습니다.')
        return self.authorize(session_id,token,scope)

    def register_brief(self, brief_id, session_id, token, path):
        self.authorize_active(session_id, token)
        target = Path(path).resolve(strict=True)
        content_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        with self.connect() as db:
            db.execute('INSERT INTO consultation_briefs VALUES (?,?,?,?,?)',
                       (brief_id, session_id, digest(token), str(target), content_hash))

    def brief_record(self, brief_id):
        with self.connect() as db:
            return db.execute('SELECT session_id,grant_hash,path,content_hash FROM consultation_briefs WHERE id=?', (brief_id,)).fetchone()

    def brief_path(self, brief_id, session_id, *, token=None, session_key=None):
        record = self.brief_record(brief_id)
        if record is None or record[0] != session_id:
            return None
        if session_key is not None:
            row = self.owned(session_id, session_key)
            grant_hash = row[3]
        else:
            self.authorize_active(session_id, token)
            grant_hash = digest(token)
        if not grant_hash or not secrets.compare_digest(record[1], grant_hash):
            return None
        target = Path(record[2])
        try:
            if hashlib.sha256(target.read_bytes()).hexdigest() != record[3]:
                return None
        except OSError:
            return None
        return target
