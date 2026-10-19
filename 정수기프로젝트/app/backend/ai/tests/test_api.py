import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai.agent_adapter import AgentUnavailable, ToolFailure
from ai.examples import SUCCESS_EXAMPLES
from ai.main import Settings, create_app
from ai.schemas import ChatResponse
from ai.session_store import SessionStore


def reply(**values):
    return {"status": "answered", "topic": "unknown", "answer": "테스트 응답", **values}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(require_login=False,brief_root=tmp_path))) as instance:
        yield instance


def send(client, session="session-test-001", **values):
    return client.post("/chat", json={"session_id": session, "message": "질문", **values})


def test_health_docs_and_schema(client):
    assert client.get("/health").json()["agent_connected"] is False
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    assert set(spec["paths"]) == {"/health", "/chat", "/briefs/{brief_id}", "/demo-sessions", "/demo-sessions/{session_id}/consent", "/demo-profiles", "/contracts/current", "/connection/current", "/demo-sessions/{session_id}/identity", "/auth/login", "/auth/logout", "/auth/me", "/guest-sessions", "/conversation/current", "/conversation/state", "/conversation/reset"}
    assert "422" in spec["paths"]["/chat"]["post"]["responses"]
    assert "examples" in spec["paths"]["/chat"]["post"]["requestBody"]["content"]["application/json"]
    for example in SUCCESS_EXAMPLES.values():
        ChatResponse.model_validate(example["value"])


def test_stub_two_turns_and_isolation(client):
    first = send(client)
    assert first.json()["status"] == "needs_info"
    assert first.json()["trace_id"] == first.headers["X-Trace-ID"]
    second = send(client, product_model="DEMO-P1")
    assert second.json()["status"] == "answered"
    assert "API 연결 테스트" in second.json()["answer"]
    assert send(client).json()["status"] == "answered"
    assert send(client, session="session-test-002").json()["status"] == "needs_info"
    assert first.json()["trace_id"] != second.json()["trace_id"]


