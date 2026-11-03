"""Provider contract, request compatibility, and secret-handling regressions."""
import json
import uuid

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.config import settings
from app.models.system_setting import SystemSetting
from app.models.user import User, UserRole
from app.schemas.model_provider import KEEP_SECRET
from app.services import model_provider_service as service
from app.utils.security import create_access_token, hash_password


@pytest.fixture(autouse=True)
def isolated_encryption_key(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "MODEL_PROVIDER_ENCRYPTION_KEY", "")
    monkeypatch.setattr(settings, "MODEL_PROVIDER_KEY_FILE", str(tmp_path / "provider.key"))


def payload(**changes):
    return {"key": "gateway", "name": "Gateway", "protocol": "openai-completions",
            "base_url": "https://gateway.test/v1", "api_key": "private-api-value",
            "headers": {"X-Gateway-Key": "private-header-value"},
            "model_ids": ["test-model"], "default_model": "test-model", **changes}


@pytest.mark.asyncio
async def test_provider_crud_masks_and_encrypts_secrets(client, auth_headers, db_session):
    created = await client.post("/api/v1/model-providers", headers=auth_headers, json=payload())
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["has_api_key"] is True
    assert data["headers"] == {"X-Gateway-Key": KEEP_SECRET}
    assert "api_key" not in data
    assert "private-api-value" not in created.text
    assert "private-header-value" not in created.text
    setting = (await db_session.execute(select(SystemSetting).where(SystemSetting.key == "model_providers"))).scalar_one()
    stored = json.dumps(setting.value_json)
    assert "private-api-value" not in stored and "private-header-value" not in stored
    assert service._decrypt(setting.value_json["providers"][0]) == {"api_key": "private-api-value", "headers": {"X-Gateway-Key": "private-header-value"}}
    duplicate = await client.post("/api/v1/model-providers", headers=auth_headers, json=payload(key="gateway"))
    assert duplicate.status_code == 409
    changed = await client.patch(f"/api/v1/model-providers/{data['id']}", headers=auth_headers, json={"is_enabled": False})
    assert changed.status_code == 200 and changed.json()["is_enabled"] is False
    assert changed.json()["headers"] == data["headers"] and changed.json()["has_api_key"] is True
    cleared = await client.patch(f"/api/v1/model-providers/{data['id']}", headers=auth_headers, json={"clear_api_key": True, "headers": {}})
    assert cleared.status_code == 200
    assert cleared.json()["has_api_key"] is False and cleared.json()["headers"] == {}
    listed = await client.get("/api/v1/model-providers", headers=auth_headers)
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert (await client.delete(f"/api/v1/model-providers/{data['id']}", headers=auth_headers)).status_code == 204
    assert (await client.get("/api/v1/model-providers", headers=auth_headers)).json() == []


