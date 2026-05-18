from __future__ import annotations

import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile

from fastapi.testclient import TestClient
import httpx
import pytest

from runtime.app.config import load_runtime_config
from runtime.app.errors import map_runtime_exception
from runtime.app.main import app
from runtime.app.pipeline_service import generate_cards_from_documents


def test_health_route_reports_plugin_identity() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["plugin_id"] == "rag-core"
    assert payload["protocol_version"] == "1"
    assert payload["configuration"]["provider_profile"] == "openai_compatible"
    assert "base_url" in payload["configuration"]
    assert "managed_remote_base_url" not in payload["configuration"]


def test_provider_check_route_uses_openai_compatible_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    captured: dict[str, object] = {}

    def fake_request(provider_meta, messages):
        captured["provider_meta"] = provider_meta
        captured["messages"] = messages
        return {"ok": True}

    base_dir = Path.cwd() / ".pytest-temp"
    base_dir.mkdir(exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(dir=base_dir))
    config_path = temp_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-test",
                "model": "gpt-4o-mini",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LMCA_PLUGIN_CONFIG_PATH", str(config_path))
    monkeypatch.setattr("runtime.app.pipeline_service._request_openai_json", fake_request)
    try:
        response = client.post("/provider/check")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["provider_name"] == "openai_compatible_local"
    assert captured["provider_meta"]["base_url"] == "https://api.example.com/v1"
    assert captured["provider_meta"]["model"] == "gpt-4o-mini"
    assert captured["messages"][0]["role"] == "system"


def test_provider_check_route_returns_structured_failure_for_model_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)

    def fake_request(provider_meta, messages):
        del provider_meta, messages
        request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
        response = httpx.Response(
            503,
            request=request,
            json={
                "error": {
                    "code": "model_not_found",
                    "message": "No available channel for model gpt-5.3-codex-xhigh",
                    "type": "new_api_error",
                }
            },
        )
        raise httpx.HTTPStatusError("Server error", request=request, response=response)

    base_dir = Path.cwd() / ".pytest-temp"
    base_dir.mkdir(exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(dir=base_dir))
    config_path = temp_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-test",
                "model": "gpt-5.3-codex-xhigh",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LMCA_PLUGIN_CONFIG_PATH", str(config_path))
    monkeypatch.setattr("runtime.app.pipeline_service._request_openai_json", fake_request)
    try:
        response = client.post("/provider/check")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "provider_model_not_found"
    assert "No available channel" in payload["error"]["message"]
    assert payload["model"] == "gpt-5.3-codex-xhigh"


def test_capabilities_route_exposes_error_state_fields() -> None:
    client = TestClient(app)

    response = client.get("/capabilities")

    assert response.status_code == 200
    configuration = response.json()["configuration"]
    assert "last_error_code" in configuration
    assert "last_error_summary" in configuration
    assert "base_url" in configuration
    assert "managed_remote_base_url" not in configuration


def test_capabilities_route_includes_evaluation_score_explanation() -> None:
    client = TestClient(app)

    response = client.get("/capabilities")

    assert response.status_code == 200
    capability_names = {item["name"] for item in response.json()["capabilities"]}
    assert "rag.generate_cards" in capability_names
    assert "evaluation.score_explanation" in capability_names


@pytest.mark.parametrize(
    ("message", "expected_code"),
    [
        ("401 Client Error: Unauthorized for url: https://api.example.com/v1/chat/completions", "provider_auth_failed"),
        ("403 Client Error: Forbidden for url: https://api.example.com/v1/chat/completions", "provider_auth_failed"),
        ("model_not_found: No available channel for model gpt-5.3-codex-xhigh", "provider_model_not_found"),
        ("chat completion request failed for model qwen at https://api.example.com after 3 attempt(s): timed out", "provider_request_timeout"),
        ("api_llm request failed: connection refused", "provider_unreachable"),
    ],
)
def test_runtime_exception_mapping_uses_stable_provider_error_codes(message: str, expected_code: str) -> None:
    mapped = map_runtime_exception(RuntimeError(message))

    assert mapped.code == expected_code
    assert mapped.message