@pytest.mark.parametrize("values", [
    {"message": ""}, {"message": " \n\t"}, {"message": 123}, {"message": "x" * 4001},
    {"session_id": ""}, {"session_id": "short"}, {"session_id": "../secret-path"},
    {"product_model": "  "}, {"product_model": 3}, {"extra": "not allowed"},
    {"demo_fixture_id": "SYNTH-01"}, {"context_input": []},
    {"context_input": {"exit_date": "2026-02-30"}},
    {"context_input": {"exit_date": "2026-9-2"}},
    {"context_input": {"exit_date": 1234567890}},
    {"context_input": {"exit_date": "2026-09-22T00:00:00"}},
    {"context_input": {"mandatory_end": "2028-01-01", "contract_end": "2026-01-01"}},
    {"context_input": {"arrears": -1}}, {"context_input": {"arrears": True}},
    {"context_input": {"continuous_after_wipe": "false"}},
    {"context_input": {"expected_total": 70000}},
])
def test_invalid_inputs(client, values):
    response = send(client, **values)
    assert response.status_code == 422
    assert response.json()["status"] == "error"
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_missing_and_broken_json(client):
    for body in ({}, {"message": "질문"}, {"session_id": "session-test-001"}):
        assert client.post("/chat", json=body).status_code == 422
    response = client.post("/chat", content='{ "broken"', headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "broken" not in response.text


def test_correction_null_and_context_isolation(tmp_path):
    seen = []

    async def record(message, context):
        seen.append(context)
        return reply()

    with TestClient(create_app(Settings(require_login=False,brief_root=tmp_path), record)) as c:
        send(c, product_model="DEMO-P1", context_input={"symptom": "온수", "exit_date": "2026-09-22", "arrears": 0})
        send(c, context_input={"exit_date": "2026-08-30"})
        assert seen[-1]["context_input"] == {"symptom": "온수", "exit_date": "2026-08-30", "arrears": 0}
        send(c, context_input={"exit_date": None})
        assert "exit_date" not in seen[-1]["context_input"]
        send(c, product_model="DEMO-P2")
        assert "symptom" not in seen[-1]["context_input"]
        assert seen[-1]["product_model"] == "DEMO-P2"
        send(c, session="session-test-002")
        assert seen[-1]["context_input"] == {}
        assert seen[-1]["history"] == []
        send(c, context_input=None, product_model=None)
        assert seen[-1]["context_input"] == {}
        assert seen[-1]["product_model"] is None


def test_merged_date_order_and_rollback(tmp_path):
    seen = []

    async def record(message, context):
        seen.append(context)
        return reply()

    with TestClient(create_app(Settings(require_login=False,brief_root=tmp_path), record)) as c:
        send(c, context_input={"mandatory_end": "2026-08-31", "contract_end": "2028-08-31"})
        result = send(c, context_input={"mandatory_end": "2029-08-31"})
        assert result.status_code == 422
        assert result.json()["error"]["code"] == "INVALID_CONTEXT"
        assert len(seen) == 1
        send(c)
        assert seen[-1]["context_input"]["mandatory_end"] == "2026-08-31"
        assert len(seen[-1]["history"]) == 2


def test_agent_natural_language_context_update(tmp_path):
    seen = []

    async def extract(message, context):
        seen.append(context)
        return {"reply": reply(), "context_update": {"context_input": {"exit_date": "2026-08-30"}}}

    with TestClient(create_app(Settings(require_login=False,brief_root=tmp_path), extract)) as c:
        assert send(c, message="검토일을 8월 30일로 바꿀게요").status_code == 200
        send(c)
        assert seen[-1]["context_input"]["exit_date"] == "2026-08-30"


@pytest.mark.parametrize("exc,status,code", [
    (RuntimeError("SECRET 010-1234-5678"), 502, "AGENT_FAILED"),
    (ToolFailure("SECRET"), 502, "TOOL_FAILED"),
    (AgentUnavailable("SECRET"), 503, "AGENT_UNAVAILABLE"),
])
def test_upstream_errors_and_no_leak(tmp_path, caplog, exc, status, code):
    async def failure(message, context):
        context["product_model"] = "MUTATED"
        raise exc

    app = create_app(Settings(require_login=False,brief_root=tmp_path), failure)
    with TestClient(app) as c:
        caplog.set_level("INFO", logger="water_api")
        result = send(c, message="홍길동 010-1234-5678 SECRET", product_model="DEMO-P1")
        assert result.status_code == status
        assert result.json()["error"]["code"] == code
        assert "SECRET" not in result.text + caplog.text
        assert "010-1234-5678" not in result.text + caplog.text
        assert "홍길동" not in caplog.text
        async def success(message, context):
            assert context["product_model"] is None
            assert context["history"] == []
            return reply()
        app.state.agent_runner = success
        assert send(c).status_code == 200


def test_validation_does_not_echo_unknown_keys_or_input(client, caplog):
    caplog.set_level("INFO", logger="water_api")
    response = send(client, **{"홍길동-010-1234-5678": "SECRET"})
    assert response.status_code == 422
    for private in ["홍길동", "010-1234-5678", "SECRET"]:
        assert private not in response.text + caplog.text


def test_timeout_cancellation_and_release(tmp_path):
    cancelled = []

    async def slow(message, context):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)

    app = create_app(Settings(require_login=False,brief_root=tmp_path, agent_timeout_seconds=0.01), slow)
    with TestClient(app) as c:
        result = send(c)
        assert result.status_code == 504
        assert result.json()["error"]["code"] == "AGENT_TIMEOUT"
        assert cancelled == [True]
        async def success(message, context):
            return reply()
        app.state.agent_runner = success
        assert send(c).status_code == 200


@pytest.mark.parametrize("output", [
    {"bad": "SECRET"}, reply(answer=""), reply(status="brief_created"),
    reply(brief_id="brief-demo-0001"), reply(status="needs_info"),
    {"reply": reply(), "context_update": {"context_input": {"exit_date": "2026-02-30"}}},
    reply(sources=[{"document_id": "bad", "title": "bad", "url": "javascript:alert(1)"}]),
    reply(cards=[{"type": "contract", "data": {}}]),
])
def test_invalid_agent_output(tmp_path, output):
    async def invalid(message, context):
        return output
    with TestClient(create_app(Settings(require_login=False,brief_root=tmp_path), invalid)) as c:
        response = send(c)
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "INVALID_AGENT_RESPONSE"
        assert "SECRET" not in response.text


def test_agent_error_status_is_not_200(tmp_path):
    async def error(message, context):
        return reply(status="error", answer="SECRET", error={"code": "TOOL_ERROR"})
    with TestClient(create_app(Settings(require_login=False,brief_root=tmp_path), error)) as c:
        result = send(c)
        assert result.status_code == 502
        assert "SECRET" not in result.text


def test_live_without_agent_does_not_fall_back_to_stub(tmp_path):
    with TestClient(create_app(Settings(require_login=False,agent_mode="live", brief_root=tmp_path))) as c:
        assert c.get("/health").json()["agent_connected"] is False
        assert send(c).status_code == 503


