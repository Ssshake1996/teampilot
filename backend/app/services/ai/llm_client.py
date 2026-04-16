import json
import logging
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified client for any OpenAI-compatible chat completions API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._http = httpx.AsyncClient(timeout=180.0, verify=False)

    def _build_payload(self, messages: list[dict], stream: bool = False, **kwargs) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
        }
        if stream:
            payload["stream"] = True
        return payload

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat(self, messages: list[dict], **kwargs) -> str:
        """Non-streaming chat. Returns the assistant content."""
        resp = await self._http.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=self._build_payload(messages, **kwargs),
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        """Streaming chat. Yields content delta strings as they arrive."""
        async with self._http.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=self._build_payload(messages, stream=True, **kwargs),
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    # Only yield actual content, skip reasoning_content (thinking)
                    content = delta.get("content")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

    async def chat_stream_collect(self, messages: list[dict], **kwargs) -> str:
        """Streaming chat that collects all content into a single string.
        Benefit: keeps the connection alive as long as tokens flow,
        no fixed timeout risk."""
        parts = []
        async for chunk in self.chat_stream(messages, **kwargs):
            parts.append(chunk)
        return "".join(parts)

    async def chat_json(self, messages: list[dict], **kwargs) -> dict:
        """Chat expecting JSON. Uses streaming internally to avoid timeout."""
        content = await self.chat_stream_collect(messages, **kwargs)
        return self._parse_json(content)

    @staticmethod
    def _parse_json(content: str) -> dict:
        """Parse JSON from LLM output, handling markdown fences."""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        if "```json" in content:
            start = content.index("```json") + 7
            end = content.index("```", start)
            return json.loads(content[start:end].strip())
        if "```" in content:
            start = content.index("```") + 3
            end = content.index("```", start)
            return json.loads(content[start:end].strip())
        raise ValueError(f"Could not parse JSON from LLM response: {content[:200]}")

    async def test_connection(self) -> dict:
        try:
            result = await self.chat(
                [{"role": "user", "content": "Say 'OK' and nothing else."}],
                max_tokens=10,
            )
            return {
                "success": bool(result.strip()),
                "message": "Connection successful" if result.strip() else "Empty response from model service",
                "status_code": 200,
                "error_type": None,
                "backend_detail": result.strip() or None,
            }
        except httpx.HTTPStatusError as exc:
            body = exc.response.text
            logger.warning(f"LLM connection test failed: {exc}")
            return {
                "success": False,
                "message": f"HTTP {exc.response.status_code}: {exc.response.reason_phrase}",
                "status_code": exc.response.status_code,
                "error_type": exc.__class__.__name__,
                "backend_detail": body[:1000] if body else None,
            }
        except httpx.RequestError as exc:
            logger.warning(f"LLM connection test failed: {exc}")
            return {
                "success": False,
                "message": str(exc),
                "status_code": None,
                "error_type": exc.__class__.__name__,
                "backend_detail": repr(exc),
            }
        except Exception as e:
            logger.warning(f"LLM connection test failed: {e}")
            return {
                "success": False,
                "message": str(e),
                "status_code": None,
                "error_type": e.__class__.__name__,
                "backend_detail": repr(e),
            }

    async def close(self):
        await self._http.aclose()