def test_load_runtime_config_prefers_plugin_config_file(monkeypatch: pytest.MonkeyPatch) -> None:
    base_dir = Path.cwd() / ".pytest-temp"
    base_dir.mkdir(exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(dir=base_dir))
    try:
        config_path = temp_dir / "config.json"
        config_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-config",
                "model": "gpt-4o-mini",
            },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("LMCA_PLUGIN_CONFIG_PATH", str(config_path))
        monkeypatch.setenv("LMCA_RAG_BASE_URL", "https://env.example.com/v1")
        monkeypatch.setenv("LMCA_RAG_API_KEY", "sk-env")
        monkeypatch.setenv("LMCA_RAG_MODEL", "env-model")

        config = load_runtime_config()

        assert config.base_url == "https://api.example.com/v1"
        assert config.api_key == "sk-config"
        assert config.model == "gpt-4o-mini"
        assert config.enabled is True
        assert config.available_provider_profiles() == ["openai_compatible"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_generate_cards_from_documents_runs_full_p3_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    from textbook_qa.schemas import QuestionType

    captured: dict[str, object] = {}

    class FakeApiLlmProvider:
        def __init__(self, settings):
            captured["extractor_settings"] = settings

    class FakeChatClient:
        def __init__(self, **kwargs):
            captured["chat_client_settings"] = kwargs

    def fake_run_p3_file_pipeline(input_path, output_dir, **kwargs):
        captured["input_text"] = Path(input_path).read_text(encoding="utf-8")
        captured["output_dir"] = output_dir
        captured["pipeline_kwargs"] = kwargs
        fake_seed = SimpleNamespace(id="seed_regularization", title="Regularization", statement="Reduces overfitting.")
        fake_unit_type = SimpleNamespace(value="concept")
        fake_context = SimpleNamespace(
            source_id="ml.md",
            block_id="block-7",
            text="Regularization adds a penalty term that constrains model complexity.",
            line_start=7,
            line_end=12,
            heading_path=["Chapter 1", "Regularization"],
            metadata={"score": 0.92},
        )
        fake_unit = SimpleNamespace(
            id="rag_regularization",
            title="Regularization",
            seed_point=fake_seed,
            concept_id="regularization",
            type=fake_unit_type,
            results=["Reduces overfitting."],
            conditions=[],
            formulas=[],
            misconceptions=[],
            examples=[],
            primary_evidence=None,
            retrieved_contexts=[fake_context],
            merged_context_text="RAG context: regularization constrains model complexity through a penalty term.",
            question_plans=[{"id": "plan_regularization_mechanism", "type": "mechanism"}],
            metadata={
                "grounding_context": {"source_block_ids": ["block-7"]},
                "concept_unit": {
                    "support_linked_members": [{"id": "support_penalty", "text": "Penalty term evidence"}],
                    "relation_linked_members": [{"id": "relation_overfit", "text": "Relation to overfitting"}],
                },
            },
        )
        fake_pair = SimpleNamespace(
            question="What does regularization do?",
            answer="It reduces overfitting.",
            question_type=QuestionType.DEFINITION,
            metadata={"source_unit_id": "rag_regularization"},
            concepts=[],
        )
        return SimpleNamespace(
            result=SimpleNamespace(
                qa_pairs=[fake_pair],
                artifacts=SimpleNamespace(warnings=["used_full_pipeline_mock"]),
            ),
            rag_units=[fake_unit],
            generation_rag_units=[fake_unit],
            runtime_metrics={"counts": {"final_pair_count": 1, "generation_rag_unit_count": 1}},
        )

    def simplified_prompt_path_should_not_run(*args, **kwargs):
        raise AssertionError("rag-core must call the Textbook QA P3 pipeline, not the simplified prompt path")

    monkeypatch.setattr("runtime.app.pipeline_service.ApiLlmProvider", FakeApiLlmProvider, raising=False)
    monkeypatch.setattr("runtime.app.pipeline_service.ChatClient", FakeChatClient, raising=False)
    monkeypatch.setattr("runtime.app.pipeline_service.run_p3_file_pipeline", fake_run_p3_file_pipeline, raising=False)
    monkeypatch.setattr("runtime.app.pipeline_service._request_openai_json", simplified_prompt_path_should_not_run)

    result = generate_cards_from_documents(
        documents=[{"filename": "../nested/../../ml.md", "content_type": "text/markdown", "text": "regularization"}],
        deck_name="ML",
        topics=None,
        generation_prefs={
            "language": "zh",
            "card_types": ["recall"],
            "max_cards_per_unit": 3,
            "max_final_questions": 12,
            "max_candidates": 24,
            "extractor_batch_mode": "block",
            "extractor_max_blocks": 36,
            "extractor_max_tokens": 1200,
        },
        provider_settings={"base_url": "https://api.example.com/v1", "api_key": "sk-test", "model": "gpt-4o-mini"},
    )

    assert result["deck"]["name"] == "ML"
    assert result["provider_meta"]["mode"] == "api"
    assert result["warnings"] == ["used_full_pipeline_mock"]
    assert result["cards"][0]["front"] == "What does regularization do?"
    knowledge_unit = result["knowledge_units"][0]
    assert knowledge_unit["provider_rag_unit_id"] == "rag_regularization"
    assert knowledge_unit["rag_context"].startswith("RAG context: regularization")
    assert knowledge_unit["retrieved_contexts"][0]["text"].startswith("Regularization adds a penalty")
    assert knowledge_unit["question_plans"][0]["id"] == "plan_regularization_mechanism"
    assert knowledge_unit["support_linked_members"][0]["id"] == "support_penalty"
    assert knowledge_unit["relation_linked_members"][0]["id"] == "relation_overfit"
    assert result["provider_meta"]["runtime_metrics"]["counts"]["final_pair_count"] == 1
    assert "regularization" in str(captured["input_text"]).lower()
    assert captured["extractor_settings"]["api_key"] == "sk-test"
    assert captured["extractor_settings"]["batch_mode"] == "token-window"
    assert captured["extractor_settings"]["max_chars"] == 16000
    assert result["provider_meta"]["adaptive_batching"]["strategy"] == "single-pass"
    assert captured["pipeline_kwargs"]["max_final_questions"] == 12
    assert captured["pipeline_kwargs"]["max_candidates"] == 24
    assert captured["pipeline_kwargs"]["candidate_unit_batch_size"] == 6
    assert captured["pipeline_kwargs"]["judge_max_pairs_per_call"] == 20
    assert captured["pipeline_kwargs"]["candidate_prompt_profile"] == "api_simple"
    assert captured["pipeline_kwargs"]["candidate_filter_profile"] == "skip_qa_guard"


def test_generate_cards_keeps_cards_when_topic_filter_matches_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    from textbook_qa.schemas import QuestionType

    class FakeApiLlmProvider:
        def __init__(self, settings):
            self.settings = settings

    class FakeChatClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def fake_run_p3_file_pipeline(input_path, output_dir, **kwargs):
        fake_seed = SimpleNamespace(id="seed_regularization", title="Regularization", statement="Reduces overfitting.")
        fake_unit_type = SimpleNamespace(value="concept")
        fake_unit = SimpleNamespace(
            id="rag_regularization",
            title="Regularization",
            seed_point=fake_seed,
            concept_id="regularization",
            type=fake_unit_type,
            results=["Reduces overfitting."],
            conditions=[],
            formulas=[],
            misconceptions=[],
            examples=[],
            primary_evidence=None,
            metadata={},
        )
        fake_pair = SimpleNamespace(
            question="What does regularization do?",
            answer="It reduces overfitting.",
            question_type=QuestionType.DEFINITION,
            metadata={"source_unit_id": "rag_regularization"},
            concepts=[],
        )
        return SimpleNamespace(
            result=SimpleNamespace(qa_pairs=[fake_pair], artifacts=SimpleNamespace(warnings=[])),
            rag_units=[fake_unit],
            generation_rag_units=[fake_unit],
            runtime_metrics={"counts": {"final_pair_count": 1}},
        )

    monkeypatch.setattr("runtime.app.pipeline_service.ApiLlmProvider", FakeApiLlmProvider, raising=False)
    monkeypatch.setattr("runtime.app.pipeline_service.ChatClient", FakeChatClient, raising=False)
    monkeypatch.setattr("runtime.app.pipeline_service.run_p3_file_pipeline", fake_run_p3_file_pipeline, raising=False)

    result = generate_cards_from_documents(
        documents=[{"filename": "ml.md", "content_type": "text/markdown", "text": "regularization"}],
        deck_name="ML",
        topics=["World model"],
        generation_prefs={"language": "en", "card_types": ["recall"], "max_cards_per_unit": 3},
        provider_settings={"base_url": "https://api.example.com/v1", "api_key": "sk-test", "model": "gpt-4o-mini"},
    )

    assert len(result["cards"]) == 1
    assert result["cards"][0]["front"] == "What does regularization do?"
    assert "topic filter matched no generated cards; kept the full generated result" in result["warnings"]


def test_task_route_reports_provider_not_configured_when_plugin_config_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    base_dir = Path.cwd() / ".pytest-temp"
    base_dir.mkdir(exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(dir=base_dir))
    config_path = temp_dir / "config.json"
    config_path.write_text(json.dumps({"enabled": True, "base_url": "https://api.example.com/v1"}), encoding="utf-8")
    monkeypatch.setenv("LMCA_PLUGIN_CONFIG_PATH", str(config_path))
    try:
        response = client.post(
            "/tasks/rag.generate_cards",
            json={
                "capability": "rag.generate_cards",
                "mode": "api",
                "provider_profile": "openai_compatible",
                "deck": {"name": "ML"},
                "documents": [{"filename": "rag.md", "content_type": "text/markdown", "text": "RAG"}],
                "generation_prefs": {"language": "zh", "card_types": ["recall"], "max_cards_per_unit": 3},
            },
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "plugin_not_configured"


def test_evaluation_task_route_normalizes_valid_model_json(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    base_dir = Path.cwd() / ".pytest-temp"
    base_dir.mkdir(exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(dir=base_dir))
    config_path = temp_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-test",
                "model": "gpt-4o-mini",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fake_request(provider_meta, messages):
        assert provider_meta["model"] == "gpt-4o-mini"
        assert "strict but helpful cognitive diagnosis judge" in messages[0]["content"]
        assert "knowledge-unit context and RAG-derived context are the primary evidence" in messages[0]["content"]
        context = json.loads(messages[1]["content"])
        assert context["target_unit"]["summary"] == "Regularization constrains model complexity."
        assert context["target_unit"]["rag_context"] == "Regularization is grounded in the generated RAG context."
        assert context["target_unit"]["related_units"][0]["summary"] == "Penalty terms are related evidence."
        assert "target_unit.rag_context" in context["evaluation_policy"]["primary_evidence_order"]
        assert context["evaluation_policy"]["rag_context_role"].startswith("Use RAG-derived context")
        assert context["evaluation_policy"]["related_context_role"].startswith("Use target_unit.related_units")
        assert context["evaluation_policy"]["reference_answer_role"].startswith("target_card.back is a reference")
        assert context["evaluation_policy"]["misconception_threshold"].startswith("Only mark misconception")
        return {
            "mastery_score": 72,
            "accuracy_score": 80,
            "mechanism_score": 65,
            "boundary_score": 55,
            "misconception_score": 20,
            "misconception_detected": False,
            "confidence_score": 88,
            "uncertain": False,
            "feedback": "The core idea is mostly correct.",
            "weak_points": ["mechanism", "boundary"],
            "reinforcement_advice": ["Explain the penalty term."],
        }

    monkeypatch.setenv("LMCA_PLUGIN_CONFIG_PATH", str(config_path))
    monkeypatch.setattr("runtime.app.pipeline_service._request_openai_json", fake_request)
    try:
        response = client.post(
            "/tasks/evaluation.score_explanation",
            json={
                "capability": "evaluation.score_explanation",
                "mode": "api",
                "rubric_version": "v1",
                "target_card": {
                    "id": 12,
                    "card_type": "understanding",
                    "front": "Why does regularization reduce overfitting?",
                    "back": "It constrains the hypothesis space.",
                    "tags": ["regularization"],
                },
                "target_unit": {
                    "id": 3,
                    "provider_unit_id": "ku_regularization",
                    "topic": "Regularization",
                    "summary": "Regularization constrains model complexity.",
                    "source_span": {"line_start": 10, "line_end": 18, "text": "..."},
                    "raw_payload": {"formulas": ["L = L_data + lambda R(theta)"]},
                    "rag_context": "Regularization is grounded in the generated RAG context.",
                    "retrieved_contexts": [{"text": "A retrieved paragraph about penalty terms."}],
                    "support_linked_members": [{"id": "support_penalty"}],
                    "related_units": [
                        {
                            "provider_unit_id": "ku_penalty",
                            "topic": "Penalty terms",
                            "summary": "Penalty terms are related evidence.",
                        }
                    ],
                },
                "learner_explanation": "It penalizes large weights.",
            },
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    result = payload["result"]
    assert result["mastery_score"] == 72
    assert result["accuracy_score"] == 80
    assert result["concept_score"] == 80
    assert result["mechanism_score"] == 65
    assert result["boundary_score"] == 55
    assert result["misconception_score"] == 20
    assert result["misconception_detected"] is False
    assert result["confidence_score"] == 88
    assert result["uncertain"] is False
    assert result["weak_points"] == ["mechanism", "boundary"]
    assert result["reinforcement_advice"] == ["Explain the penalty term."]
    assert result["rubric_version"] == "v1"
    assert result["provider_meta"]["provider_name"] == "openai_compatible"
    assert result["provider_meta"]["model"] == "gpt-4o-mini"
    assert result["provider_meta"]["trace_id"].startswith("eval-")
    assert result["provider_meta"]["context_debug"]["target_unit_provider_id"] == "ku_regularization"
    assert result["provider_meta"]["context_debug"]["related_evidence_count"] == 1
    assert result["provider_meta"]["context_debug"]["related_provider_unit_ids"] == ["ku_penalty"]
    assert result["provider_meta"]["context_debug"]["rag_context_present"] is True
    assert result["provider_meta"]["context_debug"]["retrieved_context_count"] == 1
    assert result["provider_meta"]["context_debug"]["support_linked_member_count"] == 1


def test_evaluation_task_route_returns_parse_error_for_invalid_model_json(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    base_dir = Path.cwd() / ".pytest-temp"
    base_dir.mkdir(exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(dir=base_dir))
    config_path = temp_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-test",
                "model": "gpt-4o-mini",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("LMCA_PLUGIN_CONFIG_PATH", str(config_path))
    monkeypatch.setattr("runtime.app.pipeline_service._request_openai_json", lambda _provider, _messages: {"feedback": "missing scores"})
    try:
        response = client.post(
            "/tasks/evaluation.score_explanation",
            json={
                "capability": "evaluation.score_explanation",
                "mode": "api",
                "rubric_version": "v1",
                "target_card": {
                    "id": 12,
                    "card_type": "understanding",
                    "front": "Why does regularization reduce overfitting?",
                    "back": "It constrains the hypothesis space.",
                    "tags": [],
                },
                "learner_explanation": "It penalizes large weights.",
            },
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "evaluation_parse_failed"


def test_evaluation_task_route_reports_provider_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    base_dir = Path.cwd() / ".pytest-temp"
    base_dir.mkdir(exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(dir=base_dir))
    config_path = temp_dir / "config.json"
    config_path.write_text(json.dumps({"enabled": True, "base_url": "https://api.example.com/v1"}), encoding="utf-8")
    monkeypatch.setenv("LMCA_PLUGIN_CONFIG_PATH", str(config_path))
    try:
        response = client.post(
            "/tasks/evaluation.score_explanation",
            json={
                "capability": "evaluation.score_explanation",
                "mode": "api",
                "target_card": {
                    "id": 12,
                    "card_type": "understanding",
                    "front": "Why does regularization reduce overfitting?",
                    "back": "It constrains the hypothesis space.",
                    "tags": [],
                },
                "learner_explanation": "It penalizes large weights.",
            },
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "plugin_not_configured"
