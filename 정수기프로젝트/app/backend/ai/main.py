"""실행: backend 폴더에서 python -m uvicorn ai.main:app --port 8000 --no-access-log"""
import asyncio
import inspect
import json
import logging
import os
import sys
from pathlib import Path
from time import monotonic
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Body, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import Field, ValidationError
from starlette.exceptions import HTTPException

from .agent_adapter import AgentUnavailable, ModelProviderFailure, ToolFailure, load_agent
from .brief_store import BriefStore
from .examples import ERROR_SPECS, REQUEST_EXAMPLES, SUCCESS_EXAMPLES, error_example
from .schemas import AgentReply, AgentResult, BriefId, ChatRequest, ChatResponse, ContextInput, HealthResponse, Model, SessionId
from .session_store import SessionBusy, SessionCapacity, SessionStore

# backend 폴더에서 ai.main으로 실행할 때도 공유 권한 모듈을 찾습니다.
_project_root = Path(__file__).resolve().parents[4]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
from 정수기프로젝트.app.consent import ConsentStore, ConsentDenied
from .schemas import DemoSessionRequest, ConsentEventRequest

logger = logging.getLogger("water_api")


class Settings(Model):
    require_login: bool = True
    agent_mode: Literal["stub", "live", "langchain"] = "stub"
    agent_timeout_seconds: float = Field(default=30, gt=0, le=300)
    session_ttl_seconds: int = Field(default=1800, ge=1)
    max_sessions: int = Field(default=1000, ge=1)
    consent_db: Path | None = None
    history_turns: int = Field(default=20, ge=1, le=100)
    brief_root: Path = Path(__file__).parent / "runtime" / "briefs"

    @classmethod
    def from_env(cls):
        names = {"agent_mode": "AGENT_MODE", "agent_timeout_seconds": "AGENT_TIMEOUT_SECONDS",
                 "session_ttl_seconds": "SESSION_TTL_SECONDS", "max_sessions": "MAX_SESSIONS",
                 "consent_db": "CONSENT_DB", "history_turns": "HISTORY_TURNS", "brief_root": "BRIEF_ROOT"}
        return cls(**{key: os.environ[name] for key, name in names.items() if os.environ.get(name)})


class ApiFailure(Exception):
    def __init__(self, http_status, code=None, answer=None, fields=None):
        default_code, default_answer, retryable = ERROR_SPECS[http_status]
        self.http_status = http_status
        self.payload = error_example(code or default_code, answer or default_answer, retryable, fields)


def safe_fields(errors):
    # 오류의 input/msg/임의 필드명에는 개인정보가 들어올 수 있어 사용하지 않는다.
    allowed = set(ChatRequest.model_fields) | set(ContextInput.model_fields) | {"body", "path", "header", "brief_id", "x-session-id"}
    return list(dict.fromkeys(".".join(str(p) if str(p) in allowed else "field" for p in e["loc"])[:120] or "body" for e in errors))


