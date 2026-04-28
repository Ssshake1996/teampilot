import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.data_skill import (
    ConnectorAuthType,
    DataConnector,
    SkillRun,
    SkillRunStatus,
    TaskDataSkill,
    TaskDataSkillStatus,
)
from app.models.task import Task
from app.schemas.data_skill import DataConnectorCreate, DataConnectorUpdate, TaskDataSkillUpdate
from app.services.ai.llm_client import LLMClient
from app.services import task_service


HTTP_PATTERN = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+([^\s，。；;]+)", re.IGNORECASE)
PLACEHOLDER_PATTERN = re.compile(r"{([A-Za-z_][A-Za-z0-9_]*)}")
_DYNAMIC_TOKEN_CACHE: dict[str, dict[str, Any]] = {}


async def list_connectors(db: AsyncSession) -> list[DataConnector]:
    rows = await db.execute(select(DataConnector).order_by(DataConnector.created_at.desc()))
    return rows.scalars().all()


async def get_connector(db: AsyncSession, connector_id: uuid.UUID) -> DataConnector | None:
    return (
        await db.execute(select(DataConnector).where(DataConnector.id == connector_id))
    ).scalar_one_or_none()


async def create_connector(db: AsyncSession, data: DataConnectorCreate) -> DataConnector:
    connector = DataConnector(**data.model_dump())
    db.add(connector)
    await db.flush()
    return connector


async def update_connector(
    db: AsyncSession,
    connector_id: uuid.UUID,
    data: DataConnectorUpdate,
) -> DataConnector | None:
    connector = await get_connector(db, connector_id)
    if not connector:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(connector, field, value)
    await db.flush()
    await db.refresh(connector)
    return connector


async def delete_connector(db: AsyncSession, connector_id: uuid.UUID) -> bool:
    connector = await get_connector(db, connector_id)
    if not connector:
        return False
    await db.delete(connector)
    await db.flush()
    return True


def _task_text(task: Task) -> str:
    return "\n".join([task.title or "", task.goal or "", task.description or ""]).strip()


def _safe_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def _connector_payload(connector: DataConnector) -> dict:
    return {
        "id": str(connector.id),
        "name": connector.name,
        "key": connector.key,
        "description": connector.description,
        "base_url": connector.base_url,
    }


def _choose_connector(
    natural_language: str,
    connectors: list[DataConnector],
    connector_id: uuid.UUID | None,
) -> DataConnector | None:
    if connector_id:
        return next((item for item in connectors if item.id == connector_id), None)
    lowered = natural_language.lower()
    for connector in connectors:
        if connector.key.lower() in lowered or connector.name.lower() in lowered:
            return connector
    if len(connectors) == 1:
        return connectors[0]
    return None


