from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class RuntimeTaskFailure(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


def map_runtime_exception(exc: Exception) -> RuntimeTaskFailure:
    if isinstance(exc, RuntimeTaskFailure):
        return exc
    message = str(exc).strip() or "Plugin task failed"
    provider_code, provider_message = _provider_error_payload(exc)
    lowered = f"{message} {provider_code or ''} {provider_message or ''}".lower()
    if "provider_settings must include" in lowered:
        return RuntimeTaskFailure(code="plugin_not_configured", message=message)
    if "unsupported provider_profile" in lowered:
        return RuntimeTaskFailure(code="unsupported_provider_profile", message=message)
    if "model_not_found" in lowered or "no available channel for model" in lowered:
        return RuntimeTaskFailure(code="provider_model_not_found", message=provider_message or message)
    if "401" in lowered or "403" in lowered or "unauthorized" in lowered or "forbidden" in lowered:
        return RuntimeTaskFailure(code="provider_auth_failed", message=provider_message or message)
    if "timed out" in lowered or "timeout" in lowered:
        return RuntimeTaskFailure(code="provider_request_timeout", message=message)
    if (
        "connection refused" in lowered
        or "connection reset" in lowered
        or "connection aborted" in lowered
        or "name or service not known" in lowered
        or "temporary failure in name resolution" in lowered
        or "failed to establish a new connection" in lowered
        or "no route to host" in lowered
    ):
        return RuntimeTaskFailure(code="provider_unreachable", message=message)
    return RuntimeTaskFailure(code="provider_request_failed", message=provider_message or message)


def _provider_error_payload(exc: Exception) -> tuple[str | None, str | None]:
    if not isinstance(exc, httpx.HTTPStatusError):
        return None, None
    try:
        payload: Any = exc.response.json()
    except ValueError:
        return None, _short_text(exc.response.text)
    if not isinstance(payload, dict):
        return None, None
    error = payload.get("error")
    if isinstance(error, dict):
        code = str(error.get("code") or "").strip() or None
        message = str(error.get("message") or "").strip() or None
        return code, message
    message = str(payload.get("message") or payload.get("detail") or "").strip() or None
    return None, message


def _short_text(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:500]
