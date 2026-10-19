"""수업의 함수·for·if·딕셔너리로 풀어 쓴 정수기 상담 도구.

서버 등록은 server.py, 실제 조회·판단·파일 저장은 이 파일에서 합니다.
제품/증상 자료는 공식 원문 검수 후 등록하며 계약 계산은 합성 규칙 전용입니다.
"""

from datetime import date
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

DATA_DIR = Path(__file__).parent / "data"
FIXTURE_PATH = Path(__file__).parents[2] / "05_평가" / "가상데이터" / "평가용_가상계약.json"
DEFAULT_BRIEF_ROOT = Path(__file__).parents[1] / "backend" / "ai" / "runtime" / "briefs"
BRIEF_ROOT = Path(os.environ.get("BRIEF_ROOT", str(DEFAULT_BRIEF_ROOT)))
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ALLOWED_FIXTURES = {"DEMO-A", "DEMO-B", "DEMO-C", "DEMO-D", "DEMO-E"}


def _read_json(path: Path) -> dict:
    """JSON 파일을 딕셔너리로 읽습니다. 누락·손상은 자료 오류입니다."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"자료 파일을 읽지 못했습니다: {path.name}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"자료 파일은 JSON 객체여야 합니다: {path.name}")
    return payload


def _load_json(path: Path, key: str) -> list[dict[str, Any]]:
    payload = _read_json(path)
    rows = payload.get(key)
    if not isinstance(rows, list):
        raise RuntimeError(f"자료 목록이 올바르지 않습니다: {path.name}")
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError(f"자료 항목은 객체여야 합니다: {path.name}")
    return rows


def _as_date(value: str | None, field: str) -> date | None:
    """문자열 형식뿐 아니라 실제 존재하는 날짜인지 확인합니다."""
    if value is None:
        return None
    if not isinstance(value, str) or not ISO_DATE.fullmatch(value):
        raise ValueError(f"{field}는 YYYY-MM-DD 형식이어야 합니다.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field}가 실제 날짜가 아닙니다.") from exc


def _active(row: dict) -> bool:
    return row.get("review_status") == "active"


def candidate_model_ids() -> set[str]:
    """신규 선택 후보만 제한. 기존 보유 제품의 조회 자료는 삭제하지 않습니다."""
    candidates={row['model_id'] for row in _load_json(DATA_DIR/'products.json','products')
                if _active(row) and row.get('purchase_price_status')!='unavailable'}
    import os
    if os.environ.get('CATALOG_SCOPE')=='comparison_ready':
        from .subscription.subscription_offers import demo_catalog_model_ids
        candidates &= demo_catalog_model_ids()
    return candidates


def _text(value: Any, max_length: int) -> bool:
    """공백만 있는 문자열과 너무 긴 값을 차단합니다."""
    return isinstance(value, str) and bool(value.strip()) and len(value) <= max_length


def _text_list(value: Any, max_items: int, max_length: int = 500) -> bool:
    if not isinstance(value, list) or len(value) > max_items:
        return False
    for item in value:
        if not _text(item, max_length):
            return False
    return True


def _checked_date(row: dict) -> bool:
    try:
        return _as_date(row.get("checked_at"), "checked_at") is not None
    except ValueError:
        return False


def _sources_valid(sources: Any) -> bool:
    """출처 필드의 존재·형식 검사입니다. 원문 진위 검수 자체를 대신하지 않습니다."""
    if not isinstance(sources, list) or not sources:
        return False
    for source in sources:
        if not isinstance(source, dict):
            return False
        for field in ("document_id", "title", "url"):
            if not _text(source.get(field), 2000):
                return False
        try:
            parsed_url = urlparse(source["url"])
        except ValueError:
            return False
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            return False
    return True


def lookup_product_features(model_ids: list[str], feature_query: str = "") -> dict[str, Any]:
    """검수한 모델의 기능을 조회합니다. 없는 모델은 사양을 추정하지 않습니다."""
    if not isinstance(model_ids, list):
        return {"status": "error", "code": "INVALID_MODEL_ID", "products": []}
    if not model_ids:
        return {"status": "needs_info", "missing_fields": ["model_ids"], "products": []}
    if len(model_ids) > 8 or len({m.strip().lower() for m in model_ids if isinstance(m,str)}) != len(model_ids):
        return {"status": "error", "code": "TOO_MANY_MODELS", "products": []}
    for model_id in model_ids:
        if not _text(model_id, 120):
            return {"status": "error", "code": "INVALID_MODEL_ID", "products": []}
    if not isinstance(feature_query, str) or len(feature_query) > 500:
        return {"status": "error", "code": "INVALID_QUERY", "products": []}

    query = feature_query.strip().lower()
    try:
        all_products = _load_json(DATA_DIR / "products.json", "products")
    except RuntimeError:
        return {"status": "error", "code": "DATA_LOAD_FAILED", "products": []}

    by_id = {}
    for product in all_products:
        if not _active(product):
            continue
        if not _text(product.get("model_id"), 120) or not _checked_date(product):
            continue
        if not _sources_valid(product.get("sources")):
            continue
        features = product.get("features")
        if not isinstance(features, dict) or not features:
            continue
        valid_features = True
        for name, value in features.items():
            if not _text(name, 120) or (value is not None and type(value) not in (str, bool)):
                valid_features = False
                break
        if valid_features:
            key = product["model_id"].strip().lower()
            by_id[key] = product

    found = []
    missing = []
    for model_id in model_ids:
        row = by_id.get(model_id.strip().lower())
        if row is None:
            missing.append(model_id.strip())
            continue
        features = dict(row["features"])
        if query:
            filtered_features = {}
            for name, value in features.items():
                if query in str(name).lower() or query in str(value).lower() or str(name).lower() in query:
                    filtered_features[name] = value
            features = filtered_features
            if not features:
                missing.append(model_id.strip())
                continue
        found.append({
            **{k:row[k] for k in ("display_name","image_url","product_url","purchase_price","purchase_price_status","subscription_monthly_from","price_checked_at","price_note","card_benefits","purchase_benefits") if k in row},
            "model_id": row["model_id"], "features": features,
            "checked_at": row["checked_at"], "sources": row["sources"],
            "limitations": row.get("limitations", "검수된 문서 범위의 정보입니다."),
            "is_demo": bool(row.get("is_demo", False)),
        })
    from .support.product_variants import variant_metadata
    metadata=variant_metadata()
    for product in found:
        row=metadata.get(product['model_id'])
        if row:product.update({k:row[k] for k in ('family_id','color_name','color_hex')})
    status = "ok"
    if not found:
        status = "unverified"
    result = {"status": status, "products": found, "unverified_model_ids": missing}
    if missing:
        result["message"] = "이 제품의 해당 기능은 공식 제품 페이지에서 확인해 주세요." if all(m.strip().lower() in by_id for m in missing) else "이 제품의 사양은 공식 제품 페이지에서 확인해 주세요."
    return result


def assess_symptom_next_step(
    model_id: str, symptom: str, occurred_at: str = "", flow_id: str = "", symptom_types: list[str] | None = None
) -> dict[str, Any]:
    """검수된 모델별 증상 흐름을 조회합니다. occurred_at은 기록용이며 판단에 쓰지 않습니다."""
    missing = []
    for field, value, limit in (("model_id", model_id, 120), ("symptom", symptom, 500)):
        if not isinstance(value, str) or len(value) > limit:
            return {"status": "error", "code": "INVALID_INPUT", "field": field}
        if not value.strip():
            missing.append(field)
    if missing:
        return {"status": "needs_info", "missing_fields": missing}
    for field, value in (("occurred_at", occurred_at), ("flow_id", flow_id)):
        if not isinstance(value, str) or len(value) > 120:
            return {"status": "error", "code": "INVALID_INPUT", "field": field}
    allowed_types={'hot_water_temperature','hot_water_not_dispensing','cold_water_problem','water_leak','unknown'}
    if symptom_types is not None and (not isinstance(symptom_types,list) or len(symptom_types)>4 or any(not isinstance(t,str) or t not in allowed_types for t in symptom_types)):
        return {'status':'error','code':'INVALID_SYMPTOM_TYPES'}
    semantic_flows={'hot_water_not_dispensing':'WATER-HOT','cold_water_problem':'WATER-COLD','water_leak':'WATER-LEAK'}
    requested_flows={semantic_flows[t] for t in symptom_types or [] if t in semantic_flows}
    # 위험 표현은 안전 검증이며 일반 문의의 도구 선택은 LLM이 담당한다.
    for term in ("감전", "타는 냄새", "탄 냄새", "연기", "불꽃"):
        if term in symptom:
            result = {
                "status": "unverified", "model_id": model_id, "symptom": symptom,
                "source_ids": [], "message": "위험 관련 내용이 포함되어 일반 자가조치 흐름을 적용하지 않았습니다.",
                "safety_notice": "위험 상황의 공식 안전 안내와 지원 경로를 먼저 확인하세요. 분해·수리 방법을 추정하지 마세요.",
            }
            if model_id.strip().upper()=='WD520VCT':
                result['message']='연기·이상한 냄새가 나면 사용을 중단하고 분해·수리하지 마세요.'
                result['safety_notice']='공식 사용설명서는 전원 플러그를 뺀 뒤 LG전자 서비스 센터에 연락하도록 안내합니다. 젖은 손으로 플러그를 만지지 마세요. 가스 누출이 의심되면 제품·플러그를 건드리지 말고 환기하세요.'
                result['source_ids']=['LG-WD520-MANUAL-SAFETY']
                result['sources']=[{'document_id':'LG-WD520-MANUAL-SAFETY','title':'WD520VCT 공식 사용설명서 안전 주의사항','url':'https://www.lge.co.kr/support/product-WD520VCT','section':'전원 및 제품 이상 시 안전 주의사항','model_id':'WD520VCT','checked_at':'2026-10-07'}]
            return result
    # Temperature complaints are distinct from no water dispensing. This is
    # clarification, not an approved model-specific repair procedure.
    temperature_only=symptom_types is not None and set(symptom_types)=={'hot_water_temperature'}
    if symptom_types is None and '온수' in symptom and any(t in symptom for t in ('미지근','뜨겁지','온도')):
        temperature_only=True
    if temperature_only:
        persistent=any(t in symptom for t in ('계속','매번','둘째','두 번째'))
        first_only=any(t in symptom for t in ('첫 잔만','첫잔만','처음만'))
        question='선택한 온수 설정 온도는 몇 도인가요?' if persistent or first_only else '처음 받은 한 잔만 미지근한가요, 아니면 다음 잔도 계속 미지근한가요?'
        return {'status':'needs_info','model_id':model_id,'symptom':symptom,
                'recognized_symptom':'hot_water_temperature','missing_fields':['symptom'],
                'message':'온수가 나오지만 기대한 온도보다 낮다는 문의로 이해했어요. '+question,
                'source_ids':[],'next_action':'ask_user','continue_tool_calls':False,
                'safety_notice':'손으로 물 온도를 확인하거나 제품을 분해하지 마세요. 모델별 조치 적용은 추가 확인이 필요합니다.'}
    if symptom_types is not None and set(symptom_types)=={'unknown'} and any(t in symptom for t in ('미지근','온도','뜨겁지')):
        return {'status':'needs_info','model_id':model_id,'symptom':symptom,'missing_fields':['symptom'],
                'message':'온수가 덜 뜨거운 건가요, 냉수가 덜 시원한 건가요?',
                'source_ids':[],'next_action':'ask_user','continue_tool_calls':False}

    try:
        rows = _load_json(DATA_DIR / "symptom_flows.json", "flows")
    except RuntimeError:
        return {"status": "error", "code": "DATA_LOAD_FAILED", "source_ids": []}

    matched = []
    normalized_model = model_id.strip().lower()
    normalized_symptom = re.sub(r"\s+", "", symptom.lower())
    for old,new in [('뜨거운물','온수'),('차가운물','냉수'),('따뜻한물','온수'),('물이새어','누수'),('물이새고','누수'),('물이샙','누수'),('나오지않','안나'),('나오질않','안나')]:
        normalized_symptom=normalized_symptom.replace(old,new)
    normalized_symptom=re.sub(r"(온수|냉수)(가|이|는|도)",r"\1",normalized_symptom)
    for row in rows:
        if not _active(row) or not _checked_date(row):
            continue
        if not _text_list(row.get("source_ids"), 30) or not row["source_ids"]:
            continue
        if not _text_list(row.get("next_steps"), 30) or not row["next_steps"]:
            continue
        if not _text_list(row.get("model_ids"), 100, 120):
            continue
        if not _text_list(row.get("symptom_terms"), 30):
            continue
        if flow_id and row.get("flow_id") != flow_id:
            continue
        model_matches = False
        for registered_model in row["model_ids"]:
            if registered_model.strip().lower() == normalized_model:
                model_matches = True
                break
        if not model_matches:
            continue
        if symptom_types is not None:
            if row['flow_id'] in requested_flows:matched.append(row)
            continue
        # 직접 도구를 사용하는 기존 클라이언트의 호환 경로만 유지한다.
        for term in row["symptom_terms"]:
            if re.sub(r"(온수|냉수)(가|이|는|도)",r"\1",re.sub(r"\s+", "", term.lower())) in normalized_symptom:
                matched.append(row)
                break

    if len(matched) != 1:
        return {
            "status": "unverified", "model_id": model_id, "symptom": symptom,
            "message": "여러 증상이 함께 보여 먼저 확인할 증상을 골라주세요." if matched else "현재 모델과 증상에 맞는 점검 절차를 자료에서 확인하지 못했습니다. 발생 상황을 조금 더 알려주세요.",
            "missing_fields": ["symptom"],
            "candidate_flows": [{"flow_id":r["flow_id"],"symptom_terms":r["symptom_terms"]} for r in matched],
            "next_action": "ask_user", "continue_tool_calls": False,
            "source_ids": [], "safety_notice": "미검수 자료나 모호한 증상으로 자가수리를 안내하지 않습니다.",
        }
    row = matched[0]
    return {
        "status": "ok", "model_id": model_id, "symptom": symptom,
        "next_steps": row["next_steps"], "checked_at": row["checked_at"],
        "source_ids": row["source_ids"],
        "safety_notice": row.get("safety_notice", "검수 문서의 적용 모델과 주의사항을 확인하세요."),
        "limitations": row.get("limitations", "고장 원인을 확정하는 진단이 아닙니다."),
        "is_demo": bool(row.get("is_demo", False)),
    }


def _fixture(fixture_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    if fixture_id not in ALLOWED_FIXTURES:
        return None
    payload = _read_json(FIXTURE_PATH)
    if payload.get("rule_id") != "SYNTH-01" or not isinstance(payload.get("rules"), dict):
        raise RuntimeError("합성 규칙이 올바르지 않습니다.")
    contracts = payload.get("contracts")
    if not isinstance(contracts, list):
        raise RuntimeError("가상 계약 목록이 올바르지 않습니다.")
    selected = None
    for contract in contracts:
        if not isinstance(contract, dict):
            raise RuntimeError("가상 계약 항목이 올바르지 않습니다.")
        if contract.get("id") == fixture_id:
            selected = contract
            break
    if selected is None:
        return None
    # expected_* 정답을 Agent에 노출하지 않도록 허용한 입력 필드만 복사합니다.
    terms = {}
    for field in ("id", "mandatory_end", "contract_end", "exit_date", "arrears", "discount_return"):
        if field in selected:
            terms[field] = selected[field]
    return payload["rules"], terms


def lookup_contract_terms(
    demo_fixture_id: str = "", mandatory_end: str = "", contract_end: str = "", exit_date: str = ""
) -> dict[str, Any]:
    """가상 계약 또는 고객 제공 날짜를 확인합니다. 실제 계약 DB 조회가 아닙니다."""
    if demo_fixture_id:
        try:
            data = _fixture(demo_fixture_id)
        except RuntimeError:
            return {"status": "error", "code": "DATA_LOAD_FAILED", "terms": {}}
        if data is None:
            return {"status": "error", "code": "UNKNOWN_FIXTURE", "terms": {}}
        rules, terms = data
        return {
            "status": "ok", "is_demo": True, "rule_id": "SYNTH-01", "terms": terms,
            "source_ids": ["SYNTH-01"],
            "limitations": "기술 평가용 합성 조건이며 실제 LG 계약·요금·법령 기준이 아닙니다.",
        }
    parsed = {}
    for field, value in (("mandatory_end", mandatory_end), ("contract_end", contract_end), ("exit_date", exit_date)):
        if value == "":
            value = None
        try:
            _as_date(value, field)
        except ValueError:
            return {"status": "error", "code": "INVALID_DATE", "field": field, "terms": {}}
        parsed[field] = value
    if parsed["mandatory_end"] and parsed["contract_end"]:
        if parsed["mandatory_end"] > parsed["contract_end"]:
            return {"status": "error", "code": "INVALID_PERIOD", "terms": parsed}
    has_date = False
    for value in parsed.values():
        if value is not None:
            has_date = True
    if not has_date:
        return {"status": "needs_info", "missing_fields": ["contract_end"]}
    return {
        "status": "unverified", "is_demo": False, "terms": parsed, "source_ids": [],
        "limitations": "입력 날짜만 확인했습니다. 적용 약관·요율이 미검수이므로 실제 계약 조회나 법적 판단이 아닙니다.",
    }


def assess_exit_costs(
    demo_fixture_id: str = "", mandatory_end: str = "", contract_end: str = "",
    exit_date: str = "", arrears: int | None = None, discount_return: int | None = None,
) -> dict[str, Any]:
    """SYNTH-01 가상 계약만 계산합니다. 종료일 당일까지 기간에 포함됩니다."""
    for field, amount in (("arrears", arrears), ("discount_return", discount_return)):
        if amount is not None and (type(amount) is not int or amount < 0):
            return {"status": "error", "code": "INVALID_AMOUNT", "field": field, "estimated_total": None}
    if not demo_fixture_id:
        check = lookup_contract_terms("", mandatory_end, contract_end, exit_date)
        if check["status"] == "error":
            return {"status": "error", "code": check["code"], "estimated_total": None}
        return {
            "status": "unverified", "cost_items": [], "confirmed_subtotal": 0,
            "estimated_total": None, "source_ids": [],
            "limitations": "실제 계약에 적용되는 요율·약관이 미검수이므로 비용을 계산하지 않았습니다.",
        }
    try:
        data = _fixture(demo_fixture_id)
    except RuntimeError:
        return {"status": "error", "code": "DATA_LOAD_FAILED", "estimated_total": None}
    if data is None:
        return {"status": "error", "code": "UNKNOWN_FIXTURE", "estimated_total": None}
    rules, terms = data
    for field, value in (("mandatory_end", mandatory_end), ("contract_end", contract_end), ("exit_date", exit_date)):
        if value != "":
            terms[field] = value
    if arrears is not None:
        terms["arrears"] = arrears
    if discount_return is not None:
        terms["discount_return"] = discount_return
    dates = {}
    missing = []
    for field in ("mandatory_end", "contract_end", "exit_date"):
        try:
            dates[field] = _as_date(terms.get(field), field)
        except ValueError:
            return {"status": "error", "code": "INVALID_DATE", "field": field, "estimated_total": None}
        if dates[field] is None:
            missing.append(field)
    if missing:
        return {"status": "needs_info", "missing_fields": missing, "estimated_total": None}
    mandatory = dates["mandatory_end"]
    contract = dates["contract_end"]
    exit_day = dates["exit_date"]
    if mandatory > contract:
        return {"status": "error", "code": "INVALID_PERIOD", "estimated_total": None}
    for field in ("before_or_on_mandatory_end_penalty", "collection_before_or_on_contract_end", "discount_return_before_or_on_contract_end"):
        if type(rules.get(field)) is not int or rules[field] < 0:
            return {"status": "error", "code": "INVALID_RULE", "estimated_total": None}
    arrears_value = terms.get("arrears", 0)
    discount_value = terms.get("discount_return")
    if type(arrears_value) is not int or arrears_value < 0:
        return {"status": "error", "code": "INVALID_AMOUNT", "estimated_total": None}
    if "discount_return" in terms and discount_value != "unknown":
        if type(discount_value) is not int or discount_value < 0:
            return {"status": "error", "code": "INVALID_AMOUNT", "estimated_total": None}

    # 이 0원 규칙은 SYNTH-01에서만 적용합니다. 실제 계약 기준이 아닙니다.
    after_contract = exit_day > contract
    penalty = 0
    collection = 0
    discount = 0
    discount_status = "confirmed"
    arrears_status = "confirmed"
    if after_contract:
        arrears_value = 0
        arrears_status = "not_applicable"
        discount_status = "not_applicable"
    else:
        if exit_day <= mandatory:
            penalty = rules["before_or_on_mandatory_end_penalty"]
        collection = rules["collection_before_or_on_contract_end"]
        if discount_value == "unknown":
            discount = None
            discount_status = "unverified"
        elif "discount_return" in terms:
            discount = discount_value
        else:
            discount = rules["discount_return_before_or_on_contract_end"]
    items = [
        {"name": "위약금(합성 규칙)", "status": "confirmed", "amount": penalty, "source_ids": ["SYNTH-01"]},
        {"name": "수거비(합성 규칙)", "status": "confirmed", "amount": collection, "source_ids": ["SYNTH-01"]},
        {"name": "미납금(가상 입력)", "status": arrears_status, "amount": arrears_value, "source_ids": ["SYNTH-01"]},
        {"name": "할인반환금(합성 규칙)", "status": discount_status, "amount": discount, "source_ids": ["SYNTH-01"]},
    ]
    subtotal = 0
    has_unknown = False
    for item in items:
        if item["status"] == "confirmed":
            subtotal += item["amount"]
        if item["status"] == "unverified":
            has_unknown = True
    total = subtotal
    status = "ok"
    if has_unknown:
        total = None
        status = "unverified"
    return {
        "status": status, "is_demo": True, "rule_id": "SYNTH-01", "period_summary": terms,
        "cost_items": items, "confirmed_subtotal": subtotal, "estimated_total": total,
        "source_ids": ["SYNTH-01"],
        "limitations": "기술 평가용 합성 계산이며 실제 LG 계약·요금·법령 기준이 아닙니다.",
    }


def _bullets(values: list[str]) -> str:
    lines = []
    for value in values:
        lines.append("- " + value.replace("\n", " "))
    if not lines:
        return "- 없음"
    return "\n".join(lines)


def create_consultation_brief(
    summary: str, confirmed_facts: list[str] | None = None,
    unresolved_questions: list[str] | None = None, source_ids: list[str] | None = None,
) -> dict[str, Any]:
    """고객이 요청한 상담 요약을 로컬 PDF로 저장합니다. 실제 접수는 하지 않습니다."""
    if not _text(summary, 2000):
        return {"status": "error", "code": "INVALID_SUMMARY"}
    groups = []
    for values, limit in ((confirmed_facts, 20), (unresolved_questions, 20), (source_ids, 30)):
        if values is None:
            values = []
        if not isinstance(values, list):
            return {"status": "error", "code": "INVALID_FIELD"}
        if len(values) > limit:
            return {"status": "error", "code": "TOO_MANY_ITEMS"}
        if not _text_list(values, limit):
            return {"status": "error", "code": "INVALID_FIELD"}
        groups.append(values)
    facts, questions, sources = groups
    brief_id = uuid4().hex
    root = BRIEF_ROOT.resolve()
    target = (root / f"brief-{brief_id}.pdf").resolve()
    if not target.is_relative_to(root):
        return {"status": "error", "code": "INVALID_PATH"}
    try:
        root.mkdir(parents=True, exist_ok=True)
        from 정수기프로젝트.app.mcp.brief_pdf import write_brief_pdf
        write_brief_pdf(target, summary, facts, questions, sources)
    except OSError:
        return {"status": "error", "code": "BRIEF_WRITE_FAILED"}
    return {
        "status": "ok", "brief_id": brief_id, "absolute_path": str(target),
        "source_ids": sources, "message": "로컬 상담 준비서를 생성했습니다. 실제 접수는 진행되지 않았습니다.",
    }