async def _generate_skill_with_ai(
    llm: LLMClient,
    task: Task,
    natural_language: str,
    connectors: list[DataConnector],
) -> dict:
    messages = [
        {
            "role": "system",
            "content": (
                "你是任务数据 Skill 生成器。把用户的白话数据采集说明转成可执行 JSON。"
                "只允许选择输入里的 connector，不要编造接口。只返回 JSON，不要 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": {
                        "title": task.title,
                        "description": task.description,
                    },
                    "connectors": [_connector_payload(item) for item in connectors],
                    "description": natural_language,
                    "expected_schema": {
                        "connector_key": "连接器 key",
                        "method": "GET|POST",
                        "path": "/api/example/{param}",
                        "params": {
                            "param": {
                                "from": "task.text",
                                "fallback": "ask_user",
                            }
                        },
                        "progress_strategy": "infer_from_response",
                        "analysis_prompt": "分析返回数据并给出进度、风险、会签建议",
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]
    result = await llm.chat_json(messages, max_tokens=1200, temperature=0.1)
    return result if isinstance(result, dict) else {}


def _generate_skill_by_rules(
    task: Task,
    natural_language: str,
    connectors: list[DataConnector],
    connector_id: uuid.UUID | None,
) -> dict:
    connector = _choose_connector(natural_language, connectors, connector_id)
    match = HTTP_PATTERN.search(natural_language)
    method = match.group(1).upper() if match else "GET"
    path = match.group(2).strip().rstrip("。；;,，.") if match else ""
    placeholders = PLACEHOLDER_PATTERN.findall(path)
    params = {
        name: {
            "from": "task.text",
            "fallback": "ask_user",
        }
        for name in placeholders
    }
    return {
        "connector_key": connector.key if connector else "",
        "method": method,
        "path": path,
        "params": params,
        "progress_strategy": "infer_from_response",
        "analysis_prompt": "根据接口返回数据判断任务进度、风险和是否建议会签。",
        "generated_from": "rules",
        "task_text_sample": _task_text(task)[:300],
    }


async def generate_task_data_skill(
    db: AsyncSession,
    task_id: uuid.UUID,
    natural_language: str,
    user_id: uuid.UUID,
    connector_id: uuid.UUID | None = None,
    llm: LLMClient | None = None,
) -> TaskDataSkill:
    task = await task_service.get_task(db, task_id)
    if not task:
        raise ValueError("Task not found.")
    connectors = (await db.execute(select(DataConnector).where(DataConnector.is_enabled == True))).scalars().all()
    chosen = _choose_connector(natural_language, connectors, connector_id)
    skill_json = None
    if llm:
        try:
            skill_json = await _generate_skill_with_ai(llm, task, natural_language, connectors)
        except Exception:
            skill_json = None
    if not skill_json:
        skill_json = _generate_skill_by_rules(task, natural_language, connectors, connector_id)
    connector_key = skill_json.get("connector_key")
    if connector_key:
        chosen = next((item for item in connectors if item.key == connector_key), chosen)

    skill = TaskDataSkill(
        task_id=task.id,
        connector_id=chosen.id if chosen else None,
        created_by_id=user_id,
        natural_language=natural_language,
        skill_json=skill_json,
        status=TaskDataSkillStatus.DRAFT,
    )
    if chosen:
        skill.connector = chosen
    db.add(skill)
    await db.flush()
    await db.refresh(skill)
    return skill


async def list_task_data_skills(db: AsyncSession, task_id: uuid.UUID) -> list[TaskDataSkill]:
    rows = await db.execute(
        select(TaskDataSkill)
        .options(selectinload(TaskDataSkill.connector))
        .where(TaskDataSkill.task_id == task_id)
        .order_by(TaskDataSkill.created_at.desc())
    )
    return rows.scalars().all()


async def get_task_data_skill(db: AsyncSession, skill_id: uuid.UUID) -> TaskDataSkill | None:
    return (
        await db.execute(
            select(TaskDataSkill)
            .options(selectinload(TaskDataSkill.connector))
            .where(TaskDataSkill.id == skill_id)
        )
    ).scalar_one_or_none()


async def update_task_data_skill(
    db: AsyncSession,
    skill_id: uuid.UUID,
    data: TaskDataSkillUpdate,
) -> TaskDataSkill | None:
    skill = await get_task_data_skill(db, skill_id)
    if not skill:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(skill, field, value)
    skill.status = TaskDataSkillStatus.DRAFT
    skill.confirmed_by_id = None
    skill.confirmed_at = None
    await db.flush()
    await db.refresh(skill)
    return skill


async def confirm_task_data_skill(
    db: AsyncSession,
    skill_id: uuid.UUID,
    user_id: uuid.UUID,
) -> TaskDataSkill | None:
    skill = await get_task_data_skill(db, skill_id)
    if not skill:
        return None
    skill.status = TaskDataSkillStatus.CONFIRMED
    skill.confirmed_by_id = user_id
    skill.confirmed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(skill)
    return skill


def _extract_param_from_task_text(name: str, text: str) -> str | None:
    direct = re.search(rf"{re.escape(name)}\s*[:=]\s*([A-Za-z0-9_.:-]+)", text, re.IGNORECASE)
    if direct:
        return direct.group(1)

    if name.lower() in {"feature_id", "feature", "featureid"}:
        feature = re.search(r"(?:特性|feature)\s*[:：#]?\s*([A-Za-z0-9_.-]+)", text, re.IGNORECASE)
        if feature:
            return feature.group(1)

    generic_id = re.search(r"\b([A-Z]{2,}[-_][A-Za-z0-9_.-]+)\b", text)
    if generic_id:
        return generic_id.group(1)
    return None


def _resolve_params(skill: TaskDataSkill, task: Task, provided: dict) -> tuple[dict, list[str]]:
    skill_json = skill.skill_json or {}
    text = _task_text(task)
    resolved = {}
    missing = []
    for name in (skill_json.get("params") or {}).keys():
        value = provided.get(name)
        if value is None or value == "":
            value = _extract_param_from_task_text(name, text)
        if value is None or value == "":
            missing.append(name)
        else:
            resolved[name] = value
    return resolved, missing


def _render_path(path: str, params: dict) -> str:
    rendered = path
    for name, value in params.items():
        rendered = rendered.replace("{" + name + "}", str(value))
    return rendered


def _json_path_get(data: Any, path: str | None, default: Any = None) -> Any:
    if not path:
        return default
    current = data
    clean_path = path[2:] if path.startswith("$.") else path.lstrip("$")
    if not clean_path:
        return current
    for part in clean_path.split("."):
        if not part:
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)])?", part)
        if not match:
            return default
        key, index = match.groups()
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
        if index is not None:
            if not isinstance(current, list):
                return default
            idx = int(index)
            if idx >= len(current):
                return default
            current = current[idx]
    return current


