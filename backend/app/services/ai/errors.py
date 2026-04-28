from __future__ import annotations

import httpx


class AIBackendError(RuntimeError):
    def __init__(self, message: str, original: Exception):
        super().__init__(message)
        self.message = message
        self.original = original

    @property
    def status_code(self) -> int:
        if isinstance(self.original, httpx.TimeoutException):
            return 504
        return 502

    def to_detail(self) -> dict:
        original = self.original
        backend_detail = str(original) or repr(original)
        detail = {
            "message": self.message,
            "status_code": self.status_code,
            "error_type": type(original).__name__,
            "backend_detail": backend_detail[:1000],
        }
        if isinstance(original, httpx.HTTPStatusError):
            detail["upstream_status_code"] = original.response.status_code
            detail["backend_detail"] = (original.response.text or backend_detail)[:1000]
        return detail
