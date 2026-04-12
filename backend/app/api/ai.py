import json
import uuid
import traceback
from decimal import Decimal
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.dependencies import get_current_user, require_admin
from app.models.capability_profile import AIConfig
from app.models.user import User
from app.services.ai.llm_client import LLMClient
from app.services.ai.task_assignment import recommend_assignee
from app.services.ai.capability_analysis import analyze_capability
from app.services.ai.risk_analysis import analyze_project_risk
from app.services.ai.task_decompose import decompose_task
from app.services.ai.task_estimate import estimate_task

router = APIRouter(prefix="/ai", tags=["AI"])


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


async def _get_llm_from_db() -> LLMClient:
    """Get LLM client using a fresh db session (for use inside generators)."""
    async with async_session() as db:
        result = await db.execute(select(AIConfig).where(AIConfig.id == 1))
        config = result.scalar_one_or_none()
        if not config or not config.api_key_encrypted:
            raise ValueError("AI service not configured")
        return LLMClient(
            base_url=config.api_base_url,
            api_key=config.api_key_encrypted,
            model=config.model_name,
            max_tokens=config.max_tokens,
            temperature=float(config.temperature),
        )


async def _get_llm(db: AsyncSession) -> LLMClient:
    result = await db.execute(select(AIConfig).where(AIConfig.id == 1))
    config = result.scalar_one_or_none()
    if not config or not config.api_key_encrypted:
        raise HTTPException(status_code=503, detail="AI service not configured")
    return LLMClient(
        base_url=config.api_base_url,
        api_key=config.api_key_encrypted,
        model=config.model_name,
        max_tokens=config.max_tokens,
        temperature=float(config.temperature),
    )


# ── SSE AI Endpoints ──

@router.post("/estimate-task")
async def task_estimation(
    data: EstimateRequest,
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
):
    async def generate() -> AsyncGenerator[str, None]:
        llm = None
        try:
            yield sse_status("正在加载 AI 配置...")
            llm = await _get_llm_from_db()

            yield sse_status("正在采集项目进度和团队负载数据...")
            yield sse_status("正在进行 AI 风险评估...")
            async with async_session() as db:
                result = await analyze_project_risk(db, data.project_id, llm)

            yield sse_status("风险分析完成")
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
    current_user: User = Depends(get_current_user),
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


# ── Non-streaming endpoints (config, test) ──

@router.get("/config", response_model=AIConfigOut)
async def get_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(AIConfig).where(AIConfig.id == 1))
    config = result.scalar_one_or_none()
    if not config:
        return {"api_base_url": "", "api_key_masked": "", "model_name": "", "max_tokens": 2048, "temperature": 0.7}
    key = config.api_key_encrypted
    masked = key[:8] + "****" + key[-4:] if len(key) > 12 else "****"
    return {
        "api_base_url": config.api_base_url,
        "api_key_masked": masked,
        "model_name": config.model_name,
        "max_tokens": config.max_tokens,
        "temperature": float(config.temperature),
    }


@router.put("/config")
async def update_config(
    data: AIConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(AIConfig).where(AIConfig.id == 1))
    config = result.scalar_one_or_none()
    if config:
        config.api_base_url = data.api_base_url
        if data.api_key:
            config.api_key_encrypted = data.api_key
        config.model_name = data.model_name
        config.max_tokens = data.max_tokens
        config.temperature = Decimal(str(data.temperature))
    else:
        if not data.api_key:
            raise HTTPException(status_code=400, detail="API Key is required for initial setup")
        config = AIConfig(
            id=1, api_base_url=data.api_base_url, api_key_encrypted=data.api_key,
            model_name=data.model_name, max_tokens=data.max_tokens,
            temperature=Decimal(str(data.temperature)),
        )
        db.add(config)
    await db.flush()
    return {"message": "AI config updated"}


@router.post("/test-connection")
async def test_connection(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    llm = await _get_llm(db)
    try:
        ok = await llm.test_connection()
        return {"success": ok, "message": "Connection successful" if ok else "Connection failed"}
    finally:
        await llm.close()