def _absolute_connector_url(connector: DataConnector, path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    path = path_or_url if path_or_url.startswith("/") else "/" + path_or_url
    return connector.base_url.rstrip("/") + path


def _dynamic_token_cache_key(connector: DataConnector) -> str:
    config_text = json.dumps(connector.auth_config_json or {}, sort_keys=True, ensure_ascii=False)
    return f"{connector.id}:{config_text}"


async def _get_dynamic_token(connector: DataConnector) -> str:
    config = connector.auth_config_json or {}
    cache_key = _dynamic_token_cache_key(connector)
    cached = _DYNAMIC_TOKEN_CACHE.get(cache_key)
    now = datetime.now(timezone.utc)
    if cached and cached.get("expires_at") and cached["expires_at"] > now:
        return cached["token"]

    token_url = config.get("token_url")
    if not token_url:
        raise ValueError("Dynamic token auth requires token_url.")

    method = (config.get("method") or "POST").upper()
    headers = dict(config.get("headers") or {})
    query = dict(config.get("query") or {})
    body = config.get("body")
    url = _absolute_connector_url(connector, token_url)
    async with httpx.AsyncClient(timeout=connector.timeout_seconds, verify=connector.verify_tls) as client:
        response = await client.request(
            method,
            url,
            params=query or None,
            headers=headers or None,
            json=body if method != "GET" else None,
        )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("Dynamic token response is not JSON.") from exc

    token = _json_path_get(payload, config.get("token_path") or "$.access_token")
    if not token:
        raise ValueError("Dynamic token response does not contain token.")

    expires_in = _json_path_get(payload, config.get("expires_in_path"))
    if expires_in is None:
        expires_in = config.get("cache_seconds", 3600)
    try:
        ttl = max(int(expires_in) - 30, 1)
    except (TypeError, ValueError):
        ttl = 3600
    _DYNAMIC_TOKEN_CACHE[cache_key] = {
        "token": str(token),
        "expires_at": now + timedelta(seconds=ttl),
    }
    return str(token)


async def _apply_auth(connector: DataConnector, headers: dict, query_params: dict) -> httpx.BasicAuth | None:
    config = connector.auth_config_json or {}
    if connector.auth_type == ConnectorAuthType.BEARER and config.get("token"):
        headers["Authorization"] = f"Bearer {config['token']}"
    elif connector.auth_type == ConnectorAuthType.API_KEY and config.get("key_value"):
        key_name = config.get("key_name") or "X-API-Key"
        if (config.get("in") or "header") == "query":
            query_params[key_name] = config["key_value"]
        else:
            headers[key_name] = config["key_value"]
    elif connector.auth_type == ConnectorAuthType.BASIC:
        username = config.get("username")
        password = config.get("password")
        if username is not None and password is not None:
            return httpx.BasicAuth(username, password)
    elif connector.auth_type == ConnectorAuthType.DYNAMIC_TOKEN:
        token = await _get_dynamic_token(connector)
        token_prefix = config.get("token_prefix", "Bearer")
        token_value = f"{token_prefix} {token}".strip() if token_prefix else token
        target_name = config.get("target_name") or "Authorization"
        if (config.get("target") or "header") == "query":
            query_params[target_name] = token_value
        else:
            headers[target_name] = token_value
    return None


def _flatten_numbers(data: Any, prefix: str = "") -> dict[str, float]:
    values: dict[str, float] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else str(key)
            values.update(_flatten_numbers(value, full_key))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            values.update(_flatten_numbers(value, f"{prefix}[{index}]"))
    elif isinstance(data, (int, float)) and not isinstance(data, bool):
        values[prefix] = float(data)
    return values


def _find_metric(numbers: dict[str, float], candidates: list[str]) -> float | None:
    normalized = {key.lower().replace("-", "_"): value for key, value in numbers.items()}
    for candidate in candidates:
        for key, value in normalized.items():
            leaf = key.split(".")[-1]
            if leaf == candidate or leaf.endswith("_" + candidate):
                return value
    return None


def infer_metrics(response_data: Any) -> dict:
    numbers = _flatten_numbers(response_data)
    total = _find_metric(numbers, ["total_cases", "case_total", "total", "total_count", "all"])
    executed = _find_metric(numbers, ["executed_cases", "executed", "run_cases", "run", "completed"])
    passed = _find_metric(numbers, ["passed_cases", "passed", "success", "succeeded"])
    failed = _find_metric(numbers, ["failed_cases", "failed", "failures", "error"])
    blocked = _find_metric(numbers, ["blocked_cases", "blocked", "blockers"])
    critical = _find_metric(numbers, ["critical_bugs", "p0_bugs", "p1_bugs", "critical"])
    explicit_progress = _find_metric(numbers, ["progress_pct", "progress", "completion_rate", "complete_rate"])

    progress = None
    if total and executed is not None and total > 0:
        progress = round(executed / total * 100)
    elif explicit_progress is not None:
        progress = round(explicit_progress * 100) if explicit_progress <= 1 else round(explicit_progress)
    progress = max(0, min(100, progress)) if progress is not None else None

    signoff_allowed = (
        progress == 100
        and (failed is None or failed == 0)
        and (blocked is None or blocked == 0)
        and (critical is None or critical == 0)
    )
    metrics = {
        "total": total,
        "executed": executed,
        "passed": passed,
        "failed": failed,
        "blocked": blocked,
        "critical_bugs": critical,
        "suggested_progress_pct": progress,
        "signoff_allowed": signoff_allowed,
    }
    return {key: value for key, value in metrics.items() if value is not None}


def _rule_note(metrics: dict, skill: TaskDataSkill) -> str:
    parts = []
    if "total" in metrics and "executed" in metrics:
        parts.append(f"外部数据执行 {int(metrics['executed'])}/{int(metrics['total'])}")
    if metrics.get("failed"):
        parts.append(f"失败 {int(metrics['failed'])}")
    if metrics.get("blocked"):
        parts.append(f"阻塞 {int(metrics['blocked'])}")
    if metrics.get("critical_bugs"):
        parts.append(f"严重缺陷 {int(metrics['critical_bugs'])}")
    if not parts:
        parts.append("已采集外部平台数据")
    return "；".join(parts)


async def _analyze_response_with_ai(
    llm: LLMClient,
    skill: TaskDataSkill,
    task: Task,
    response_data: Any,
    metrics: dict,
) -> dict:
    messages = [
        {
            "role": "system",
            "content": (
                "你是任务数据验证分析器。根据任务、Skill 说明、接口返回和规则指标，"
                "输出进度建议、风险和是否建议会签。只返回 JSON，不要 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": {
                        "title": task.title,
                        "goal": task.goal,
                        "description": task.description,
                    },
                    "natural_language": skill.natural_language,
                    "skill_json": skill.skill_json,
                    "response_data": response_data,
                    "rule_metrics": metrics,
                    "expected_schema": {
                        "suggested_progress_pct": 80,
                        "suggested_note": "简短进展说明",
                        "risk_summary": "风险说明",
                        "signoff_allowed": False,
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]
    result = await llm.chat_json(messages, max_tokens=1200, temperature=0.1)
    return result if isinstance(result, dict) else {}


async def run_task_data_skill(
    db: AsyncSession,
    skill_id: uuid.UUID,
    user_id: uuid.UUID,
    provided_params: dict | None = None,
    llm: LLMClient | None = None,
) -> SkillRun:
    skill = await get_task_data_skill(db, skill_id)
    if not skill:
        raise ValueError("Task data Skill not found.")
    task = await task_service.get_task(db, skill.task_id)
    if not task:
        raise ValueError("Task not found.")
    if task.is_deleted:
        raise ValueError("Deleted tasks cannot run data Skill.")
    connector = await get_connector(db, skill.connector_id) if skill.connector_id else None
    if not connector or not connector.is_enabled:
        raise ValueError("Data connector is not configured or disabled.")

    params, missing = _resolve_params(skill, task, provided_params or {})
    if missing:
        raise ValueError("Missing required params: " + ", ".join(missing))

    skill_json = skill.skill_json or {}
    method = (skill_json.get("method") or "GET").upper()
    path = _render_path(skill_json.get("path") or "", params)
    if not path.startswith("/"):
        path = "/" + path
    url = connector.base_url.rstrip("/") + path
    headers = dict(connector.headers_json or {})
    query_params = dict(skill_json.get("query") or {})
    body = skill_json.get("body") if method != "GET" else None
    request_snapshot = {
        "method": method,
        "url": url,
        "params": params,
        "query": query_params,
        "headers": sorted(headers.keys()),
        "auth_type": connector.auth_type.value,
    }

    try:
        auth = await _apply_auth(connector, headers, query_params)
        request_snapshot["query"] = query_params
        request_snapshot["headers"] = sorted(headers.keys())
        async with httpx.AsyncClient(timeout=connector.timeout_seconds, verify=connector.verify_tls) as client:
            response = await client.request(
                method,
                url,
                params=query_params or None,
                headers=headers or None,
                json=body,
                auth=auth,
            )
        response_text = response.text
        try:
            response_data = response.json()
        except ValueError:
            response_data = {"raw_text": response_text}
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {response.status_code}",
                request=response.request,
                response=response,
            )

        metrics = infer_metrics(response_data)
        ai_analysis = {}
        if llm:
            try:
                ai_analysis = await _analyze_response_with_ai(llm, skill, task, response_data, metrics)
            except Exception as exc:
                ai_analysis = {"error": str(exc)}

        suggested_progress = ai_analysis.get("suggested_progress_pct") or metrics.get("suggested_progress_pct")
        suggested_progress = int(suggested_progress) if suggested_progress is not None else None
        suggested_note = ai_analysis.get("suggested_note") or _rule_note(metrics, skill)
        run = SkillRun(
            task_data_skill_id=skill.id,
            task_id=task.id,
            actor_id=user_id,
            status=SkillRunStatus.SUCCESS,
            request_json=request_snapshot,
            response_json={"status_code": response.status_code, "data": response_data},
            metrics_json=metrics,
            ai_analysis_json=ai_analysis,
            suggested_progress_pct=suggested_progress,
            suggested_note=suggested_note,
        )
    except Exception as exc:
        response_payload = {}
        if isinstance(exc, httpx.HTTPStatusError):
            try:
                response_payload = {
                    "status_code": exc.response.status_code,
                    "data": exc.response.json(),
                }
            except ValueError:
                response_payload = {
                    "status_code": exc.response.status_code,
                    "data": {"raw_text": exc.response.text[:2000]},
                }
        run = SkillRun(
            task_data_skill_id=skill.id,
            task_id=task.id,
            actor_id=user_id,
            status=SkillRunStatus.FAILED,
            request_json=request_snapshot,
            response_json=response_payload,
            metrics_json={},
            ai_analysis_json={},
            error_message=f"{type(exc).__name__}: {exc}",
        )

    db.add(run)
    await db.flush()
    await db.refresh(run)
    return run


async def list_skill_runs(db: AsyncSession, task_id: uuid.UUID) -> list[SkillRun]:
    rows = await db.execute(
        select(SkillRun)
        .where(SkillRun.task_id == task_id)
        .order_by(SkillRun.created_at.desc())
    )
    return rows.scalars().all()


async def get_skill_run(db: AsyncSession, run_id: uuid.UUID) -> SkillRun | None:
    return (
        await db.execute(select(SkillRun).where(SkillRun.id == run_id))
    ).scalar_one_or_none()


async def adopt_skill_run(
    db: AsyncSession,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    progress_pct: int | None = None,
    note: str | None = None,
    hours_spent: float | None = None,
):
    run = await get_skill_run(db, run_id)
    if not run:
        raise ValueError("Skill run not found.")
    if run.status != SkillRunStatus.SUCCESS:
        raise ValueError("Only successful Skill runs can be adopted.")
    progress = progress_pct if progress_pct is not None else run.suggested_progress_pct
    if progress is None:
        raise ValueError("Skill run has no suggested progress.")
    final_note = note or run.suggested_note or "采纳外部数据 Skill 执行结果"
    final_note = f"数据 Skill：{final_note}"
    return await task_service.log_progress(
        db,
        run.task_id,
        user_id,
        int(progress),
        final_note,
        hours_spent,
    )


def task_data_skill_to_out(skill: TaskDataSkill) -> dict:
    connector = skill.__dict__.get("connector")
    return {
        **{c.name: getattr(skill, c.name) for c in skill.__table__.columns},
        "connector_name": connector.name if connector else None,
    }
