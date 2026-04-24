import json
import uuid
import traceback
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.dependencies import get_current_user, require_permission
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services.ai.llm_client import LLMClient
from app.services.ai.task_assignment import recommend_assignee
from app.services.ai.capability_analysis import analyze_capability
from app.services.ai.risk_analysis import analyze_project_risk
from app.services.ai.task_decompose import decompose_task
from app.services.ai.task_estimate import estimate_task
from app.services.ai.progress_import import parse_progress_updates
from app.services.ai.project_automation import (
    commit_project_plan,
    daily_brief,
    preview_project_plan,
    project_retrospective,
    signoff_assistant,
)
from app.services import task_service
from app.websocket.events import emit_progress_event

router = APIRouter(prefix="/ai", tags=["AI"])

AI_CONFIG_KEY = "ai_config"
AI_CONFIG_DEFAULT = {
    "api_base_url": "",
    "api_key_encrypted": "",
    "model_name": "",
    "max_tokens": 2048,
    "temperature": 0.7,
    "prompt_task_assign": None,
    "prompt_capability": None,
    "prompt_risk": None,
    "prompt_estimate": None,
    "prompt_decompose": None,
}


# ── Request Models ──

class RecommendRequest(BaseModel):
    task_id: uuid.UUID

class AnalyzeRequest(BaseModel):
    user_id: uuid.UUID

class RiskRequest(BaseModel):
    project_id: uuid.UUID

class DecomposeRequest(BaseModel):
    task_id: uuid.UUID

class EstimateRequest(BaseModel):
    project_id: uuid.UUID
    title: str
    description: str = ""

class ProgressImportRequest(BaseModel):
    project_id: uuid.UUID | None = None
    text: str

class ProgressImportCommitItem(BaseModel):
    task_id: uuid.UUID
    progress_pct: int
    note: str = ""
    person_name: str = ""
    reported_at: str = ""
    hours_spent: float | None = None

class ProgressImportCommitRequest(BaseModel):
    updates: list[ProgressImportCommitItem]

class ProjectPlanPreviewRequest(BaseModel):
    prompt: str

class ProjectPlanCommitRequest(BaseModel):
    plan: dict

class SignoffAssistRequest(BaseModel):
    task_id: uuid.UUID

class RetrospectiveRequest(BaseModel):
    project_id: uuid.UUID

class AIConfigUpdate(BaseModel):
    api_base_url: str
    api_key: str
    model_name: str
    max_tokens: int = 2048
    temperature: float = 0.7

class AIConfigOut(BaseModel):
    api_base_url: str
    api_key_masked: str
    model_name: str
    max_tokens: int
    temperature: float


# ── SSE Helpers ──

def sse_event(event: str, data: dict | str) -> str:
    """Format a Server-Sent Event."""
    payload = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else data
    return f"event: {event}\ndata: {payload}\n\n"


def sse_status(message: str) -> str:
    """Send a status update to the frontend."""
    return sse_event("status", {"message": message})


def sse_result(data: dict) -> str:
    """Send the final result."""
    return sse_event("result", data)


def sse_error(message: str) -> str:
    """Send an error."""
    return sse_event("error", {"message": message})


async def _get_config_dict(db: AsyncSession) -> dict:
    setting = (
        await db.execute(select(SystemSetting).where(SystemSetting.key == AI_CONFIG_KEY))
    ).scalar_one_or_none()
    if not setting:
        return AI_CONFIG_DEFAULT.copy()
    return {**AI_CONFIG_DEFAULT, **(setting.value_json or {})}


async def _save_config_dict(db: AsyncSession, payload: dict) -> None:
    setting = (
        await db.execute(select(SystemSetting).where(SystemSetting.key == AI_CONFIG_KEY))
    ).scalar_one_or_none()
    if setting:
        setting.value_json = payload
    else:
        db.add(SystemSetting(key=AI_CONFIG_KEY, value_json=payload))
    await db.flush()


async def _get_llm_from_db() -> LLMClient:
    """Get LLM client using a fresh db session (for use inside generators)."""
    async with async_session() as db:
        config = await _get_config_dict(db)
        if not config.get("api_key_encrypted"):
            raise ValueError("AI service not configured")
        return LLMClient(
            base_url=config.get("api_base_url") or "",
            api_key=config["api_key_encrypted"],
            model=config.get("model_name") or "",
            max_tokens=int(config.get("max_tokens") or 2048),
            temperature=float(config.get("temperature") or 0.7),
        )