def test_concurrent_same_session_rejected_other_session_runs(tmp_path):
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        async def runner(message, context):
            if context["session_id"] == "session-test-001":
                started.set()
                await release.wait()
            return reply()
        app = create_app(Settings(require_login=False,brief_root=tmp_path), runner)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            data = {"session_id": "session-test-001", "message": "질문"}
            first = asyncio.create_task(c.post("/chat", json=data))
            await asyncio.wait_for(started.wait(), timeout=2)
            second = await c.post("/chat", json=data)
            other = await c.post("/chat", json={**data, "session_id": "session-test-002"})
            release.set()
            assert (await first).status_code == 200
            assert second.status_code == 409
            assert other.status_code == 200
    asyncio.run(scenario())


def test_ttl_capacity_and_history(tmp_path):
    now = [0.0]
    store = SessionStore(ttl_seconds=10, max_sessions=1, history_turns=1, clock=lambda: now[0])
    contexts = []
    async def runner(message, context):
        contexts.append(context)
        return reply()
    with TestClient(create_app(Settings(require_login=False,brief_root=tmp_path), runner, store)) as c:
        send(c, product_model="DEMO-P1")
        send(c)
        send(c)
        assert len(contexts[-1]["history"]) == 2
        assert send(c, session="session-test-002").status_code == 503
        now[0] = 11
        assert send(c).status_code == 200
        assert contexts[-1]["product_model"] is None
        assert contexts[-1]["history"] == []


def test_brief_registration_download_isolation_missing_file(tmp_path):
    app = create_app(Settings(require_login=False,brief_root=tmp_path))
    brief = tmp_path / "test.md"
    brief.write_text("# 가상 상담 준비서", encoding="utf-8")
    async def created(message, context):
        app.state.briefs.register("brief-test-0001", brief, context["session_id"])
        return reply(status="brief_created", brief_id="brief-test-0001")
    app.state.agent_runner = created
    with TestClient(app) as c:
        assert send(c).status_code == 200
        path = "/briefs/brief-test-0001"
        good = c.get(path, headers={"X-Session-ID": "session-test-001"})
        assert good.status_code == 200
        assert "가상 상담 준비서" in good.text
        assert "attachment" in good.headers["content-disposition"]
        assert c.get(path, headers={"X-Session-ID": "session-test-002"}).status_code == 404
        assert c.get(path).status_code == 422
        brief.unlink()
        assert c.get(path, headers={"X-Session-ID": "session-test-001"}).status_code == 404


def test_brief_unregistered_never_success(tmp_path):
    async def invalid(message, context):
        return reply(status="brief_created", brief_id="brief-test-0001")
    with TestClient(create_app(Settings(require_login=False,brief_root=tmp_path), invalid)) as c:
        assert send(c).json()["error"]["code"] == "INVALID_BRIEF"
        assert c.get("/briefs/brief-test-0001", headers={"X-Session-ID": "session-test-001"}).status_code == 404


def test_register_rejects_path_escape(tmp_path):
    app = create_app(Settings(require_login=False,brief_root=tmp_path / "allowed"))
    external = tmp_path / "secret.md"
    external.write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError):
        app.state.briefs.register("brief-test-0001", external, "session-test-001")
    with pytest.raises(ValueError):
        app.state.briefs.register("../secret", external, "session-test-001")


def test_contract_unknown_total_is_never_zero():
    raw = SUCCESS_EXAMPLES["contract_null"]["value"]
    parsed = ChatResponse.model_validate(raw)
    assert parsed.cards[0].data.estimated_total is None
    bad = parsed.model_dump(mode="json")
    bad["cards"][0]["data"]["estimated_total"] = 0
    with pytest.raises(ValidationError):
        ChatResponse.model_validate(bad)


def test_unknown_route_and_method_error_envelope(client):
    for response in (client.get("/missing"), client.get("/chat")):
        assert response.status_code in {404, 405}
        assert response.json()["status"] == "error"
        assert response.json()["trace_id"] == response.headers["X-Trace-ID"]


def test_fixture_change_clears_old_model_context_history(tmp_path):
    seen = []
    async def record(message, context):
        seen.append(context)
        return reply()
    with TestClient(create_app(Settings(require_login=False,brief_root=tmp_path), record)) as c:
        send(c, demo_fixture_id="DEMO-A", product_model="DEMO-P1", context_input={"arrears": 30000})
        send(c, demo_fixture_id="DEMO-B")
        assert seen[-1]["product_model"] is None
        assert seen[-1]["context_input"] == {}
        assert seen[-1]["history"] == []
        send(c, demo_fixture_id="DEMO-P2", product_model="DEMO-P2")
        assert seen[-1]["product_model"] == "DEMO-P2"


