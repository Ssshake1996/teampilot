from typing import Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.report_service import (
    format_report_text,
    generate_weekly_report,
    get_report_snapshot,
    parse_recipients,
    refresh_report_snapshot,
    report_subject,
    send_report_email,
    report_history,
    report_history_item,
    _scope_allowed,
)

router = APIRouter(prefix="/reports", tags=["reports"])


class SendReportRequest(BaseModel):
    report_type: Literal["daily", "weekly"] = "daily"
    recipients: list[str] = []
    subject: str | None = None
    report: dict | None = None
    history_id: uuid.UUID | None = None


class ReportSnapshotRequest(BaseModel):
    report_type: Literal["daily", "weekly"] = "daily"


@router.get("/snapshot")
async def report_snapshot(
    report_type: Literal["daily", "weekly"] = "daily",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_report_snapshot(db, report_type, user=current_user)


@router.post("/refresh")
async def refresh_report(
    data: ReportSnapshotRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await refresh_report_snapshot(db, data.report_type, trigger="manual", user=current_user)


@router.get("/weekly")
async def weekly_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.project_access_service import get_visible_project_ids
    return await generate_weekly_report(db, project_ids=await get_visible_project_ids(db, current_user))


@router.get("/history")
async def history(report_type: Literal["daily", "weekly"] = "weekly", db: AsyncSession = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    return await report_history(db, report_type, current_user)


@router.get("/history/{version_id}")
async def history_item(version_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    item = await report_history_item(db, version_id, current_user)
    if item is None:
        raise HTTPException(404, "Report version not found or no longer accessible")
    return item


@router.post("/send")
async def send_report(
    data: SendReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = data.report if current_user.role == "admin" and not data.history_id else None
    if data.history_id:
        version = await report_history_item(db, data.history_id, current_user)
        if not version:
            raise HTTPException(404, "Report version not found or no longer accessible")
        if version["report_type"] != data.report_type:
            raise HTTPException(400, "Report version type does not match the request")
        report = version["report"]
    elif not report:
        if data.report_type == "weekly":
            snapshot = await get_report_snapshot(db, "weekly", user=current_user)
        else:
            snapshot = await get_report_snapshot(db, "daily", user=current_user)
        report = snapshot.get("report")
    if not report:
        raise HTTPException(status_code=400, detail="No cached report. Refresh the report first.")
    if current_user.role != "admin" and data.report is not None and data.report != report:
        raise HTTPException(status_code=403, detail="Only your current server report or an accessible history version may be sent")
    if not await _scope_allowed(db, report, current_user):
        raise HTTPException(status_code=403, detail="Report is outside your current project access")

    recipients = parse_recipients(data.recipients)
    subject = data.subject or report_subject(data.report_type, report)
    body = format_report_text(data.report_type, report)

    try:
        send_report_email(recipients, subject, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Email send failed: {type(exc).__name__}: {exc}",
        ) from exc

    return {
        "message": "Report sent",
        "report_type": data.report_type,
        "recipients": recipients,
        "subject": subject,
    }