async def _get_llm(db: AsyncSession) -> LLMClient:
    config = await _get_config_dict(db)
    if not config.get("api_key_encrypted"):
        raise HTTPException(status_code=503, detail="AI service not configured")
    return LLMClient(
        base_url=config.get("api_base_url") or "",
        api_key=config["api_key_encrypted"],
        model=config.get("model_name") or "",
        max_tokens=int(config.get("max_tokens") or 2048),
        temperature=float(config.get("temperature") or 0.7),
    )


# ── SSE AI Endpoints ──

@router.post("/estimate-task")
async def task_estimation(
    data: EstimateRequest,
    current_user: User = Depends(require_permission("ai.estimate")),
):
    async def generate() -> AsyncGenerator[str, None]:
        llm = None
        try:
            yield sse_status("正在加载 AI 配置...")
            llm = await _get_llm_from_db()

            yield sse_status("正在分析团队成员技能和工作负载...")
            async with async_session() as db:
                result = await estimate_task(db, data.project_id, data.title, data.description, llm)

            yield sse_status("分析完成")
            yield sse_result(result)
        except Exception as e:
            traceback.print_exc()
            yield sse_error(f"{type(e).__name__}: {str(e)}")
        finally:
            if llm:
                await llm.close()

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/recommend-assignee")
async def recommend(
    data: RecommendRequest,
    current_user: User = Depends(require_permission("ai.estimate")),
):
    async def generate() -> AsyncGenerator[str, None]:
        llm = None
        try:
            yield sse_status("正在加载 AI 配置...")
            llm = await _get_llm_from_db()

            yield sse_status("正在分析任务需求和候选人能力...")
            async with async_session() as db:
                result = await recommend_assignee(db, data.task_id, llm)

            yield sse_status("推荐完成")
            yield sse_result(result)
        except Exception as e:
            traceback.print_exc()
            yield sse_error(str(e))
        finally:
            if llm:
                await llm.close()

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/analyze-capability")
async def analyze(
    data: AnalyzeRequest,
    current_user: User = Depends(require_permission("ai.capability")),
):
    async def generate() -> AsyncGenerator[str, None]:
        llm = None
        try:
            yield sse_status("正在加载 AI 配置...")
            llm = await _get_llm_from_db()

            yield sse_status("正在收集技能和历史绩效数据...")
            yield sse_status("正在进行 AI 能力分析...")
            async with async_session() as db:
                result = await analyze_capability(db, data.user_id, llm)

            yield sse_status("分析完成")
            yield sse_result(result)
        except Exception as e:
            traceback.print_exc()
            yield sse_error(str(e))
        finally:
            if llm:
                await llm.close()

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/analyze-risk")
async def risk_analysis(
    data: RiskRequest,
    current_user: User = Depends(require_permission("ai.risk")),
):
    async def generate() -> AsyncGenerator[str, None]:
        llm = None
        try:
            yield sse_status("正在加载 AI 配置...")
            llm = await _get_llm_from_db()

            yield sse_status("正在采集项目进度和团队负载数据...")
            yield sse_status("正在进行 AI 项目分析...")
            async with async_session() as db:
                result = await analyze_project_risk(db, data.project_id, llm)

            yield sse_status("项目分析完成")
            yield sse_result(result)
        except Exception as e:
            traceback.print_exc()
            yield sse_error(str(e))
        finally:
            if llm:
                await llm.close()

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/decompose-task")
async def task_decomposition(
    data: DecomposeRequest,
    current_user: User = Depends(require_permission("ai.estimate")),
):
    async def generate() -> AsyncGenerator[str, None]:
        llm = None
        try:
            yield sse_status("正在加载 AI 配置...")
            llm = await _get_llm_from_db()

            yield sse_status("正在分析任务结构和团队能力...")
            yield sse_status("正在生成子任务拆解方案...")
            async with async_session() as db:
                result = await decompose_task(db, data.task_id, llm)

            yield sse_status("拆解完成")
            yield sse_result(result)
        except Exception as e:
            traceback.print_exc()
            yield sse_error(str(e))
        finally:
            if llm:
                await llm.close()

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/progress-import/preview")
async def progress_import_preview(
    data: ProgressImportRequest,
    current_user: User = Depends(require_permission("progress.submit")),
):
    async def generate() -> AsyncGenerator[str, None]:
        llm = None
        try:
            yield sse_status("正在加载 AI 配置...")
            llm = await _get_llm_from_db()
            yield sse_status("正在读取项目任务并识别群消息...")
            async with async_session() as db:
                result = await parse_progress_updates(db, data.text, llm, data.project_id)
            yield sse_status("识别完成")
            yield sse_result(result)
        except Exception as e:
            traceback.print_exc()
            yield sse_error(f"{type(e).__name__}: {str(e)}")
        finally:
            if llm:
                await llm.close()

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/progress-import/commit")
async def progress_import_commit(
    data: ProgressImportCommitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("progress.submit")),
):
    saved = []
    for item in data.updates:
        note_parts = []
        if item.person_name or item.reported_at:
            note_parts.append(f"群消息：{item.person_name} {item.reported_at}".strip())
        if item.note:
            note_parts.append(item.note)
        note = "\n".join(note_parts)
        try:
            await task_service.log_progress(
                db,
                item.task_id,
                current_user.id,
                item.progress_pct,
                note,
                item.hours_spent,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        task = await task_service.get_task(db, item.task_id)
        if task:
            saved.append(await task_service.task_to_out(db, task))
        await emit_progress_event({"task_id": str(item.task_id), "progress_pct": item.progress_pct})
    return {"saved": saved, "count": len(saved)}


@router.post("/project-plan/preview")
async def project_plan_preview(
    data: ProjectPlanPreviewRequest,
    current_user: User = Depends(require_permission("ai.estimate")),
):
    async def generate() -> AsyncGenerator[str, None]:
        llm = None
        try:
            yield sse_status("正在加载 AI 配置...")
            llm = await _get_llm_from_db()
            yield sse_status("正在生成项目计划和任务树...")
            async with async_session() as db:
                result = await preview_project_plan(db, data.prompt, llm)
            yield sse_status("计划生成完成")
            yield sse_result(result)
        except Exception as e:
            traceback.print_exc()
            yield sse_error(f"{type(e).__name__}: {str(e)}")
        finally:
            if llm:
                await llm.close()

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/project-plan/commit")
async def project_plan_commit(
    data: ProjectPlanCommitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("project.create")),
):
    return await commit_project_plan(db, data.plan, current_user.id)


