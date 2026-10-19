"""단일 프로세스용 메모리 세션: TTL, 용량 제한, 요청 단위 원자적 반영."""
from copy import deepcopy
from dataclasses import dataclass, field
from time import monotonic

from .schemas import ContextInput


class SessionBusy(Exception):
    pass


class SessionCapacity(Exception):
    pass


@dataclass
class Session:
    product_model: str | None = None
    context_input: dict = field(default_factory=dict)
    demo_fixture_id: str | None = None
    history: list[dict] = field(default_factory=list)
    ui_state: dict = field(default_factory=dict)
    ui_scopes: list[str] = field(default_factory=list)
    ui_customer_id: str | None = None
    ui_revision: int = 0
    ui_epoch: int = 0
    brief_ids: set[str] = field(default_factory=set)

    def patch(self, fields: dict):
        # 모든 병합 후 재검증하므로 이전 값과 새 값의 날짜 순서도 검사된다.
        if "demo_fixture_id" in fields:
            fixture = fields["demo_fixture_id"]
            if fixture != self.demo_fixture_id:
                self.context_input = {}
                self.product_model = None
                self.brief_ids.clear()
                self.history.clear()
                self.ui_state.clear();self.ui_scopes.clear();self.ui_customer_id=None
            self.demo_fixture_id = fixture
        if "product_model" in fields:
            model = fields["product_model"]
            if model != self.product_model:
                for key in ("symptom", "occurred_at", "lock_status", "continuous_after_wipe"):
                    self.context_input.pop(key, None)
            self.product_model = model
        if "context_input" in fields:
            patch = fields["context_input"]
            if patch is None:
                self.context_input = {}
            else:
                for key, value in patch.items():
                    if value is None:
                        self.context_input.pop(key, None)
                    else:
                        self.context_input[key] = value
        ContextInput.model_validate(self.context_input)

    def agent_context(self, session_id: str, trace_id: str):
        return deepcopy({"session_id": session_id, "trace_id": trace_id,
                         "product_model": self.product_model, "context_input": self.context_input,
                         "demo_fixture_id": self.demo_fixture_id, "history": self.history})


@dataclass
class Entry:
    session: Session
    touched: float
    busy: bool = False


class SessionStore:
    def __init__(self, ttl_seconds=1800, max_sessions=1000, history_turns=20, clock=monotonic):
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self.history_turns = history_turns
        self.clock = clock
        self._entries: dict[str, Entry] = {}

    def _prune(self):
        now = self.clock()
        for key, entry in list(self._entries.items()):
            if not entry.busy and now - entry.touched >= self.ttl_seconds:
                del self._entries[key]

    def begin(self, session_id: str) -> Session:
        # await 없는 구간: 한 ASGI 이벤트 루프에서 동일 세션의 병렬 요청을 거절.
        self._prune()
        entry = self._entries.get(session_id)
        if entry and entry.busy:
            raise SessionBusy
        if entry is None:
            if len(self._entries) >= self.max_sessions:
                raise SessionCapacity
            entry = self._entries[session_id] = Entry(Session(), self.clock())
        entry.busy = True
        return deepcopy(entry.session)

    def finish(self, session_id: str, session: Session | None):
        entry = self._entries[session_id]
        if session is not None:
            session.history = session.history[-2 * self.history_turns:]
            entry.session = deepcopy(session)
        entry.touched = self.clock()
        entry.busy = False

    def owns_brief(self, session_id: str, brief_id: str) -> bool:
        self._prune()
        entry = self._entries.get(session_id)
        return bool(entry and brief_id in entry.session.brief_ids)
