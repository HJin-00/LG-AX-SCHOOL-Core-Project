"""Agent가 MCP 도구 명세를 조회하고 선택한 도구를 호출하는 연결부.

수업과 같은 Client(mcp) 연결을 사용합니다. 별도 프로세스/포트가 필요 없고,
Tool Calling의 선택은 Agent가 담당합니다. 이 파일은 LLM을 호출하지 않습니다.
"""

from typing import Any
from copy import deepcopy
from fastmcp import Client
from .server import mcp

ALLOWED_TOOLS = {'get_official_channel', 'compare_retention_renewal', 'create_contract_document_brief', 'create_renewal_brief', 'search_contract_knowledge', 'assess_contract_document_costs', 'lookup_subscription_offers', 'compare_contract_options', 'lookup_product_features', 'suggest_contract_timing', 'lookup_contract_document'}


class MCPToolError(RuntimeError):
    """통신·명세·도구 실행 오류. 업무 결과의 unverified와는 구분합니다."""


def _server_client() -> Client:
    # 수업의 서버 객체 연결: 같은 Python 프로세스 안에서 MCP 프로토콜로 호출.
    return Client(mcp, timeout=30.0)


def _data(result: Any) -> dict[str, Any]:
    if result.is_error:
        raise MCPToolError("MCP 도구 실행에 실패했습니다.")
    if not isinstance(result.data, dict):
        raise MCPToolError("MCP 도구가 딕셔너리 결과를 반환하지 않았습니다.")
    return result.data


def _agent_schema(name, schema):
    schema = deepcopy(schema)
    if name in {"lookup_contract_terms", "assess_exit_costs", "create_consultation_brief", "lookup_contract_document", "assess_contract_document_costs", "compare_contract_options", "create_contract_document_brief", "compare_retention_renewal", "create_renewal_brief", "suggest_contract_timing", "lookup_care_schedule", "create_support_brief"}:
        for key in ("session_id", "access_token"):
            schema.get("properties", {}).pop(key, None)
        schema["required"] = [key for key in schema.get("required", []) if key not in {"session_id", "access_token"}]
    if name=='assess_symptom_next_step':
        schema['required']=list(dict.fromkeys([*schema.get('required',[]),'symptom_types']))
    if name=='search_contract_knowledge':
        for key in ('purpose','model_id'):schema.get('properties',{}).pop(key,None)
        schema['required']=[key for key in schema.get('required',[]) if key not in {'purpose','model_id'}]
    if name=='lookup_subscription_offers':schema.get('properties',{}).pop('exclude_model_id',None)
    return schema


async def get_tool_specs() -> list[dict[str, Any]]:
    """Agent가 사용할 도구명·설명·입력 JSON Schema를 서버에서 가져옵니다.

    특정 LLM 제공자의 요청 형식으로 변환하는 작업은 agent.py에서 합니다.
    서버 명세를 그대로 가져오므로 입력 필드를 별도로 중복 작성하지 않습니다.
    """
    specs = []
    try:
        async with _server_client() as client:
            registered = await client.list_tools()
            for tool in registered:
                if tool.name in ALLOWED_TOOLS:
                    specs.append({
                        "name": tool.name,
                        "description": tool.description or "",
                        "input_schema": _agent_schema(tool.name, tool.inputSchema),
                    })
    except Exception as exc:
        raise MCPToolError("MCP 도구 명세를 가져오지 못했습니다.") from exc
    return specs


async def call_tool(name: str, arguments: dict[str, Any], *, trusted_authorization: dict | None = None) -> dict[str, Any]:
    """LLM이 선택한 허용 도구 하나만 호출합니다. 도구를 자동 선택하지 않습니다."""
    if name not in ALLOWED_TOOLS:
        raise MCPToolError("허용되지 않은 MCP 도구입니다.")
    if not isinstance(arguments, dict):
        raise MCPToolError("도구 인자는 딕셔너리여야 합니다.")
    arguments = dict(arguments)
    if name in {"lookup_contract_terms", "assess_exit_costs", "create_consultation_brief", "lookup_contract_document", "assess_contract_document_costs", "compare_contract_options", "create_contract_document_brief", "compare_retention_renewal", "create_renewal_brief", "suggest_contract_timing", "lookup_care_schedule", "create_support_brief"}:
        allowed = {"exit_date", "exit_date_a", "exit_date_b", "comparison_date"} if name == "create_contract_document_brief" else {"exit_date_a", "exit_date_b", "comparison_date"} if name == "compare_contract_options" else ({"exit_date"} if name in {"assess_exit_costs", "create_consultation_brief", "assess_contract_document_costs", "create_contract_document_brief", "compare_retention_renewal", "create_renewal_brief", "suggest_contract_timing", "lookup_care_schedule", "create_support_brief"} else set())
        if name in {'compare_retention_renewal','create_renewal_brief'}:
            allowed = {'offer_id','comparison_date','comparison_months','maintenance_monthly_fee','installation_conditions','planned_start_date','card_id','card_spend','card_eligibility','card_application_date'}
        if name in {'suggest_contract_timing','lookup_care_schedule'}:allowed=set()
        if name=='create_support_brief':allowed={'topic','model_id','symptom','symptom_types'}
        if set(arguments) - allowed:
            raise MCPToolError("Agent가 계약·권한 인자를 직접 지정할 수 없습니다.")
        auth = trusted_authorization or {}
        arguments.update(session_id=auth.get("session_id", ""), access_token=auth.get("access_token", ""))
    try:
        async with _server_client() as client:
            result = await client.call_tool(name, arguments)
            return _data(result)
    except MCPToolError:
        raise
    except Exception as exc:
        # 상세 오류를 고객에게 그대로 보여 주지 않도록 일반 문구로 변환합니다.
        raise MCPToolError("MCP 도구 호출에 실패했습니다.") from exc


async def lookup_product_features(model_ids: list[str], feature_query: str = "") -> dict[str, Any]:
    return await call_tool("lookup_product_features", {
        "model_ids": model_ids, "feature_query": feature_query,
    })


async def assess_symptom_next_step(model_id: str, symptom: str, occurred_at: str = "", flow_id: str = "") -> dict[str, Any]:
    return await call_tool("assess_symptom_next_step", {
        "model_id": model_id, "symptom": symptom, "occurred_at": occurred_at, "flow_id": flow_id,
    })


async def lookup_contract_terms(*, trusted_authorization: dict | None = None) -> dict[str, Any]:
    return await call_tool("lookup_contract_terms", {}, trusted_authorization=trusted_authorization)


async def assess_exit_costs(exit_date: str, *, trusted_authorization: dict | None = None) -> dict[str, Any]:
    return await call_tool("assess_exit_costs", {"exit_date": exit_date}, trusted_authorization=trusted_authorization)


async def create_consultation_brief(exit_date: str = '', *, trusted_authorization: dict | None = None) -> dict[str, Any]:
    return await call_tool('create_consultation_brief', {'exit_date': exit_date}, trusted_authorization=trusted_authorization)