@router.post("/daily-brief")
async def daily_briefing(
    current_user: User = Depends(get_current_user),
):
    async def generate() -> AsyncGenerator[str, None]:
        llm = None
        try:
            yield sse_status("正在加载 AI 配置...")
            try:
                llm = await _get_llm_from_db()
                yield sse_status("正在汇总项目、任务和进展数据...")
                yield sse_status("正在调用 AI 生成每日巡检报告...")
            except Exception:
                yield sse_status("AI 配置不可用，正在使用系统规则生成每日巡检报告...")
            async with async_session() as db:
                result = await daily_brief(db, llm)
            yield sse_status("每日巡检报告已生成")
            yield sse_result(result)
        except Exception as e:
            traceback.print_exc()
            yield sse_error(f"{type(e).__name__}: {str(e)}")
        finally:
            if llm:
                await llm.close()

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/signoff-assist")
async def signoff_assist(
    data: SignoffAssistRequest,
    current_user: User = Depends(require_permission("ai.risk")),
):
    async def generate() -> AsyncGenerator[str, None]:
        llm = None
        try:
            yield sse_status("正在加载 AI 配置...")
            llm = await _get_llm_from_db()
            yield sse_status("正在检查任务进展、子任务和风险...")
            async with async_session() as db:
                result = await signoff_assistant(db, data.task_id, llm)
            yield sse_status("会签建议生成完成")
            yield sse_result(result)
        except Exception as e:
            traceback.print_exc()
            yield sse_error(f"{type(e).__name__}: {str(e)}")
        finally:
            if llm:
                await llm.close()

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/project-retrospective")
async def retrospective(
    data: RetrospectiveRequest,
    current_user: User = Depends(require_permission("ai.risk")),
):
    async def generate() -> AsyncGenerator[str, None]:
        llm = None
        try:
            yield sse_status("正在加载 AI 配置...")
            llm = await _get_llm_from_db()
            yield sse_status("正在整理任务树和进展历史...")
            async with async_session() as db:
                result = await project_retrospective(db, data.project_id, llm)
            yield sse_status("项目复盘生成完成")
            yield sse_result(result)
        except Exception as e:
            traceback.print_exc()
            yield sse_error(f"{type(e).__name__}: {str(e)}")
        finally:
            if llm:
                await llm.close()

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Non-streaming endpoints (config, test) ──

