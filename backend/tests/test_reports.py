"""Tests for report generation and email sending."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient

from app.config import settings
from app.models.project import Project, ProjectStatus
from app.services import report_service
from app.services.ai.project_automation import daily_brief


class DummySMTP:
    messages = []

    def __init__(self, host, port, timeout=20):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.logged_in = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.logged_in = True

    def send_message(self, message):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_weekly_report_endpoint(client: AsyncClient, auth_headers):
    res = await client.get("/api/v1/reports/weekly", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["period_start"]
    assert data["period_end"]
    assert "summary" in data
    assert "project_progress_table" in data
    assert "progress_fast_top3" in data
    assert "progress_slow_top3" in data
    assert "members_without_updates" not in data


@pytest.mark.asyncio
async def test_weekly_report_includes_all_active_projects(client: AsyncClient, auth_headers):
    project_names = ["Weekly Report Project A", "Weekly Report Project B"]
    for name in project_names:
        res = await client.post("/api/v1/projects", json={"name": name}, headers=auth_headers)
        assert res.status_code == 201

    archived = await client.post(
        "/api/v1/projects",
        json={"name": "Archived Weekly Report Project"},
        headers=auth_headers,
    )
    assert archived.status_code == 201
    await client.delete(f"/api/v1/projects/{archived.json()['id']}", headers=auth_headers)

    res = await client.get("/api/v1/reports/weekly", headers=auth_headers)
    assert res.status_code == 200
    table_names = {item["project_name"] for item in res.json()["project_progress_table"]}
    assert set(project_names).issubset(table_names)
    assert "Archived Weekly Report Project" not in table_names


@pytest.mark.asyncio
async def test_weekly_report_uses_ai_sections_without_changing_project_table(db_session, test_user):
    user, _ = test_user
    db_session.add(Project(
        name="AI Weekly Report Project",
        owner_id=user.id,
        status=ProjectStatus.ACTIVE,
    ))
    await db_session.commit()

    class WeeklyLLM:
        async def chat_json(self, messages, temperature=0.2, max_tokens=4096):
            return {
                "summary": "AI weekly summary",
                "risky_projects": ["AI risk"],
                "progress_fast_top3": ["Fast A"],
                "progress_slow_top3": ["Slow B"],
            }

    data = await report_service.generate_weekly_report(db_session, WeeklyLLM())
    assert data["source"] == "ai"
    assert data["summary"] == "AI weekly summary"
    assert data["risky_projects"] == ["AI risk"]
    assert data["progress_fast_top3"] == ["Fast A"]
    assert data["progress_slow_top3"] == ["Slow B"]
    assert data["project_progress_table"][0]["project_name"] == "AI Weekly Report Project"
    assert "members_without_updates" not in data


@pytest.mark.asyncio
async def test_daily_brief_normalizes_ai_report_schema(db_session, test_user):
    class PartialLLM:
        async def chat_json(self, messages, temperature=0.2, max_tokens=4096):
            return {
                "summary": "AI 巡检摘要",
                "risky_projects": "项目 A 有风险",
                "extra_key": "should be ignored",
            }

    data = await daily_brief(db_session, PartialLLM())
    assert data == {
        "summary": "AI 巡检摘要",
        "risky_projects": ["项目 A 有风险"],
        "overdue_blocked_tasks": ["今天没有逾期或明显阻塞的任务。"],
        "progress_fast_top3": ["今天没有足够数据判断进展较快成员。"],
        "progress_slow_top3": ["今天没有足够数据判断进展较慢成员。"],
        "priority_tasks": ["今天没有需要额外优先处理的任务。"],
        "signoff_pending": ["今天没有达到 100% 但待会签的任务。"],
        "source": "ai",
        "source_label": "AI 生成",
    }


@pytest.mark.asyncio
async def test_report_refresh_and_snapshot(client: AsyncClient, auth_headers):
    refresh = await client.post(
        "/api/v1/reports/refresh",
        json={"report_type": "weekly"},
        headers=auth_headers,
    )
    assert refresh.status_code == 200
    refreshed = refresh.json()
    assert refreshed["report_type"] == "weekly"
    assert refreshed["generated_at"]
    assert refreshed["report"]["project_progress_table"] is not None

    snapshot = await client.get(
        "/api/v1/reports/snapshot",
        params={"report_type": "weekly"},
        headers=auth_headers,
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["generated_at"] == refreshed["generated_at"]


def test_report_schedule_slots():
    tz = ZoneInfo("Asia/Shanghai")
    before_daily = datetime(2026, 4, 29, 6, 59, tzinfo=tz)
    due_daily = datetime(2026, 4, 29, 7, 0, tzinfo=tz)
    before_weekly = datetime(2026, 5, 1, 12, 29, tzinfo=tz)
    due_weekly = datetime(2026, 5, 1, 12, 30, tzinfo=tz)

    assert report_service._is_schedule_due("daily", before_daily) is False
    assert report_service._is_schedule_due("daily", due_daily) is True
    assert report_service._schedule_key("daily", before_daily) == "daily:2026-04-28T07:00+08:00"
    assert report_service._schedule_key("daily", due_daily) == "daily:2026-04-29T07:00+08:00"

    assert report_service._is_schedule_due("weekly", before_weekly) is False
    assert report_service._is_schedule_due("weekly", due_weekly) is True
    assert report_service._schedule_key("weekly", before_weekly) == "weekly:2026-04-24T12:30+08:00"
    assert report_service._schedule_key("weekly", due_weekly) == "weekly:2026-05-01T12:30+08:00"


@pytest.mark.asyncio
async def test_send_report_uses_smtp_config(client: AsyncClient, auth_headers, monkeypatch):
    DummySMTP.messages = []
    monkeypatch.setattr(report_service.smtplib, "SMTP", DummySMTP)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "robot@example.test")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "teampilot@example.test")
    monkeypatch.setattr(settings, "SMTP_USE_TLS", True)
    monkeypatch.setattr(settings, "SMTP_USE_SSL", False)

    res = await client.post(
        "/api/v1/reports/send",
        json={
            "report_type": "daily",
            "recipients": ["pm@example.test"],
            "report": {
                "summary": "今日巡检正常",
                "risky_projects": ["暂无风险"],
            },
        },
        headers=auth_headers,
    )

    assert res.status_code == 200
    assert res.json()["recipients"] == ["pm@example.test"]
    assert len(DummySMTP.messages) == 1
    assert DummySMTP.messages[0]["To"] == "pm@example.test"
    assert "今日巡检正常" in DummySMTP.messages[0].get_content()
