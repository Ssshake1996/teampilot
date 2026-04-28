from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.ai.errors import AIBackendError
from app.services.report_service import (
    format_report_text,
    generate_weekly_report,
    get_report_snapshot,
    parse_recipients,
    refresh_report_snapshot,
    report_subject,
    send_report_email,
)

router = APIRouter(prefix="/reports", tags=["reports"])


class SendReportRequest(BaseModel):
    report_type: Literal["daily", "weekly"] = "daily"
    recipients: list[str] = []
    subject: str | None = None
    report: dict | None = None


class ReportSnapshotRequest(BaseModel):
    report_type: Literal["daily", "weekly"] = "daily"


@router.get("/snapshot")
async def report_snapshot(
    report_type: Literal["daily", "weekly"] = "daily",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_report_snapshot(db, report_type)


@router.post("/refresh")
async def refresh_report(
    data: ReportSnapshotRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await refresh_report_snapshot(
            db,
            data.report_type,
            trigger="manual",
            raise_ai_error=True,
        )
    except AIBackendError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.get("/weekly")
async def weekly_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await generate_weekly_report(db)


@router.post("/send")
async def send_report(
    data: SendReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = data.report
    if not report:
        if data.report_type == "weekly":
            snapshot = await get_report_snapshot(db, "weekly")
        else:
            snapshot = await get_report_snapshot(db, "daily")
        report = snapshot.get("report")
    if not report:
        raise HTTPException(status_code=400, detail="No cached report. Refresh the report first.")

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
