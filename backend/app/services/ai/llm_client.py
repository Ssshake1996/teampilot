import json
import logging

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
        self._http = httpx.AsyncClient(timeout=180.0)

    async def chat(self, messages: list[dict], **kwargs) -> str:
        """Send a chat completion request. Returns the assistant content."""
        resp = await self._http.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                "temperature": kwargs.get("temperature", self.temperature),
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    async def chat_json(self, messages: list[dict], **kwargs) -> dict:
        """Chat expecting a JSON response. Parses from markdown fences if needed."""
        content = await self.chat(messages, **kwargs)
        # Try direct JSON parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        # Try extracting from ```json ... ``` fences
        if "```json" in content:
            start = content.index("```json") + 7
            end = content.index("```", start)
            return json.loads(content[start:end].strip())
        if "```" in content:
            start = content.index("```") + 3
            end = content.index("```", start)
            return json.loads(content[start:end].strip())
        raise ValueError(f"Could not parse JSON from LLM response: {content[:200]}")

    async def test_connection(self) -> bool:
        """Test if the API endpoint is reachable and configured correctly."""
        try:
            result = await self.chat(
                [{"role": "user", "content": "Say 'OK' and nothing else."}],
                max_tokens=10,
            )
            return bool(result.strip())
        except Exception as e:
            logger.warning(f"LLM connection test failed: {e}")
            return False

    async def close(self):
        await self._http.aclose()
