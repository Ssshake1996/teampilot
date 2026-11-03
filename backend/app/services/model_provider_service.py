"""Persist provider settings and adapt the three supported HTTP protocols."""
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.system_setting import SystemSetting
from app.schemas.model_provider import (
    KEEP_SECRET, ModelProtocol, ModelProviderCreate, ModelProviderProbe, ModelProviderUpdate,
)

SETTING_KEY = "model_providers"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024

CATALOG = {
    "protocols": [
        {"id": "openai-completions", "label": "OpenAI Chat Completions"},
        {"id": "openai-responses", "label": "OpenAI Responses"},
        {"id": "anthropic-messages", "label": "Anthropic Messages"},
    ],
    "presets": [
        {"key": "deepseek", "name": "DeepSeek", "protocol": "openai-completions", "base_url": "https://api.deepseek.com", "model_ids": ["deepseek-chat", "deepseek-reasoner"], "default_model": "deepseek-chat"},
        {"key": "openai", "name": "OpenAI", "protocol": "openai-responses", "base_url": "https://api.openai.com/v1", "model_ids": [], "default_model": ""},
        {"key": "anthropic", "name": "Anthropic", "protocol": "anthropic-messages", "base_url": "https://api.anthropic.com", "model_ids": [], "default_model": ""},
        {"key": "moonshot", "name": "Moonshot", "protocol": "openai-completions", "base_url": "https://api.moonshot.cn/v1", "model_ids": [], "default_model": ""},
        {"key": "custom", "name": "自定义供应商", "protocol": "openai-completions", "base_url": "", "model_ids": [], "default_model": ""},
    ],
}


class ProviderError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _fernet(*, create: bool) -> Fernet:
    configured = settings.MODEL_PROVIDER_ENCRYPTION_KEY.strip()
    if configured:
        key = configured.encode()
    else:
        path = (Path(settings.MODEL_PROVIDER_KEY_FILE).expanduser() if settings.MODEL_PROVIDER_KEY_FILE
                else Path(__file__).resolve().parents[2] / ".model-provider.key")
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        try:
            if not path.exists() and create:
                path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    pass
                else:
                    with os.fdopen(descriptor, "wb") as target:
                        target.write(Fernet.generate_key())
            key = path.read_bytes().strip()
        except OSError:
            raise ProviderError("模型配置加密密钥不可用，请恢复原密钥文件或配置环境变量") from None
    try:
        return Fernet(key)
    except (ValueError, TypeError):
        raise ProviderError("模型配置加密密钥格式不正确，请检查部署配置") from None


def _encrypt(secrets: dict) -> str:
    if not secrets["api_key"] and not secrets["headers"]:
        return ""
    return _fernet(create=True).encrypt(json.dumps(secrets).encode()).decode()


def _decrypt(provider: dict) -> dict:
    if not provider.get("secrets"):
        return {"api_key": "", "headers": {}}
    try:
        return json.loads(_fernet(create=False).decrypt(provider["secrets"].encode()))
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise ProviderError("模型配置凭据无法解密，请恢复保存时使用的加密密钥") from None


async def _setting(db: AsyncSession, *, lock: bool = False) -> SystemSetting | None:
    query = select(SystemSetting).where(SystemSetting.key == SETTING_KEY)
    if lock:
        query = query.with_for_update()
    return (await db.execute(query)).scalar_one_or_none()


def _rows(setting: SystemSetting | None) -> list[dict]:
    return list(setting.value_json.get("providers", [])) if setting else []


def _find(rows: list[dict], provider_id: uuid.UUID | str) -> dict:
    item = next((row for row in rows if row["id"] == str(provider_id)), None)
    if item is None:
        raise ProviderError("模型供应商不存在，请刷新后重试", 404)
    return item


def _public(provider: dict) -> dict:
    return {key: value for key, value in provider.items() if key != "secrets"} | {
        "has_api_key": provider.get("has_api_key", False),
        "headers": {key: KEEP_SECRET for key in provider.get("header_names", [])},
    }


async def list_providers(db: AsyncSession) -> list[dict]:
    return [_public(row) for row in _rows(await _setting(db))]


def _resolve(data: ModelProviderCreate | ModelProviderProbe, existing: dict | None = None) -> tuple[dict, dict]:
    values = data.model_dump(mode="json", exclude={"id", "api_key", "clear_api_key", "headers"})
    values["name"] = values["name"].strip()
    if not values["name"]:
        raise ProviderError("请输入供应商名称")
    # Preserve the old encrypted secret when an edit leaves the password field empty.
    old = _decrypt(existing) if existing else {"api_key": "", "headers": {}}
    incoming_key = data.api_key.get_secret_value().strip() if data.api_key else ""
    api_key = "" if data.clear_api_key else incoming_key or old["api_key"]
    headers = {}
    for key, value in data.headers.items():
        if value == KEEP_SECRET:
            old_name = next((name for name in old["headers"] if name.lower() == key.lower()), None)
            if old_name is None:
                raise ProviderError("新请求头不能使用已保存值占位符，请输入实际值")
            value = old["headers"][old_name]
        headers[key] = value
    return values, {"api_key": api_key, "headers": headers}


