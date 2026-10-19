"""로컬 테스트 계정 로그인. 실제 LG 로그인·본인확인과 별도입니다."""
import hashlib,hmac,secrets,time
from .schemas import Model
from pydantic import SecretStr,Field

COOKIE_NAME='water_login'
LABELS={'DEMO-U01':'이서연','DEMO-U02':'박지훈','DEMO-U03':'최유진','DEMO-U04':'정민수'}


class LoginRequest(Model):
    username: str = Field(min_length=1,max_length=64)
    password: SecretStr = Field(min_length=1,max_length=128)


class LoginDenied(Exception):
    def __init__(self,code='LOGIN_REQUIRED',status=401):
        self.code,self.status=code,status
        self.answer={'LOGIN_REQUIRED':'개인 계약 상담은 로그인이 필요한 서비스입니다.','LOGIN_FAILED':'아이디 또는 비밀번호를 확인해 주세요.','LOGIN_RATE_LIMIT':'잠시 후 다시 로그인해 주세요.','LOGIN_OWNER_MISMATCH':'현재 계정의 계약만 조회할 수 있습니다.'}.get(code,'로그인을 확인해 주세요.')


class LoginStore:
    def __init__(self,consents,clock=time.time,ttl=14400):
        self.consents,self.clock,self.ttl=consents,clock,ttl
        self.attempts={}
        with consents.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS demo_accounts (username VARCHAR(64) PRIMARY KEY, customer VARCHAR(32) NOT NULL, salt VARCHAR(32) NOT NULL, password_hash VARCHAR(64) NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS demo_logins (token_hash VARCHAR(64) PRIMARY KEY, username VARCHAR(64) NOT NULL, expires DOUBLE NOT NULL, demo_session_id VARCHAR(64))')

    @staticmethod
    def password_hash(password,salt):
        return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),310000).hex()

    def seed(self,username,password,customer='DEMO-U01'):
        if len(password)<12 or len(username)>64 or not username:raise ValueError('테스트 비밀번호는 12자 이상, 아이디는 1~64자')
        self.consents.profile(customer)
        salt=secrets.token_hex(16)
        with self.consents.connect() as db:
            if db.execute('SELECT 1 FROM demo_accounts WHERE username=?',(username,)).fetchone():
                raise ValueError('이미 등록된 계정입니다. 덮어쓰지 않습니다.')
            db.execute('INSERT INTO demo_accounts VALUES (?,?,?,?)',(username,customer,salt,self.password_hash(password,salt)))

    def seed_fixture_accounts(self):
        """사용자 지정 가상 고객 계정만 갱신. 일반 계정 비밀번호 정책은 유지합니다."""
        with self.consents.connect() as db:
            for number in range(1,5):
                username=f'test{number}';customer=f'DEMO-U0{number}'
                self.consents.profile(customer)
                existing=db.execute('SELECT customer FROM demo_accounts WHERE username=?',(username,)).fetchone()
                if existing and existing[0]!=customer:
                    raise ValueError('동일 아이디가 다른 고객에 연결되어 있습니다.')
                sessions=db.execute('SELECT demo_session_id FROM demo_logins WHERE username=?',(username,)).fetchall()
                for session in sessions:
                    if session[0]:db.execute('UPDATE sessions SET grant_hash=NULL,scopes=? WHERE id=?',('[]',session[0]))
                db.execute('DELETE FROM demo_logins WHERE username=?',(username,))
                salt=secrets.token_hex(16);hashed=self.password_hash('1234',salt)
                if existing:
                    db.execute('UPDATE demo_accounts SET salt=?,password_hash=? WHERE username=?',(salt,hashed,username))
                else:
                    db.execute('INSERT INTO demo_accounts VALUES (?,?,?,?)',(username,customer,salt,hashed))

    def login(self,username,password):
        now=self.clock();recent=[t for t in self.attempts.get(username,[]) if t>now-60]
        if len(recent)>=5:raise LoginDenied('LOGIN_RATE_LIMIT',429)
        # 실패 기록은 로컬 단일 프로세스 시연 한도입니다.
        self.attempts={k:[t for t in v if t>now-60] for k,v in self.attempts.items() if any(t>now-60 for t in v)}
        if len(self.attempts)>1000:raise LoginDenied('LOGIN_RATE_LIMIT',429)
        with self.consents.connect() as db:
            row=db.execute('SELECT customer,salt,password_hash FROM demo_accounts WHERE username=?',(username,)).fetchone()
            calculated=self.password_hash(password,row[1] if row else '0'*32)
            if not row or not hmac.compare_digest(calculated,row[2]):
                self.attempts[username]=recent+[now];raise LoginDenied('LOGIN_FAILED')
            self.attempts.pop(username,None)
            db.execute('DELETE FROM demo_logins WHERE expires<=?',(now,))
            token=secrets.token_urlsafe(32)
            db.execute('INSERT INTO demo_logins VALUES (?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),username,now+self.ttl,None))
        return token

    def account(self,token):
        if not isinstance(token,str) or not token:raise LoginDenied()
        with self.consents.connect() as db:
            row=db.execute('SELECT a.username,a.customer,l.expires,l.demo_session_id FROM demo_logins l JOIN demo_accounts a ON a.username=l.username WHERE l.token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not row or row[2]<=self.clock():raise LoginDenied()
        profile=self.consents.profile(row[1])
        return {'username':row[0],'demo_customer_id':row[1],'display_name':LABELS[row[1]],'product_model':profile['product_model'],'usage_type':profile['usage_type'],'demo_session_id':row[3],'is_demo':True}

    def bind(self,token,session_id):
        account=self.account(token)
        old=account['demo_session_id']
        if old and old!=session_id:self.revoke_session(old)
        with self.consents.connect() as db:
            db.execute('UPDATE demo_logins SET demo_session_id=? WHERE token_hash=?',(session_id,hashlib.sha256(token.encode()).hexdigest()))

    def revoke_session(self,session_id):
        with self.consents.connect() as db:
            db.execute('UPDATE sessions SET grant_hash=NULL,scopes=? WHERE id=?',('[]',session_id))

    def logout(self,token):
        try:account=self.account(token)
        except LoginDenied:account=None
        if account and account['demo_session_id']:self.revoke_session(account['demo_session_id'])
        if token:
            with self.consents.connect() as db:db.execute('DELETE FROM demo_logins WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
        return account
