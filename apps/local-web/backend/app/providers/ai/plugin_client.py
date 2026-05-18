from __future__ import annotations

import httpx

_PLUGIN_PROVIDER_TEST_TIMEOUT_SECONDS = 15.0
_PLUGIN_GENERATE_TIMEOUT_SECONDS = 1800.0
_PLUGIN_EVALUATION_TIMEOUT_SECONDS = 120.0
_PLUGIN_SCHEDULER_TIMEOUT_SECONDS = 30.0


class PluginClient:
    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self.client = client or httpx.Client()

    def generate_rag_cards(self, payload: dict[str, object]) -> dict[str, object]:
        return self._post_task(
            "/tasks/rag.generate_cards",
            payload,
            timeout=_PLUGIN_GENERATE_TIMEOUT_SECONDS,
        )

    def score_explanation(self, payload: dict[str, object]) -> dict[str, object]:
        return self._post_task(
            "/tasks/evaluation.score_explanation",
            payload,
            timeout=_PLUGIN_EVALUATION_TIMEOUT_SECONDS,
        )

    def plan_review(self, payload: dict[str, object]) -> dict[str, object]:
        return self._post_task(
            "/tasks/scheduler.plan_review",
            payload,
            timeout=_PLUGIN_SCHEDULER_TIMEOUT_SECONDS,
        )

    def _post_task(self, path: str, payload: dict[str, object], *, timeout: float) -> dict[str, object]:
        try:
            response = self.client.post(
                f"{self.base_url}{path}",
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"plugin_runtime_request_failed: {exc}") from exc
        task = response.json()
        if task.get("status") != "succeeded":
            error = task.get("error") or {}
            code = error.get("code") if isinstance(error, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            if code and message:
                raise RuntimeError(f"{code}: {message}")
            if code:
                raise RuntimeError(str(code))
            raise RuntimeError(str(message or "Plugin task failed"))
        result = task.get("result")
        return result if isinstance(result, dict) else {}

    def test_provider(self) -> dict[str, object]:
        try:
            response = self.client.post(
                f"{self.base_url}/provider/check",
                timeout=_PLUGIN_PROVIDER_TEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"plugin_runtime_request_failed: {exc}") from exc
        payload = response.json()
        if isinstance(payload, dict) and (payload.get("ok") is False or payload.get("error")):
            error = payload.get("error") or {}
            code = error.get("code") if isinstance(error, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            if code and message:
                raise RuntimeError(f"{code}: {message}")
            if code:
                raise RuntimeError(str(code))
            raise RuntimeError(str(message or "Provider check failed"))
        return payload if isinstance(payload, dict) else {}

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