def create_app(settings: Settings | None = None, agent_runner=None, session_store=None):
    settings = settings or Settings.from_env()
    app = FastAPI(title="정수기 상담 API · C 담당", version="0.1.0",
                  description="C의 입력검증·세션·응답 계약 구현. 기본 stub은 API 연결 시험용이며 실제 AI 상담이 아닙니다. "
                              "카드·문맥 세부 규격은 C 구현안으로 A/B/E 통합 확인이 필요합니다.")
    app.state.settings = settings
    app.state.sessions = session_store or SessionStore(settings.session_ttl_seconds, settings.max_sessions, settings.history_turns)
    app.state.consents = ConsentStore(settings.consent_db, ttl=settings.session_ttl_seconds)
    app.state.briefs = BriefStore(settings.brief_root)
    app.state.agent_runner = agent_runner if agent_runner is not None else load_agent(settings.agent_mode)

    def error_response(request, failure):
        data = {**failure.payload, "trace_id": request.state.trace_id}
        return JSONResponse(status_code=failure.http_status, content=data)

    @app.middleware("http")
    async def request_trace(request, call_next):
        request.state.trace_id = uuid4().hex
        start = monotonic()
        try:
            response = await call_next(request)
        except Exception:
            # 예외 본문/stack/원문 입력은 기록하거나 클라이언트에 돌려주지 않는다.
            response = error_response(request, ApiFailure(500))
        response.headers["X-Trace-ID"] = request.state.trace_id
        response.headers["Cache-Control"] = "no-store"
        logger.info("trace_id=%s status=%s duration_ms=%d", request.state.trace_id,
                    response.status_code, int((monotonic() - start) * 1000))
        return response

    @app.exception_handler(ApiFailure)
    async def api_error(request, exc):
        return error_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error_response(request, ApiFailure(422, fields=safe_fields(exc.errors())))

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        if exc.status_code == 404:
            return error_response(request, ApiFailure(404, "NOT_FOUND", "요청한 경로를 찾을 수 없습니다."))
        data = error_example("HTTP_ERROR", "요청한 HTTP 작업을 처리할 수 없습니다.")
        return JSONResponse({**data, "trace_id": request.state.trace_id}, status_code=exc.status_code, headers=exc.headers)

    @app.get("/health", response_model=HealthResponse, tags=["상태"], summary="API 상태 및 Agent 연결 여부")
    async def health():
        return HealthResponse(agent_mode=settings.agent_mode,
                              agent_connected=settings.agent_mode in {"live", "langchain"} and app.state.agent_runner is not None)

    @app.exception_handler(ConsentDenied)
    async def consent_error(request, exc):
        return JSONResponse(status_code=403, content={"code":exc.code if exc.code.startswith("DEMO_") else "CONSENT_DENIED", "answer":str(exc) if exc.code.startswith("DEMO_") else "시연 세션 키·동의 범위를 확인해 주세요.", "trace_id":request.state.trace_id})

    from .login_store import LoginStore, LoginRequest, LoginDenied, COOKIE_NAME
    app.state.logins = LoginStore(app.state.consents)

    @app.exception_handler(LoginDenied)
    async def login_error(request, exc):
        return JSONResponse(status_code=exc.status,content={'code':exc.code,'answer':exc.answer,'trace_id':request.state.trace_id})

    def login_account(request, customer=None):
        account=app.state.logins.account(request.cookies.get(COOKIE_NAME))
        if customer is not None and account['demo_customer_id']!=customer:
            raise LoginDenied('LOGIN_OWNER_MISMATCH',403)
        return account

    def check_login_origin(request):
        origin=request.headers.get('origin')
        if origin and origin not in {'http://localhost:3001','http://127.0.0.1:3001','http://localhost:5173','http://127.0.0.1:5173',str(request.base_url).rstrip('/')}:
            raise LoginDenied('LOGIN_OWNER_MISMATCH',403)

    @app.post('/auth/login',tags=['테스트 로그인'])
    async def login(payload: LoginRequest, request: Request, response: Response):
        check_login_origin(request)
        token=app.state.logins.login(payload.username,payload.password.get_secret_value())
        app.state.logins.logout(request.cookies.get(COOKIE_NAME))
        # 직접 FastAPI 테스트/접속은 /api 접두사가 없으므로 공통 경로를 사용합니다.
        response.set_cookie(COOKIE_NAME,token,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=14400,path='/')
        account=app.state.logins.account(token);account.pop('demo_session_id',None)
        return {'account':account}

    @app.get('/auth/me',tags=['테스트 로그인'])
    async def me(request: Request):
        try:account=login_account(request)
        except LoginDenied:return {'account':None}
        account.pop('demo_session_id',None)
        return {'account':account}

    @app.post('/auth/logout',tags=['테스트 로그인'])
    async def logout(request: Request,response: Response):
        check_login_origin(request)
        account=app.state.logins.logout(request.cookies.get(COOKIE_NAME))
        if account and account['demo_session_id']:
            app.state.identities.clear(account['demo_session_id'])
            try:
                working=app.state.sessions.begin(account['demo_session_id'])
                working.history.clear();working.context_input.clear();working.brief_ids.clear();working.ui_state.clear();working.ui_scopes.clear()
                app.state.sessions.finish(account['demo_session_id'],working)
            except (SessionBusy,SessionCapacity):pass
        response.delete_cookie(COOKIE_NAME,path='/');response.delete_cookie(COOKIE_NAME,path='/api')
        return {'logged_out':True}

    @app.post('/guest-sessions',tags=['일반 상담'])
    async def guest_session():
        import secrets
        return {'session_id':secrets.token_urlsafe(24),'expires_in_seconds':1800,'is_demo':True}

    @app.get("/demo-profiles", tags=["가상 고객·동의"])
    async def demo_profiles(request: Request):
        if settings.require_login:
            account=login_account(request);return {"is_demo":True,"profiles":[{k:account[k] for k in ("demo_customer_id","display_name","product_model","usage_type")}]}
        # 공개 시연용 선택 목록만 반환. 기간·금액·납부·개인정보는 동의 후 조회.
        labels={'DEMO-U01':'이서연','DEMO-U02':'박지훈','DEMO-U03':'최유진','DEMO-U04':'정민수'}
        return {"is_demo":True,"profiles":[{
            "demo_customer_id":p['demo_customer_id'],"display_name":labels[p['demo_customer_id']],
            "product_model":p['product_model'],"usage_type":p['usage_type']
        } for p in app.state.consents.profiles()]}

    @app.get("/contracts/current", tags=["가상 고객·동의"])
    async def current_contract(request: Request, session_id: str = Header(alias="X-Session-ID"),
                               session_key: str = Header(default="",alias="X-Demo-Session-Key"),
                               access_token: str = Header(default="",alias="X-Tool-Access-Token")):
        owned = app.state.consents.owned(session_id,session_key)
        if settings.require_login:login_account(request,owned[1])
        require_identity(session_id, owned[1])
        app.state.consents.authorize(session_id,access_token,'contract_terms')
        from 정수기프로젝트.app.mcp.contracts.contract_documents import lookup_contract_document
        result=lookup_contract_document(session_id,access_token)
        if result.get('status')=='error':
            raise ApiFailure(502,"CONTRACT_READ_FAILED","계약 자료를 읽을 수 없습니다.")
        from 정수기프로젝트.app.mcp.tools import lookup_product_features
        profile=app.state.consents.profile(owned[1])
        products=lookup_product_features([profile['product_model']]).get('products',[])
        if products:
            result={**result,'product':{k:products[0].get(k) for k in ('model_id','display_name','image_url')}}
        return result

    @app.get("/connection/current", tags=["가상 고객·동의"])
    async def current_connection(request: Request, session_id: str = Header(alias="X-Session-ID"),
                                 session_key: str = Header(default="",alias="X-Demo-Session-Key"),
                                 access_token: str = Header(default="",alias="X-Tool-Access-Token")):
        owned=app.state.consents.owned(session_id,session_key)
        if settings.require_login:login_account(request,owned[1])
        require_identity(session_id,owned[1])
        profile=app.state.consents.authorize_active(session_id,access_token)
        scopes=json.loads(owned[4])
        from 정수기프로젝트.app.mcp.contracts.contract_documents import lookup_contract_document
        from 정수기프로젝트.app.mcp.tools import lookup_product_features
        result=lookup_contract_document(session_id,access_token) if 'contract_terms' in scopes else {'status':'ok','terms':{}}
        if result.get('status') not in {'ok','not_applicable'}:
            raise ApiFailure(502,"CONTRACT_READ_FAILED","연결된 계약을 다시 확인할 수 없습니다.")
        products=lookup_product_features([profile['product_model']]).get('products',[])
        product={k:products[0].get(k) for k in ('model_id','display_name','image_url')} if products else {}
        identity=app.state.identities.records[session_id]
        return {**result,'product':product,'scopes':scopes,
                'expires_in_seconds':max(0,int(owned[2]-app.state.consents.clock())),
                'identity_expires_in_seconds':max(0,int(identity[1]-app.state.identities.clock()))}

    @app.post("/demo-sessions", tags=["가상 고객·동의"])
    async def create_demo_session(payload: DemoSessionRequest, request: Request):
        if settings.require_login:login_account(request,payload.demo_customer_id)
        result=app.state.consents.create(payload.demo_customer_id)
        if settings.require_login:app.state.logins.bind(request.cookies.get(COOKIE_NAME),result['session_id'])
        return result

    from .demo_identity import DemoIdentityStore, DemoIdentityRequest, InstallationEstimateRequest
    app.state.identities = DemoIdentityStore()


    def require_identity(session_id, customer):
        if not app.state.identities.valid(session_id, customer):
            raise ConsentDenied("본인확인 시연과 계약 명의 일치 확인이 필요합니다. 실제 인증은 아닙니다.", code="DEMO_IDENTITY_REQUIRED")

    @app.post("/demo-sessions/{session_id}/identity", tags=["가상 고객·동의"])
    async def verify_demo_identity(request: Request, session_id: SessionId, payload: DemoIdentityRequest,
                                   session_key: str = Header(default="", alias="X-Demo-Session-Key")):
        owned = app.state.consents.owned(session_id, session_key)
        if settings.require_login:login_account(request,owned[1])
        try:
            working = app.state.sessions.begin(session_id)
        except SessionBusy:
            raise ApiFailure(409) from None
        except SessionCapacity:
            raise ApiFailure(503) from None
        committed = None
        try:
            # 재시도·실패 시 기존 동의와 개인 대화 상태를 폐기합니다.
            app.state.consents.event(session_id, session_key, 'revoke', [])
            working.history.clear(); working.context_input.clear(); working.brief_ids.clear();working.ui_state.clear();working.ui_scopes.clear()
            working.demo_fixture_id = None; working.product_model = None
            committed = working
            code = app.state.identities.verify(session_id, owned[1], payload.claimed_demo_customer_id, payload.outcome)
            if code:
                raise ConsentDenied("본인확인 시연 실패 또는 선택 계약 명의 불일치입니다. 실제 인증은 아닙니다.", code=code)
            return {"is_demo": True, "identity_state": "demo_verified", "expires_in_seconds": 600,
                    "message": "본인확인 시연 완료. 실제 PASS 또는 휴대폰 본인인증이 아닙니다."}
        finally:
            app.state.sessions.finish(session_id, committed)

    @app.post("/demo-sessions/{session_id}/consent", tags=["가상 고객·동의"])
    async def consent_event(request: Request, session_id: SessionId, payload: ConsentEventRequest,
                            session_key: Annotated[str, Header(alias="X-Demo-Session-Key")] = ""):
        owned=app.state.consents.owned(session_id, session_key)
        if settings.require_login:login_account(request,owned[1])
        try:
            working = app.state.sessions.begin(session_id)
        except SessionBusy:
            raise ApiFailure(409) from None
        except SessionCapacity:
            raise ApiFailure(503) from None
        committed = None
        try:
            if payload.action == 'grant':
                selected = app.state.consents.owned(session_id, session_key)[1]
                require_identity(session_id, selected)
            else:
                app.state.identities.clear(session_id)
            result = app.state.consents.event(session_id, session_key, payload.action, payload.scopes, payload.demo_customer_id)
            # 같은 본인확인 세션의 조회 범위 추가는 상담 이력을 보존한다.
            # 철회·범위 축소는 기존 개인 내용과 준비서 권한을 폐기한다.
            preserve_history=payload.action=='grant' and set(json.loads(owned[4])).issubset(set(payload.scopes))
            if not preserve_history:
                working.history.clear()
                working.ui_state.clear();working.ui_scopes.clear();working.ui_customer_id=None
                working.context_input.clear()
                working.demo_fixture_id = None
                working.product_model = None
                working.brief_ids.clear()
            committed = working
            return result
        finally:
            app.state.sessions.finish(session_id, committed)

    def conversation_subject(request,session_id,session_key,access_token):
        if not app.state.consents.exists(session_id):return None,[]
        owned=app.state.consents.owned(session_id,session_key)
        if settings.require_login:login_account(request,owned[1])
        require_identity(session_id,owned[1])
        app.state.consents.authorize_active(session_id,access_token)
        return owned[1],json.loads(owned[4])

    @app.get('/conversation/current',tags=['상담 상태'])
    async def conversation_current(request: Request,session_id: SessionId=Header(alias='X-Session-ID'),session_key: str=Header(default='',alias='X-Demo-Session-Key'),access_token: str=Header(default='',alias='X-Tool-Access-Token')):
        customer,scopes=conversation_subject(request,session_id,session_key,access_token)
        try:working=app.state.sessions.begin(session_id)
        except SessionBusy:raise ApiFailure(409) from None
        except SessionCapacity:raise ApiFailure(503) from None
        try:
            valid=working.ui_customer_id==customer and set(working.ui_scopes).issubset(scopes)
            from .conversation_state import valid_state
            state=working.ui_state if valid and working.ui_state else None
            if state and not valid_state(state):raise ApiFailure(422,'INVALID_CONVERSATION_STATE','저장된 상담을 복원할 수 없습니다. 새 대화를 시작해 주세요.')
            return {'state':state,'revision':working.ui_revision,'epoch':working.ui_epoch}
        finally:app.state.sessions.finish(session_id,None)

    @app.post('/conversation/state',tags=['상담 상태'])
    async def conversation_state(request: Request,payload: dict=Body(),session_id: SessionId=Header(alias='X-Session-ID'),session_key: str=Header(default='',alias='X-Demo-Session-Key'),access_token: str=Header(default='',alias='X-Tool-Access-Token')):
        customer,scopes=conversation_subject(request,session_id,session_key,access_token)
        state=payload.get('state')
        allowed={'messages','activeTopic','showRenewalReason','showContractQuestion','showRenewalPreferences','renewalContext'}
        from .conversation_state import valid_state
        if not valid_state(state) or set(state)-allowed or not isinstance(state.get('messages'),list) or len(state['messages'])>2*settings.history_turns+2 or len(json.dumps(state,ensure_ascii=False).encode())>2_000_000:
            raise ApiFailure(422,'INVALID_CONVERSATION_STATE','상담 화면 상태를 저장할 수 없습니다.')
        # UI 표시값은 모델의 authoritative history/context_input에 병합하지 않습니다.
        try:working=app.state.sessions.begin(session_id)
        except SessionBusy:raise ApiFailure(409) from None
        except SessionCapacity:raise ApiFailure(503) from None
        committed=None
        try:
            # Legacy first write is accepted only before any save/reset. All later writes require CAS.
            if payload.get('revision',0)!=working.ui_revision or payload.get('epoch',0)!=working.ui_epoch:
                raise ApiFailure(409,'CONVERSATION_CONFLICT','다른 창에서 상담이 변경되었습니다. 최신 상담을 다시 불러와 주세요.')
            working.ui_state=state;working.ui_scopes=scopes;working.ui_customer_id=customer;working.ui_revision+=1;committed=working
            return {'status':'ok','revision':working.ui_revision,'epoch':working.ui_epoch}
        finally:app.state.sessions.finish(session_id,committed)

    @app.post('/conversation/reset',tags=['상담 상태'])
    async def conversation_reset(request: Request,session_id: SessionId=Header(alias='X-Session-ID'),session_key: str=Header(default='',alias='X-Demo-Session-Key'),access_token: str=Header(default='',alias='X-Tool-Access-Token')):
        conversation_subject(request,session_id,session_key,access_token)
        try:working=app.state.sessions.begin(session_id)
        except SessionBusy:raise ApiFailure(409) from None
        except SessionCapacity:raise ApiFailure(503) from None
        committed=None
        try:
            working.history.clear();working.context_input.clear();working.ui_state.clear();working.ui_scopes.clear();working.ui_customer_id=None
            working.ui_epoch+=1;working.ui_revision+=1
            committed=working
            return {'status':'ok','contract_connection_preserved':True,'revision':working.ui_revision,'epoch':working.ui_epoch}
        finally:app.state.sessions.finish(session_id,committed)

    error_docs = {status: {"model": ChatResponse, "description": spec[1],
                         "content": {"application/json": {"example": error_example(*spec)}}}
                  for status, spec in ERROR_SPECS.items()}

    @app.post("/chat", response_model=ChatResponse, tags=["상담"], summary="입력 검증 → 세션 → Agent → 응답 검증",
              responses={200: {"content": {"application/json": {"examples": SUCCESS_EXAMPLES}}}, **error_docs})
    async def chat(payload: Annotated[ChatRequest, Body(openapi_examples=REQUEST_EXAMPLES)], request: Request,
                   session_key: Annotated[str, Header(alias="X-Demo-Session-Key")] = "",
                   access_token: Annotated[str, Header(alias="X-Tool-Access-Token")] = ""):
        managed = app.state.consents.exists(payload.session_id)
        if managed:
            owned=app.state.consents.owned(payload.session_id, session_key)
            if settings.require_login:login_account(request,owned[1])
            if payload.demo_fixture_id is not None:
                raise ConsentDenied("고객이 fixture를 선택할 수 없습니다.")
        store = app.state.sessions
        try:
            working = store.begin(payload.session_id)
        except SessionBusy:
            raise ApiFailure(409) from None
        except SessionCapacity:
            raise ApiFailure(503, "SESSION_CAPACITY", "대화 저장 용량이 가득 찼습니다. 잠시 후 다시 요청해 주세요.") from None
        committed = None
        try:
            try:
                working.patch(payload.model_dump(mode="json", exclude_unset=True))
            except ValidationError as exc:
                raise ApiFailure(422, "INVALID_CONTEXT", "기존 대화와 합친 날짜·조건이 올바르지 않습니다. 종료일을 확인해 주세요.", safe_fields(exc.errors())) from None
            runner = app.state.agent_runner
            if runner is None:
                raise ApiFailure(503)
            if not inspect.iscoroutinefunction(runner):
                raise ApiFailure(503, "AGENT_UNAVAILABLE", "Agent 연결 함수는 async run_agent 형식이어야 합니다.")
            try:
                async with asyncio.timeout(settings.agent_timeout_seconds):
                    context = working.agent_context(payload.session_id, request.state.trace_id)
                    # 계약 fixture는 Agent/사용자 임의 입력 대신 권한 도구에서 연결합니다.
                    context["demo_fixture_id"] = None
                    context["tool_authorization"] = {"session_id": payload.session_id, "access_token": ""}
                    if managed and access_token:
                        require_identity(payload.session_id, app.state.consents.owned(payload.session_id, session_key)[1])
                        granted_scopes = json.loads(owned[4])
                        context["granted_scopes"] = granted_scopes
                        profile_scope=next((scope for scope in ('contract_terms','care_info','contract_costs') if scope in granted_scopes),'contract_terms')
                        profile = app.state.consents.authorize(payload.session_id, access_token, profile_scope)
                        context["tool_authorization"]["access_token"] = access_token
                        context["demo_customer_id"] = profile['demo_customer_id']
                        # 연결된 본인 제품은 사용 방법·오류 상담에도 동일하게 사용합니다.
                        context["product_model"] = profile['product_model']
                    raw = await runner(payload.message, context)
                    if managed and settings.require_login:login_account(request,owned[1])
                # A는 AgentResult 또는 동등한 dict를 반환한다. 간단한 AgentReply/dict도 허용.
                if isinstance(raw, (AgentResult, AgentReply)):
                    raw = raw.model_dump(mode="json", exclude_unset=True)
                result = AgentResult.model_validate(raw if isinstance(raw, dict) and "reply" in raw else {"reply": raw})
            except TimeoutError:
                raise ApiFailure(504) from None
            except (ConsentDenied,LoginDenied):
                raise
            except ModelProviderFailure as exc:
                failure=ApiFailure(503,exc.code,exc.answer)
                failure.payload['error']['retryable']=exc.code=='MODEL_RATE_LIMIT'
                raise failure from None
            except AgentUnavailable:
                raise ApiFailure(503) from None
            except ToolFailure:
                raise ApiFailure(502, "TOOL_FAILED", "도구 실행에 실패했습니다. 실행 결과를 확인한 뒤 다시 요청해 주세요.") from None
            except ValidationError:
                raise ApiFailure(502, "INVALID_AGENT_RESPONSE", "Agent 응답 형식이 올바르지 않습니다. 서버 담당자에게 확인해 주세요.") from None
            except Exception:
                raise ApiFailure(502) from None
            if result.reply.status == "error":
                # Agent가 만든 임의 오류 문구에는 키/원문이 있을 수 있어 일반 문구로 교체.
                raise ApiFailure(502)
            if result.context_update is not None:
                try:
                    working.patch(result.context_update.model_dump(mode="json", exclude_unset=True))
                except ValidationError:
                    raise ApiFailure(502, "INVALID_AGENT_RESPONSE", "Agent가 반환한 문맥이 올바르지 않습니다.") from None
            if result.reply.brief_id:
                if app.state.briefs.resolve(result.reply.brief_id, payload.session_id) is None:
                    path = app.state.consents.brief_path(result.reply.brief_id, payload.session_id, token=access_token)
                    if path is None:
                        raise ApiFailure(502, "INVALID_BRIEF", "등록된 준비서 파일을 확인할 수 없습니다.")
                    try:
                        app.state.briefs.register(result.reply.brief_id, path, payload.session_id)
                    except (ValueError, OSError):
                        raise ApiFailure(502, "INVALID_BRIEF", "준비서 파일을 확인할 수 없습니다.") from None
                working.brief_ids.add(result.reply.brief_id)
            response = ChatResponse(**result.reply.model_dump(mode="json"), trace_id=request.state.trace_id)
            working.history.extend([{"role": "user", "content": payload.message},
                                    {"role": "assistant", "content": response.answer}])
            committed = working
            return response
        finally:
            # 실패하면 수정값과 대화 이력을 전부 롤백한다.
            store.finish(payload.session_id, committed)

    @app.get("/briefs/{brief_id}", tags=["상담 준비서"], summary="E가 생성·등록한 준비서 다운로드",
             response_class=FileResponse, responses={404: error_docs[404], 422: error_docs[422], 500: error_docs[500]},
             description="동일 대화의 X-Session-ID가 필요합니다. 가상 고객 세션은 X-Demo-Session-Key도 필요하며 키 누락·만료는 403입니다. 미등록/타 세션/삭제 파일은 404입니다.")
    async def download_brief(request: Request, brief_id: BriefId, session_id: Annotated[SessionId, Header(alias="X-Session-ID")],
                             session_key: Annotated[str | None, Header(alias="X-Demo-Session-Key")] = None):
        if app.state.consents.exists(session_id):
            owned = app.state.consents.owned(session_id, session_key)
            if settings.require_login:login_account(request,owned[1])
            require_identity(session_id, owned[1])
        if app.state.consents.brief_record(brief_id) is not None:
            if app.state.consents.brief_path(brief_id, session_id, session_key=session_key) is None:
                raise ApiFailure(404)
        path = app.state.briefs.resolve(brief_id, session_id)
        if path is None or not app.state.sessions.owns_brief(session_id, brief_id):
            raise ApiFailure(404)
        media = {".md": "text/markdown", ".txt": "text/plain", ".pdf": "application/pdf"}[path.suffix]
        return FileResponse(path, media_type=media, filename=f"consultation-{brief_id}{path.suffix}")

    return app


app = create_app()