@router.get("/config", response_model=AIConfigOut)
async def get_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("ai.config")),
):
    config = await _get_config_dict(db)
    if not config.get("api_base_url") and not config.get("model_name") and not config.get("api_key_encrypted"):
        return {"api_base_url": "", "api_key_masked": "", "model_name": "", "max_tokens": 2048, "temperature": 0.7}
    key = config.get("api_key_encrypted") or ""
    masked = key[:8] + "****" + key[-4:] if len(key) > 12 else "****"
    return {
        "api_base_url": config.get("api_base_url") or "",
        "api_key_masked": masked,
        "model_name": config.get("model_name") or "",
        "max_tokens": int(config.get("max_tokens") or 2048),
        "temperature": float(config.get("temperature") or 0.7),
    }


@router.put("/config")
async def update_config(
    data: AIConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("ai.config")),
):
    config = await _get_config_dict(db)
    if data.api_key:
        config["api_key_encrypted"] = data.api_key
    elif not config.get("api_key_encrypted"):
        raise HTTPException(status_code=400, detail="API Key is required for initial setup")
    config.update({
        "api_base_url": data.api_base_url,
        "model_name": data.model_name,
        "max_tokens": data.max_tokens,
        "temperature": data.temperature,
    })
    await _save_config_dict(db, config)
    return {"message": "AI config updated"}


@router.post("/test-connection")
async def test_connection(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("ai.config")),
):
    llm = await _get_llm(db)
    try:
        return await llm.test_connection()
    finally:
        await llm.close()


# ── Prompt Configuration (admin only) ──

PROMPT_FIELDS = ["prompt_task_assign", "prompt_capability", "prompt_risk", "prompt_estimate", "prompt_decompose"]
PROMPT_LABELS = {
    "prompt_task_assign": "任务分配推荐",
    "prompt_capability": "能力分析",
    "prompt_risk": "项目分析",
    "prompt_estimate": "工时预估与人选推荐",
    "prompt_decompose": "任务拆解",
}


@router.get("/prompts")
async def get_prompts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("ai.prompt")),
):
    """Get all custom system prompts. Returns defaults from prompts.py if not customized."""
    from app.services.ai import prompts as default_prompts

    config = await _get_config_dict(db)

    defaults = {
        "prompt_task_assign": default_prompts.TASK_ASSIGNMENT_SYSTEM,
        "prompt_capability": default_prompts.CAPABILITY_ANALYSIS_SYSTEM,
        "prompt_risk": default_prompts.RISK_ANALYSIS_SYSTEM,
        "prompt_estimate": default_prompts.TASK_ESTIMATE_SYSTEM,
        "prompt_decompose": default_prompts.TASK_DECOMPOSE_SYSTEM,
    }

    items = []
    for field in PROMPT_FIELDS:
        custom = config.get(field)
        items.append({
            "key": field,
            "label": PROMPT_LABELS[field],
            "value": custom or "",
            "default": defaults[field],
            "is_custom": bool(custom),
        })
    return items


class PromptUpdate(BaseModel):
    key: str
    value: str


@router.put("/prompts")
async def update_prompt(
    data: PromptUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("ai.prompt")),
):
    if data.key not in PROMPT_FIELDS:
        raise HTTPException(status_code=400, detail=f"Invalid prompt key: {data.key}")

    config = await _get_config_dict(db)
    config[data.key] = data.value.strip() or None
    await _save_config_dict(db, config)
    return {"message": f"Prompt '{PROMPT_LABELS[data.key]}' updated"}
