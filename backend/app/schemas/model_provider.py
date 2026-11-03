"""Model provider configuration, separate from business data connectors."""
import re
import uuid
from datetime import datetime
from enum import Enum
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


KEEP_SECRET = "__KEEP_SECRET__"


class ModelProtocol(str, Enum):
    OPENAI_COMPLETIONS = "openai-completions"
    OPENAI_RESPONSES = "openai-responses"
    ANTHROPIC_MESSAGES = "anthropic-messages"


def validate_base_url(value: str) -> str:
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("API 地址不能包含空白或控制字符")
    value = value.rstrip("/")
    parsed = urlsplit(value)
    try:
        if parsed.port is not None and parsed.port < 1:
            raise ValueError
    except ValueError:
        raise ValueError("API 地址端口不正确") from None
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("API 地址须为不含账号、查询参数或片段的 HTTP/HTTPS 基础地址")
    return value


def validate_headers(value: dict[str, str]) -> dict[str, str]:
    if len(value) > 50:
        raise ValueError("自定义请求头最多 50 项")
    normalized = {}
    used = set()
    for key, item in value.items():
        key = key.strip()
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key):
            raise ValueError("请求头名称不正确")
        if key.lower() in used:
            raise ValueError("请求头名称不能重复（不区分大小写）")
        if any(character in item for character in "\r\n\x00") or not item.isascii() or len(item) > 8192:
            raise ValueError("请求头值包含不支持的字符或过长")
        if key.lower() in {"host", "content-length", "transfer-encoding", "connection"}:
            raise ValueError("不能自定义 HTTP 传输控制请求头")
        used.add(key.lower())
        normalized[key] = item
    return normalized


class ProviderFields(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9-]*$")
    name: str = Field(min_length=1, max_length=100)
    protocol: ModelProtocol
    base_url: str = Field(max_length=2048)
    api_key: SecretStr | None = None
    clear_api_key: bool = False
    headers: dict[str, str] = Field(default_factory=dict)
    model_ids: list[str] = Field(default_factory=list, max_length=500)
    default_model: str = Field(default="", max_length=256)
    is_enabled: bool = True
    timeout_seconds: int = Field(default=60, ge=1, le=180)
    verify_tls: bool = True

    _base_url = field_validator("base_url")(validate_base_url)
    _headers = field_validator("headers")(validate_headers)

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value and (not value.get_secret_value().isascii() or any(character in value.get_secret_value() for character in "\r\n\x00")):
            raise ValueError("API Key 包含不支持的字符")
        return value

    @field_validator("name", "default_model")
    @classmethod
    def trim_string(cls, value: str) -> str:
        value = value.strip()
        if "\n" in value or "\r" in value:
            raise ValueError("名称或模型 ID 不能包含换行")
        return value

    @field_validator("model_ids")
    @classmethod
    def validate_models(cls, values: list[str]) -> list[str]:
        models = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(model) > 256 or "\n" in model or "\r" in model for model in models):
            raise ValueError("模型 ID 不正确或过长")
        return models


class ModelProviderCreate(ProviderFields):
    pass


class ModelProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    key: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9-]*$")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    protocol: ModelProtocol | None = None
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: SecretStr | None = None
    clear_api_key: bool = False
    headers: dict[str, str] | None = None
    model_ids: list[str] | None = Field(default=None, max_length=500)
    default_model: str | None = Field(default=None, max_length=256)
    is_enabled: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=180)
    verify_tls: bool | None = None


class ModelProviderProbe(ProviderFields):
    id: uuid.UUID | None = None


class ModelProviderOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    protocol: ModelProtocol
    base_url: str
    has_api_key: bool
    headers: dict[str, str]
    model_ids: list[str]
    default_model: str
    is_enabled: bool
    timeout_seconds: int
    verify_tls: bool
    created_at: datetime
    updated_at: datetime
