from __future__ import annotations

import httpx

from app.providers.ai.plugin_client import PluginClient


def test_plugin_client_posts_task_payload() -> None:
    seen_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            200,
            json={
                "task_id": "task-1",
                "status": "succeeded",
                "result": {
                    "deck": {"name": "ML"},
                    "cards": [],
                    "knowledge_units": [],
                    "warnings": [],
                    "provider_meta": {"trace_id": "trace-1"},
                },
                "error": None,
            },
        )

    client = PluginClient(base_url="http://127.0.0.1:8095", client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = client.generate_rag_cards(
        {
            "capability": "rag.generate_cards",
            "mode": "api",
            "provider_profile": "managed_remote_service",
            "deck": {"name": "ML"},
            "documents": [{"filename": "rag.md", "text": "RAG"}],
            "generation_prefs": {"language": "zh", "card_types": ["recall"], "max_cards_per_unit": 3},
        }
    )

    assert seen_request is not None
    assert str(seen_request.url) == "http://127.0.0.1:8095/tasks/rag.generate_cards"
    assert result["provider_meta"]["trace_id"] == "trace-1"


def test_plugin_client_includes_task_error_code_in_raised_exception() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "task_id": "task-2",
                "status": "failed",
                "result": None,
                "error": {
                    "code": "plugin_not_configured",
                    "message": "AI plugin is enabled but provider settings are incomplete.",
                },
            },
        )

    client = PluginClient(base_url="http://127.0.0.1:8095", client=httpx.Client(transport=httpx.MockTransport(handler)))

    try:
        client.generate_rag_cards(
            {
                "capability": "rag.generate_cards",
                "mode": "api",
                "provider_profile": "openai_compatible",
                "deck": {"name": "ML"},
                "documents": [{"filename": "rag.md", "text": "RAG"}],
                "generation_prefs": {"language": "zh"},
            }
        )
    except RuntimeError as exc:
        assert str(exc) == "plugin_not_configured: AI plugin is enabled but provider settings are incomplete."
    else:
        raise AssertionError("expected PluginClient to raise for failed task responses")


def test_plugin_client_can_probe_provider_readiness() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://127.0.0.1:8095/provider/check"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "provider_name": "openai_compatible_local",
                "model": "gpt-4o-mini",
            },
        )

    client = PluginClient(base_url="http://127.0.0.1:8095", client=httpx.Client(transport=httpx.MockTransport(handler)))
    payload = client.test_provider()

    assert payload["ok"] is True
    assert payload["provider_name"] == "openai_compatible_local"


def test_plugin_client_raises_provider_code_when_probe_returns_structured_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://127.0.0.1:8095/provider/check"
        return httpx.Response(
            200,
            json={
                "ok": False,
                "error": {
                    "code": "provider_model_not_found",
                    "message": "No available channel for model gpt-5.3-codex-xhigh",
                },
            },
        )

    client = PluginClient(base_url="http://127.0.0.1:8095", client=httpx.Client(transport=httpx.MockTransport(handler)))

    try:
        client.test_provider()
    except RuntimeError as exc:
        assert str(exc) == "provider_model_not_found: No available channel for model gpt-5.3-codex-xhigh"
    else:
        raise AssertionError("expected PluginClient to raise for failed provider probes")


def test_plugin_client_posts_evaluation_task_payload() -> None:
    seen_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            200,
            json={
                "task_id": "task-eval-1",
                "status": "succeeded",
                "result": {
                    "mastery_score": 72,
                    "accuracy_score": 80,
                    "concept_score": 80,
                    "mechanism_score": 65,
                    "boundary_score": 55,
                    "misconception_score": 20,
                    "misconception_detected": False,
                    "feedback": "Mostly correct.",
                    "weak_points": ["mechanism"],
                    "reinforcement_advice": ["Explain the causal path."],
                    "rubric_version": "v1",
                    "provider_meta": {"trace_id": "eval-trace-1"},
                },
                "error": None,
            },
        )

    client = PluginClient(base_url="http://127.0.0.1:8095", client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = client.score_explanation(
        {
            "capability": "evaluation.score_explanation",
            "mode": "api",
            "target_card": {
                "id": 3,
                "card_type": "understanding",
                "front": "Why regularization?",
                "back": "It constrains model complexity.",
                "tags": [],
            },
            "learner_explanation": "It penalizes large weights.",
        }
    )

    assert seen_request is not None
    assert str(seen_request.url) == "http://127.0.0.1:8095/tasks/evaluation.score_explanation"
    assert result["mastery_score"] == 72
    assert result["provider_meta"]["trace_id"] == "eval-trace-1"


def test_plugin_client_posts_scheduler_task_payload() -> None:
    seen_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            200,
            json={
                "task_id": "task-scheduler-1",
                "status": "succeeded",
                "result": {
                    "scheduler_type": "ai_rl_v1",
                    "interval_days": 3,
                    "confidence": 0.6,
                },
                "error": None,
            },
        )

    client = PluginClient(base_url="http://127.0.0.1:8095", client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = client.plan_review(
        {
            "capability": "scheduler.plan_review",
            "mode": "local",
            "grade": "good",
            "card": {"id": 1},
            "state": {"interval_days": 2},
            "baseline_decision": {"interval_days": 4},
        }
    )

    assert seen_request is not None
    assert str(seen_request.url) == "http://127.0.0.1:8095/tasks/scheduler.plan_review"
    assert result["scheduler_type"] == "ai_rl_v1"
    assert result["interval_days"] == 3


def test_plugin_client_uses_longer_timeout_for_generation_tasks() -> None:
    seen_timeout: float | None = None

    class RecordingClient:
        def post(self, url: str, **kwargs) -> httpx.Response:
            nonlocal seen_timeout
            assert url == "http://127.0.0.1:8095/tasks/rag.generate_cards"
            seen_timeout = kwargs.get("timeout")
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "task_id": "task-3",
                    "status": "succeeded",
                    "result": {"cards": [], "knowledge_units": [], "warnings": [], "provider_meta": {}},
                    "error": None,
                },
            )

        def close(self) -> None:
            return None

    client = PluginClient(base_url="http://127.0.0.1:8095", client=RecordingClient())  # type: ignore[arg-type]
    client.generate_rag_cards(
        {
            "capability": "rag.generate_cards",
            "mode": "api",
            "provider_profile": "openai_compatible",
            "deck": {"name": "ML"},
            "documents": [{"filename": "rag.md", "text": "RAG"}],
            "generation_prefs": {"language": "zh"},
        }
    )

    assert seen_timeout == 1800.0


def test_plugin_client_uses_shorter_timeout_for_provider_probe() -> None:
    seen_timeout: float | None = None

    class RecordingClient:
        def post(self, url: str, **kwargs) -> httpx.Response:
            nonlocal seen_timeout
            assert url == "http://127.0.0.1:8095/provider/check"
            seen_timeout = kwargs.get("timeout")
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={"ok": True, "provider_name": "openai_compatible_local", "model": "demo-model"},
            )

        def close(self) -> None:
            return None

    client = PluginClient(base_url="http://127.0.0.1:8095", client=RecordingClient())  # type: ignore[arg-type]
    client.test_provider()

    assert seen_timeout == 15.0
