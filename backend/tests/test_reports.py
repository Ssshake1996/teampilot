"""Tests for report generation and email sending."""

import pytest
from httpx import AsyncClient

from app.config import settings
from app.services import report_service


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
