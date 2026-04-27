import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.schemas.data_skill import (
    DataConnectorCreate,
    DataConnectorOut,
    DataConnectorUpdate,
    SkillRunAdoptRequest,
    SkillRunOut,
    SkillRunRequest,
    TaskDataSkillGenerateRequest,
    TaskDataSkillOut,
    TaskDataSkillUpdate,
)
from app.services import data_skill_service
from app.services.ai.llm_client import LLMClient
from app.websocket.events import emit_progress_event

router = APIRouter(tags=["Data Skills"])

AI_CONFIG_KEY = "ai_config"


async def _get_optional_llm(db: AsyncSession) -> LLMClient | None:
    setting = (
        await db.execute(select(SystemSetting).where(SystemSetting.key == AI_CONFIG_KEY))
    ).scalar_one_or_none()
    config = setting.value_json if setting else {}
    if not config.get("api_key_encrypted") or not config.get("api_base_url") or not config.get("model_name"):
        return None
    return LLMClient(
        base_url=config.get("api_base_url") or "",
        api_key=config["api_key_encrypted"],
        model=config.get("model_name") or "",
        max_tokens=int(config.get("max_tokens") or 2048),
        temperature=float(config.get("temperature") or 0.7),
    )


@router.get("/data-connectors", response_model=list[DataConnectorOut])
async def list_connectors(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("ai.config")),
):
    return await data_skill_service.list_connectors(db)


@router.post("/data-connectors", response_model=DataConnectorOut, status_code=201)
async def create_connector(
    data: DataConnectorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("ai.config")),
):
    return await data_skill_service.create_connector(db, data)


@router.patch("/data-connectors/{connector_id}", response_model=DataConnectorOut)
async def update_connector(
    connector_id: uuid.UUID,
    data: DataConnectorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("ai.config")),
):
    connector = await data_skill_service.update_connector(db, connector_id, data)
    if not connector:
        raise HTTPException(status_code=404, detail="Data connector not found")
    return connector


@router.delete("/data-connectors/{connector_id}")
async def delete_connector(
    connector_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("ai.config")),
):
    ok = await data_skill_service.delete_connector(db, connector_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Data connector not found")
    return {"message": "Data connector deleted"}


@router.get("/tasks/{task_id}/data-skills", response_model=list[TaskDataSkillOut])
async def list_task_data_skills(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    skills = await data_skill_service.list_task_data_skills(db, task_id)
    return [data_skill_service.task_data_skill_to_out(item) for item in skills]


@router.post("/tasks/{task_id}/data-skills/generate", response_model=TaskDataSkillOut, status_code=201)
async def generate_task_data_skill(
    task_id: uuid.UUID,
    data: TaskDataSkillGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("progress.submit")),
):
    llm = await _get_optional_llm(db)
    try:
        skill = await data_skill_service.generate_task_data_skill(
            db,
            task_id,
            data.natural_language,
            current_user.id,
            data.connector_id,
            llm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        if llm:
            await llm.close()
    return data_skill_service.task_data_skill_to_out(skill)


@router.patch("/tasks/{task_id}/data-skills/{skill_id}", response_model=TaskDataSkillOut)
async def update_task_data_skill(
    task_id: uuid.UUID,
    skill_id: uuid.UUID,
    data: TaskDataSkillUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("progress.submit")),
):
    skill = await data_skill_service.update_task_data_skill(db, skill_id, data)
    if not skill or skill.task_id != task_id:
        raise HTTPException(status_code=404, detail="Task data Skill not found")
    return data_skill_service.task_data_skill_to_out(skill)


@router.post("/tasks/{task_id}/data-skills/{skill_id}/confirm", response_model=TaskDataSkillOut)
async def confirm_task_data_skill(
    task_id: uuid.UUID,
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("progress.submit")),
):
    skill = await data_skill_service.confirm_task_data_skill(db, skill_id, current_user.id)
    if not skill or skill.task_id != task_id:
        raise HTTPException(status_code=404, detail="Task data Skill not found")
    return data_skill_service.task_data_skill_to_out(skill)


@router.post("/tasks/{task_id}/data-skills/{skill_id}/run", response_model=SkillRunOut, status_code=201)
async def run_task_data_skill(
    task_id: uuid.UUID,
    skill_id: uuid.UUID,
    data: SkillRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("progress.submit")),
):
    llm = await _get_optional_llm(db) if data.use_ai else None
    try:
        run = await data_skill_service.run_task_data_skill(
            db,
            skill_id,
            current_user.id,
            data.params,
            llm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        if llm:
            await llm.close()
    if run.task_id != task_id:
        raise HTTPException(status_code=404, detail="Task data Skill not found")
    return run


@router.get("/tasks/{task_id}/data-skills/runs", response_model=list[SkillRunOut])
async def list_skill_runs(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await data_skill_service.list_skill_runs(db, task_id)


@router.post("/tasks/{task_id}/data-skills/runs/{run_id}/adopt")
async def adopt_skill_run(
    task_id: uuid.UUID,
    run_id: uuid.UUID,
    data: SkillRunAdoptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("progress.submit")),
):
    try:
        event = await data_skill_service.adopt_skill_run(
            db,
            run_id,
            current_user.id,
            data.progress_pct,
            data.note,
            data.hours_spent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if event.task_id != task_id:
        raise HTTPException(status_code=404, detail="Skill run not found")
    await emit_progress_event({"task_id": str(task_id), "progress_pct": event.progress_pct})
    return {
        "id": event.id,
        "task_id": event.task_id,
        "user_id": event.actor_id,
        "user_name": current_user.full_name,
        "progress_pct": event.progress_pct,
        "note": event.note,
        "hours_spent": float(event.hours_spent) if event.hours_spent else None,
        "created_at": event.created_at,
    }
