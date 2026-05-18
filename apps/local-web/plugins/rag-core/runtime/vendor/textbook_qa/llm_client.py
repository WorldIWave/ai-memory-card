# Input: chat messages plus OpenAI-compatible endpoint settings.
# Output: model response text from local or remote chat completion APIs.
# Role: share one tiny injectable client across P3 local generation and judge calls.
# Note: no OpenAI SDK dependency; tests inject transport to avoid network access.

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


Transport = Callable[[str, dict[str, Any], dict[str, str], float], dict[str, Any] | str]


class ChatClientRequestError(RuntimeError):
    def __init__(self, *, base_url: str, model: str, attempts: int, retryable: bool, cause: BaseException) -> None:
        self.base_url = base_url
        self.model = model
        self.attempts = attempts
        self.retryable = retryable
        cause_text = str(cause).strip() or cause.__class__.__name__
        super().__init__(
            f"chat completion request failed for model {model} at {base_url} after {attempts} attempt(s): {cause_text}"
        )


class ChatClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 120.0,
        transport: Transport | None = None,
        max_retries: int = 2,
        retry_backoff_seconds: float = 1.0,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self._transport = transport or _urllib_transport
        self._sleep = sleep or time.sleep

    @classmethod
    def from_env(cls, prefix: str, *, transport: Transport | None = None) -> ChatClient:
        return cls(
            base_url=os.environ.get(f"{prefix}_BASE_URL", "").strip(),
            model=os.environ.get(f"{prefix}_MODEL", "").strip(),
            api_key=os.environ.get(f"{prefix}_API_KEY", "").strip(),
            timeout=_float_env(f"{prefix}_TIMEOUT", 120.0),
            transport=transport,
        )

    def is_configured(self) -> bool:
        return bool(self.base_url and self.model)

    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if extra:
            payload.update(extra)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._transport(self._chat_url(), payload, headers, self.timeout)
                return _extract_content(response)
            except Exception as exc:
                retryable = _is_retryable_transport_error(exc)
                if not retryable or attempt > self.max_retries + 1:
                    raise ChatClientRequestError(
                        base_url=self.base_url,
                        model=self.model,
                        attempts=attempt,
                        retryable=retryable,
                        cause=exc,
                    ) from exc
                self._sleep(self.retry_backoff_seconds * (2 ** (attempt - 1)))

    def _chat_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return self.base_url + "/chat/completions"


def _extract_content(response: dict[str, Any] | str) -> str:
    if isinstance(response, str):
        return response.strip()
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict) and message.get("content") is not None:
        return str(message["content"]).strip()
    if first.get("text") is not None:
        return str(first["text"]).strip()
    return ""


def _urllib_transport(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _is_retryable_transport_error(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in {408, 429, 500, 502, 503, 504}
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, socket.gaierror):
            return False
        return isinstance(
            reason,
            (
                TimeoutError,
                ConnectionError,
                ConnectionAbortedError,
                ConnectionRefusedError,
                ConnectionResetError,
                socket.timeout,
                OSError,
            ),
        )
    return isinstance(
        exc,
        (
            TimeoutError,
            ConnectionError,
            ConnectionAbortedError,
            ConnectionRefusedError,
            ConnectionResetError,
            socket.timeout,
        ),
    )


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default
