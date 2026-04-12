import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.capability_profile import AIConfig
from app.models.user import User
from app.services.ai.llm_client import LLMClient
from app.services.ai.task_assignment import recommend_assignee
from app.services.ai.capability_analysis import analyze_capability
from app.services.ai.risk_analysis import analyze_project_risk
from app.services.ai.task_decompose import decompose_task

router = APIRouter(prefix="/ai", tags=["AI"])


class RecommendRequest(BaseModel):
    task_id: uuid.UUID


class AnalyzeRequest(BaseModel):
    user_id: uuid.UUID


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


async def _get_llm(db: AsyncSession) -> LLMClient:
    result = await db.execute(select(AIConfig).where(AIConfig.id == 1))
    config = result.scalar_one_or_none()
    if not config or not config.api_key_encrypted:
        raise HTTPException(status_code=503, detail="AI service not configured")
    return LLMClient(
        base_url=config.api_base_url,
        api_key=config.api_key_encrypted,  # simplified: storing plain for MVP
        model=config.model_name,
        max_tokens=config.max_tokens,
        temperature=float(config.temperature),
    )


@router.post("/recommend-assignee")
async def recommend(
    data: RecommendRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    llm = await _get_llm(db)
    try:
        result = await recommend_assignee(db, data.task_id, llm)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")
    finally:
        await llm.close()


@router.post("/analyze-capability")
async def analyze(
    data: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    llm = await _get_llm(db)
    try:
        result = await analyze_capability(db, data.user_id, llm)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")
    finally:
        await llm.close()


class RiskRequest(BaseModel):
    project_id: uuid.UUID


class DecomposeRequest(BaseModel):
    task_id: uuid.UUID


@router.post("/analyze-risk")
async def risk_analysis(
    data: RiskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    llm = await _get_llm(db)
    try:
        result = await analyze_project_risk(db, data.project_id, llm)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")
    finally:
        await llm.close()


@router.post("/decompose-task")
async def task_decomposition(
    data: DecomposeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    llm = await _get_llm(db)
    try:
        result = await decompose_task(db, data.task_id, llm)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")
    finally:
        await llm.close()


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
        if data.api_key:  # Only update key if provided (non-empty)
            config.api_key_encrypted = data.api_key
        config.model_name = data.model_name
        config.max_tokens = data.max_tokens
        config.temperature = Decimal(str(data.temperature))
    else:
        if not data.api_key:
            raise HTTPException(status_code=400, detail="API Key is required for initial setup")
        config = AIConfig(
            id=1,
            api_base_url=data.api_base_url,
            api_key_encrypted=data.api_key,
            model_name=data.model_name,
            max_tokens=data.max_tokens,
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