async def _save(db: AsyncSession, setting: SystemSetting | None, rows: list[dict]) -> None:
    if setting:
        setting.value_json = {"providers": rows}
    else:
        db.add(SystemSetting(key=SETTING_KEY, value_json={"providers": rows}))
    try:
        await db.flush()
    except IntegrityError:
        raise ProviderError("模型配置已被其他用户更新，请刷新后重试", 409) from None


def _require_saved_models(values: dict) -> None:
    if values["default_model"] and values["default_model"] not in values["model_ids"]:
        values["model_ids"].append(values["default_model"])
    if not values["model_ids"]:
        raise ProviderError("请至少添加一个模型后再保存供应商")
    if not values["default_model"]:
        values["default_model"] = values["model_ids"][0]


async def create_provider(db: AsyncSession, data: ModelProviderCreate) -> dict:
    setting = await _setting(db, lock=True)
    rows = _rows(setting)
    if any(row["key"].lower() == data.key.lower() for row in rows):
        raise ProviderError("供应商标识已存在", 409)
    values, secrets = _resolve(data)
    _require_saved_models(values)
    now = datetime.now(timezone.utc).isoformat()
    item = values | {"id": str(uuid.uuid4()), "created_at": now, "updated_at": now,
                     "secrets": _encrypt(secrets), "has_api_key": bool(secrets["api_key"]), "header_names": list(secrets["headers"])}
    await _save(db, setting, rows + [item])
    return _public(item)


async def update_provider(db: AsyncSession, provider_id: uuid.UUID, data: ModelProviderUpdate) -> dict:
    setting = await _setting(db, lock=True)
    rows = _rows(setting)
    old = _find(rows, provider_id)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    raw = {key: value for key, value in old.items() if key not in {"id", "created_at", "updated_at", "secrets", "has_api_key", "header_names"}}
    raw["headers"] = {name: KEEP_SECRET for name in old.get("header_names", [])}
    raw.update(changes)
    full = ModelProviderCreate.model_validate(raw)
    if any(row["id"] != str(provider_id) and row["key"].lower() == full.key.lower() for row in rows):
        raise ProviderError("供应商标识已存在", 409)
    values, secrets = _resolve(full, old)
    _require_saved_models(values)
    item = values | {"id": old["id"], "created_at": old["created_at"], "updated_at": datetime.now(timezone.utc).isoformat(),
                     "secrets": _encrypt(secrets), "has_api_key": bool(secrets["api_key"]), "header_names": list(secrets["headers"])}
    await _save(db, setting, [item if row["id"] == old["id"] else row for row in rows])
    return _public(item)


async def delete_provider(db: AsyncSession, provider_id: uuid.UUID) -> None:
    setting = await _setting(db, lock=True)
    rows = _rows(setting)
    _find(rows, provider_id)
    await _save(db, setting, [row for row in rows if row["id"] != str(provider_id)])


async def resolve_probe(db: AsyncSession, data: ModelProviderProbe) -> tuple[dict, dict]:
    existing = _find(_rows(await _setting(db)), data.id) if data.id else None
    return _resolve(data, existing)


def _request_config(provider: dict, secrets: dict, *, discover: bool) -> tuple[str, dict]:
    base = provider["base_url"].rstrip("/")
    anthropic = provider["protocol"] == ModelProtocol.ANTHROPIC_MESSAGES.value
    headers = {name.lower(): value for name, value in secrets["headers"].items()}
    headers["content-type"] = "application/json"
    if anthropic:
        if base.endswith("/v1"):
            base = base[:-3]
        headers["anthropic-version"] = "2023-06-01"
        if secrets["api_key"]:
            headers["x-api-key"] = secrets["api_key"]
        path = "/v1/models?limit=1000" if discover else "/v1/messages"
    else:
        if secrets["api_key"]:
            headers["authorization"] = "Bearer " + secrets["api_key"]
        path = "/models" if discover else ("/responses" if provider["protocol"] == ModelProtocol.OPENAI_RESPONSES.value else "/chat/completions")
    return base + path, headers