def mock_upstream(monkeypatch, handler):
    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol,base,path,body_field,response", [
    ("openai-completions", "https://gateway.test/prefix/v1/", "/prefix/v1/chat/completions", "messages", {"choices": [{"message": {"content": "OK"}}]}),
    ("openai-responses", "https://gateway.test/prefix/v1", "/prefix/v1/responses", "input", {"output": [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}]}),
    ("anthropic-messages", "https://gateway.test/prefix/v1/", "/prefix/v1/messages", "messages", {"content": [{"type": "text", "text": "OK"}]}),
])
async def test_protocol_inference_urls_auth_and_bodies(client, auth_headers, monkeypatch, protocol, base, path, body_field, response):
    calls = []

    def handler(request):
        assert request.url.path == path
        assert request.method == "POST"
        body = json.loads(request.content)
        assert body["model"] == "test-model" and body_field in body
        assert body["stream"] is False
        assert request.headers["X-Gateway-Key"] == "private-header-value"
        if protocol == "anthropic-messages":
            assert request.headers["x-api-key"] == "private-api-value"
            assert request.headers["anthropic-version"] == "2023-06-01"
            assert "authorization" not in request.headers
        else:
            assert request.headers["authorization"] == "Bearer private-api-value"
            assert "x-api-key" not in request.headers
        calls.append(request)
        return httpx.Response(200, json=response)

    mock_upstream(monkeypatch, handler)
    result = await client.post("/api/v1/model-providers/test", headers=auth_headers, json=payload(protocol=protocol, base_url=base))
    assert result.status_code == 200, result.text
    assert result.json()["ok"] is True and result.json()["model"] == "test-model"
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol,base,path", [
    ("openai-completions", "https://gateway.test/prefix/v1/", "/prefix/v1/models"),
    ("openai-responses", "https://gateway.test/prefix/v1", "/prefix/v1/models"),
    ("anthropic-messages", "https://gateway.test/prefix/v1", "/prefix/v1/models"),
])
async def test_model_discovery_keeps_saved_secrets_and_standard_auth_priority(client, auth_headers, monkeypatch, protocol, base, path):
    saved = await client.post("/api/v1/model-providers", headers=auth_headers,
                              json=payload(protocol=protocol, base_url=base, headers={"Authorization": "Custom private-token", "X-API-Key": "Custom private-key", "Anthropic-Version": "wrong"}))
    assert saved.status_code == 201

    def handler(request):
        assert request.method == "GET" and request.url.path == path
        if protocol == "anthropic-messages":
            assert request.url.params["limit"] == "1000"
            assert request.headers["x-api-key"] == "private-api-value"
            assert request.headers["anthropic-version"] == "2023-06-01"
            assert request.headers["authorization"] == "Custom private-token"
        else:
            assert request.headers["authorization"] == "Bearer private-api-value"
        return httpx.Response(200, json={"data": [{"id": "model-a"}, {"id": "model-a"}, {"id": "model-b", "display_name": "Model B"}]})

    mock_upstream(monkeypatch, handler)
    probe = payload(protocol=protocol, base_url=base, id=saved.json()["id"], api_key="", headers=saved.json()["headers"])
    result = await client.post("/api/v1/model-providers/models", headers=auth_headers, json=probe)
    assert result.status_code == 200, result.text
    assert result.json()["models"] == [{"id": "model-a", "name": "model-a"}, {"id": "model-b", "name": "Model B"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,status", [("unauthorized",502),("malformed",502),("timeout",504),("large",502)])
async def test_provider_failures_do_not_echo_upstream_secrets(client, auth_headers, monkeypatch, mode, status):
    def handler(request):
        if mode == "unauthorized":
            return httpx.Response(401, text="private-api-value private-header-value")
        if mode == "malformed":
            return httpx.Response(200, json={"choices": [{}]})
        if mode == "large":
            return httpx.Response(200, content=b"x" * (service.MAX_RESPONSE_BYTES + 1))
        raise httpx.ReadTimeout("private-api-value")

    mock_upstream(monkeypatch, handler)
    result = await client.post("/api/v1/model-providers/test", headers=auth_headers, json=payload())
    assert result.status_code == status, result.text
    assert "private-api-value" not in result.text and "private-header-value" not in result.text


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol,response", [
    ("openai-completions", {"choices": None}),
    ("openai-completions", {"choices": 7}),
    ("openai-responses", {"output": None}),
    ("openai-responses", {"output": True}),
    ("anthropic-messages", {"content": None}),
    ("anthropic-messages", {"content": "OK"}),
    ("openai-responses", {"status": "failed", "output": [{"type":"message","content":[{"text":"OK"}]}]}),
    ("openai-responses", {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}, "output": [{"type":"message","content":[{"text":"OK"}]}]}),
])
async def test_malformed_or_incomplete_outputs_are_not_success(client, auth_headers, monkeypatch, protocol, response):
    mock_upstream(monkeypatch, lambda request: httpx.Response(200,json=response))
    result = await client.post("/api/v1/model-providers/test", headers=auth_headers, json=payload(protocol=protocol))
    assert result.status_code == 502, result.text
    if response.get("status") == "incomplete":
        assert "额度不足" in result.json()["detail"]


@pytest.mark.asyncio
async def test_models_object_fallback_and_header_only_auth(client, auth_headers, monkeypatch):
    def handler(request):
        assert request.headers["authorization"] == "Custom private-token"
        return httpx.Response(200,json={"data":None,"models":{"model-a":{"name":"Model A"},"metadata":"ignore","count":7}})
    mock_upstream(monkeypatch,handler)
    result=await client.post("/api/v1/model-providers/models",headers=auth_headers,json=payload(api_key="",headers={"Authorization":"Custom private-token"},model_ids=[],default_model=""))
    assert result.status_code==200,result.text
    assert result.json()["models"]==[{"id":"model-a","name":"Model A"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["gpt-5", "gpt-5.1", "o1", "o3-mini", "o4-mini"])
async def test_openai_reasoning_model_uses_completion_token_parameter(client,auth_headers,monkeypatch,model):
    def handler(request):
        body=json.loads(request.content)
        assert "max_completion_tokens" in body and "max_tokens" not in body
        return httpx.Response(200,json={"choices":[{"message":{"content":"OK"}}]})
    mock_upstream(monkeypatch,handler)
    result=await client.post("/api/v1/model-providers/test",headers=auth_headers,json=payload(default_model=model))
    assert result.status_code==200,result.text


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"headers": {"X-Token": "private-header-value\r\nInjected: true"}},
    {"headers": {"Host": "private-header-value"}},
    {"base_url": "https://user:private-api-value@gateway.test"},
    {"protocol": "unsupported"},
    {"timeout_seconds": 999},
    {"headers": {"X-Token": "private-header-value中文"}},
    {"api_key": "private-api-value中文"},
    {"base_url": "https://gateway.test/path with-space"},
    {"base_url": "https://gateway.test:0"},
])
async def test_invalid_provider_input_never_echoes_secrets(client, auth_headers, changes):
    result = await client.post("/api/v1/model-providers", headers=auth_headers, json=payload(**changes))
    assert result.status_code == 422, result.text
    assert "private-header-value" not in result.text and "private-api-value" not in result.text