def test_brief_expires_with_session(tmp_path):
    now = [0]
    store = SessionStore(ttl_seconds=10, clock=lambda: now[0])
    app = create_app(Settings(require_login=False,brief_root=tmp_path), session_store=store)
    path = tmp_path / "test.md"
    path.write_text("test", encoding="utf-8")
    async def created(message, context):
        app.state.briefs.register("brief-test-0001", path, context["session_id"])
        return reply(status="brief_created", brief_id="brief-test-0001")
    app.state.agent_runner = created
    with TestClient(app) as c:
        assert send(c).status_code == 200
        now[0] = 11
        result = c.get("/briefs/brief-test-0001", headers={"X-Session-ID": "session-test-001"})
        assert result.status_code == 404


def test_new_frontend_profile_and_contract_endpoints(tmp_path,monkeypatch):
    from 정수기프로젝트.app.consent import ConsentStore
    from ai.main import create_app,Settings
    from fastapi.testclient import TestClient
    monkeypatch.setenv('CONSENT_BACKEND','sqlite');monkeypatch.setenv('CONSENT_DB',str(tmp_path/'frontend.db'))
    client=TestClient(create_app(Settings(require_login=False,consent_db=tmp_path/'frontend.db',brief_root=tmp_path/'briefs')))
    profiles=client.get('/demo-profiles').json()['profiles']
    assert len(profiles)==4
    assert all(set(p)=={'demo_customer_id','display_name','product_model','usage_type'}for p in profiles)
    s=client.post('/demo-sessions',json={'demo_customer_id':'DEMO-U01'}).json()
    headers={'X-Session-ID':s['session_id'],'X-Demo-Session-Key':s['session_key']}
    assert client.get('/contracts/current',headers=headers).status_code==403
    assert client.post('/demo-sessions/'+s['session_id']+'/identity',headers=headers,json={'claimed_demo_customer_id':'DEMO-U01'}).status_code==200
    g=client.post('/demo-sessions/'+s['session_id']+'/consent',headers=headers,json={'action':'grant','scopes':['contract_terms']}).json()
    headers['X-Tool-Access-Token']=g['tool_access_token']
    r=client.get('/contracts/current',headers=headers)
    assert r.status_code==200 and r.json()['terms']['mandatory_end']=='2026-08-31'
    assert 'monthly_fee'not in r.json()['terms']
    assert client.post('/demo-sessions/'+s['session_id']+'/identity',headers=headers,json={'claimed_demo_customer_id':'DEMO-U01'}).status_code==200
    g=client.post('/demo-sessions/'+s['session_id']+'/consent',headers=headers,json={'action':'grant','scopes':['contract_terms','contract_costs']}).json()
    headers['X-Tool-Access-Token']=g['tool_access_token']
    assert client.get('/contracts/current',headers=headers).json()['terms']['monthly_fee']==29900
    other=client.post('/demo-sessions',json={'demo_customer_id':'DEMO-U02'}).json()
    assert client.get('/contracts/current',headers={**headers,'X-Session-ID':other['session_id']}).status_code==403

def test_connection_restore_revalidates_scope_owner_and_identity(tmp_path,monkeypatch):
    monkeypatch.setenv('CONSENT_BACKEND','sqlite');monkeypatch.setenv('CONSENT_DB',str(tmp_path/'restore.db'))
    with TestClient(create_app(Settings(require_login=False,consent_db=tmp_path/'restore.db',brief_root=tmp_path/'briefs'))) as c:
        s=c.post('/demo-sessions',json={'demo_customer_id':'DEMO-U01'}).json()
        h={'X-Session-ID':s['session_id'],'X-Demo-Session-Key':s['session_key']}
        c.post('/demo-sessions/'+s['session_id']+'/identity',headers=h,json={'claimed_demo_customer_id':'DEMO-U01'})
        grant=c.post('/demo-sessions/'+s['session_id']+'/consent',headers=h,json={'action':'grant','scopes':['contract_terms']}).json()
        h['X-Tool-Access-Token']=grant['tool_access_token']
        r=c.get('/connection/current',headers=h)
        assert r.status_code==200
        assert r.json()['product']['model_id']=='WD520VCT'
        assert r.json()['scopes']==['contract_terms']
        assert 'monthly_fee' not in r.json()['terms']
        assert c.get('/connection/current',headers={**h,'X-Tool-Access-Token':'wrong'}).status_code==403
        c.app.state.identities.clear(s['session_id'])
        assert c.get('/connection/current',headers=h).status_code==403