async def _request(provider: dict, secrets: dict, *, discover: bool) -> dict:
    url, headers = _request_config(provider, secrets, discover=discover)
    body = None
    if not discover:
        model = provider["default_model"]
        if not model:
            raise ProviderError("请先选择或输入测试模型")
        if provider["protocol"] == ModelProtocol.OPENAI_RESPONSES.value:
            body = {"model": model, "input": "Reply with OK.", "max_output_tokens": 256, "stream": False}
        else:
            token_field = "max_completion_tokens" if provider["protocol"] == ModelProtocol.OPENAI_COMPLETIONS.value and re.match(r"^(gpt-5(?:[.-]|$)|o[134](?:[.-]|$))", model) else "max_tokens"
            body = {"model": model, "messages": [{"role": "user", "content": "Reply with OK."}], token_field: 256, "stream": False}
    try:
        async with httpx.AsyncClient(timeout=provider["timeout_seconds"], verify=provider["verify_tls"], follow_redirects=False) as client:
            async with client.stream("GET" if discover else "POST", url, headers=headers, **({"json": body} if body else {})) as response:
                if response.status_code >= 400 or response.is_redirect:
                    status = response.status_code
                    hint = "鉴权失败，请检查 API Key 和请求头" if status in {401, 403} else "请求失败，请检查协议、地址和模型配置"
                    raise ProviderError(f"供应商返回 HTTP {status}：{hint}", 502)
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise ProviderError("供应商响应超过 4 MiB 限制，请检查 API 地址或缩小模型列表", 502)
                    content.extend(chunk)
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ProviderError("供应商响应不是有效的 JSON 对象", 502)
        if result.get("error"):
            raise ProviderError("供应商返回错误，请检查模型、鉴权和账户状态", 502)
        return result
    except httpx.TimeoutException:
        raise ProviderError("连接供应商超时，请检查地址或稍后重试", 504) from None
    except (httpx.HTTPError, httpx.InvalidURL, UnicodeEncodeError):
        raise ProviderError("无法连接供应商，请检查 API 地址、网络和 HTTPS 证书", 502) from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ProviderError("供应商响应不是有效 JSON，请检查 API 地址和协议", 502) from None


async def discover_models(db: AsyncSession, data: ModelProviderProbe) -> dict:
    provider, secrets = await resolve_probe(db, data)
    response = await _request(provider, secrets, discover=True)
    candidates = response.get("data")
    if not isinstance(candidates, list):
        models = response.get("models")
        candidates = [{"id": key, "name": value.get("name", key)} for key, value in models.items() if isinstance(value, dict)] if isinstance(models, dict) else None
    if not isinstance(candidates, list):
        raise ProviderError("供应商未返回模型列表，可手动输入模型 ID 后测试连接", 502)
    models = {}
    for item in candidates:
        model_id = item.get("id") if isinstance(item, dict) else None
        if isinstance(model_id, str) and model_id.strip():
            models[model_id] = {"id": model_id, "name": str(item.get("name") or item.get("display_name") or model_id) if isinstance(item, dict) else model_id}
    return {"models": list(models.values())}


async def test_connection(db: AsyncSession, data: ModelProviderProbe) -> dict:
    provider, secrets = await resolve_probe(db, data)
    started = time.monotonic()
    response = await _request(provider, secrets, discover=False)
    protocol = provider["protocol"]
    incomplete = response.get("incomplete_details")
    if response.get("status") == "incomplete" and isinstance(incomplete, dict) and incomplete.get("reason") == "max_output_tokens":
        raise ProviderError("测试输出额度不足，模型尚未完成回复；请检查模型的推理输出要求", 502)
    if response.get("status") in ("failed", "cancelled", "incomplete") or response.get("type") == "error":
        raise ProviderError("供应商模型输出失败或不完整，请检查模型与账户状态", 502)
    if protocol == ModelProtocol.OPENAI_COMPLETIONS.value:
        choices = response.get("choices")
        if isinstance(choices, list) and any(isinstance(choice, dict) and choice.get("finish_reason") == "length" for choice in choices):
            raise ProviderError("测试输出额度不足，模型尚未完成回复；请检查模型的推理输出要求", 502)
        valid = any(isinstance(choice, dict) and isinstance(choice.get("message"), dict)
                    and any(isinstance(choice["message"].get(key), str) and choice["message"][key].strip() for key in ("content", "reasoning_content"))
                    and choice.get("finish_reason") not in ("length", "content_filter", "error")
                    for choice in choices) if isinstance(choices, list) else False
    elif protocol == ModelProtocol.OPENAI_RESPONSES.value:
        output = response.get("output")
        valid = any(isinstance(item, dict) and item.get("type") == "message"
                    and isinstance(item.get("content"), list)
                    and any(isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"].strip() for part in item["content"])
                    for item in output) if isinstance(output, list) else False
    else:
        content = response.get("content")
        if response.get("stop_reason") == "max_tokens":
            raise ProviderError("测试输出额度不足，模型尚未完成回复；请检查模型的推理输出要求", 502)
        valid = any(isinstance(item, dict) and any(isinstance(item.get(key), str) and item[key].strip() for key in ("text", "thinking"))
                    for item in content) if isinstance(content, list) else False
        valid = valid and response.get("stop_reason") not in ("max_tokens", "refusal", "error")
    if not valid:
        raise ProviderError("供应商未返回对应协议的模型输出，请检查协议与 API 地址", 502)
    return {"ok": True, "model": provider["default_model"], "protocol": protocol,
            "message": "模型调用成功", "latency_ms": round((time.monotonic() - started) * 1000)}