@pytest.mark.asyncio
async def test_missing_key_does_not_replace_or_destroy_saved_credentials(client, auth_headers, monkeypatch, tmp_path):
    saved = await client.post("/api/v1/model-providers", headers=auth_headers, json=payload())
    assert saved.status_code == 201
    key_path = tmp_path / "provider.key"
    assert key_path.is_file()
    original_key = key_path.read_bytes()
    key_path.unlink()
    result = await client.patch(f"/api/v1/model-providers/{saved.json()['id']}", headers=auth_headers, json={"name": "Changed"})
    assert result.status_code == 400
    assert not key_path.exists()
    key_path.write_bytes(original_key)
    result = await client.patch(f"/api/v1/model-providers/{saved.json()['id']}", headers=auth_headers, json={"name": "Changed"})
    assert result.status_code == 200
    assert result.json()["has_api_key"] is True
    assert (await client.get("/api/v1/model-providers", headers=auth_headers)).json()[0]["name"] == "Changed"


@pytest.mark.asyncio
async def test_provider_permissions_and_catalog(client, auth_headers, db_session):
    response = await client.get("/api/v1/model-providers/catalog", headers=auth_headers)
    assert response.status_code == 200
    assert {item["id"] for item in response.json()["protocols"]} == {"openai-completions", "openai-responses", "anthropic-messages"}
    user = User(id=uuid.uuid4(), username="provider-member", full_name="Member", hashed_password=hash_password("password123"), role=UserRole.MEMBER)
    db_session.add(user)
    await db_session.commit()
    headers = {"Authorization": "Bearer " + create_access_token({"sub": str(user.id), "role": user.role.value})}
    assert (await client.get("/api/v1/model-providers", headers=headers)).status_code == 403
    assert (await client.post("/api/v1/model-providers/test", headers=headers, json=payload())).status_code == 403


@pytest.mark.asyncio
async def test_saving_requires_models_and_sets_a_valid_default(client, auth_headers):
    empty = await client.post("/api/v1/model-providers", headers=auth_headers, json=payload(model_ids=[], default_model=""))
    assert empty.status_code == 400
    default_only = await client.post("/api/v1/model-providers", headers=auth_headers, json=payload(model_ids=[]))
    assert default_only.status_code == 201
    assert default_only.json()["model_ids"] == ["test-model"]
    model_only = await client.post("/api/v1/model-providers", headers=auth_headers, json=payload(key="second", default_model="", model_ids=["first-model", "second-model"]))
    assert model_only.status_code == 201
    assert model_only.json()["default_model"] == "first-model"
    invalid_patch = await client.patch(f"/api/v1/model-providers/{model_only.json()['id']}", headers=auth_headers, json={"headers": {"Invalid Header": "private-header-value"}})
    assert invalid_patch.status_code == 422
    assert "private-header-value" not in invalid_patch.text


@pytest.mark.asyncio
async def test_environment_encryption_key_avoids_local_key_file(client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "MODEL_PROVIDER_ENCRYPTION_KEY", Fernet.generate_key().decode())
    created = await client.post("/api/v1/model-providers", headers=auth_headers, json=payload())
    assert created.status_code == 201
    assert not (tmp_path / "provider.key").exists()
    changed = await client.patch(f"/api/v1/model-providers/{created.json()['id']}", headers=auth_headers, json={"api_key": "", "headers": {"X-Gateway-Key": KEEP_SECRET}})
    assert changed.status_code == 200
    monkeypatch.setattr(settings, "MODEL_PROVIDER_ENCRYPTION_KEY", Fernet.generate_key().decode())
    failed = await client.patch(f"/api/v1/model-providers/{created.json()['id']}", headers=auth_headers, json={"name": "Unchanged"})
    assert failed.status_code == 400
    assert (await client.get("/api/v1/model-providers", headers=auth_headers)).json()[0]["name"] == "Gateway"


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    {"choices": [{"message": {"content": True}}]},
    {"choices": [{"message": {"content": "   "}}]},
    {"choices": [{"message": {"content": "OK"}, "finish_reason": "length"}]},
    {"choices": [{"message": {"content": {"unsupported": "OK"}}}]},
    {"status": {}, "choices": None},
])
async def test_invalid_text_shapes_fail_safely(client, auth_headers, monkeypatch, response):
    mock_upstream(monkeypatch, lambda request: httpx.Response(200, json=response))
    result = await client.post("/api/v1/model-providers/test", headers=auth_headers, json=payload())
    assert result.status_code == 502, result.text
