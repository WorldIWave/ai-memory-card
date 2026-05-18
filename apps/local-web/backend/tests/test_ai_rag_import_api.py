# Input: FastAPI TestClient + fake RAG provider  |  Output: /api/ai/rag/import-cards 导入断言
# Role: 验证本地后端能调用远端 RAG 生成契约，并复用 ImportService 落库生成卡片
# Note: 测试通过依赖覆盖注入 fake provider，不访问真实远端 AI 服务
# Usage: pytest tests/test_ai_rag_import_api.py
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from app.api.dependencies import get_rag_import_service
from app.main import app
from app.services.ai_plugin_host_service import AIPluginHostService
from app.services.rag_import_service import RAGImportService


class FakeHost(AIPluginHostService):
    def __init__(self) -> None:
        super().__init__(plugin_root=Path.cwd(), plugin_state_root=Path.cwd())
        self.last_payload: dict[str, object] | None = None

    def run_rag_generate_cards(self, payload: dict[str, object]) -> dict[str, object]:
        self.last_payload = payload
        deck = payload["deck"] if isinstance(payload.get("deck"), dict) else {}
        return {
            "deck": {"name": deck.get("name") or "Generated Deck"},
            "cards": [
                {
                    "card_type": "recall",
                    "front": "What is regularization?",
                    "back": "A method that reduces overfitting.",
                    "render_format": "markdown",
                    "tags": ["ai-generated", "regularization"],
                    "source_unit_id": "ku_regularization",
                }
            ],
            "knowledge_units": [
                {
                    "unit_id": "ku_regularization",
                    "topic": "Regularization",
                    "concept_definition": "A method that reduces overfitting.",
                }
            ],
            "warnings": [],
            "provider_meta": {"trace_id": "rag-test-trace", "provider_name": "fake", "plugin_id": "rag-core"},
        }


def override_rag_import_service() -> Generator[RAGImportService, None, None]:
    yield RAGImportService(plugin_host_service=FakeHost())


def test_ai_rag_import_endpoint_generates_and_imports_cards(memory_client) -> None:
    host = FakeHost()

    def override_service() -> Generator[RAGImportService, None, None]:
        yield RAGImportService(plugin_host_service=host)

    app.dependency_overrides[get_rag_import_service] = override_service
    try:
        response = memory_client.post(
            "/api/ai/rag/import-cards",
            json={
                "deck_name": "Machine Learning",
                "documents": [
                    {
                        "filename": "regularization.md",
                        "content_type": "text/markdown",
                        "text": "Regularization reduces overfitting.",
                    }
                ],
                "topics": ["Regularization"],
                "generation_prefs": {
                    "backend": "extractive",
                    "language": "en",
                    "max_final_questions": 12,
                    "max_candidates": 24,
                    "extractor_batch_mode": "block",
                    "extractor_max_blocks": 36,
                    "extractor_max_tokens": 1200,
                    "candidate_unit_batch_size": 1,
                },
            },
        )
    finally:
        app.dependency_overrides.pop(get_rag_import_service, None)

    assert response.status_code == 201
    payload = response.json()
    assert payload["deck"]["name"] == "Machine Learning"
    assert payload["imported_count"] == 1
    assert payload["cards"][0]["front"] == "What is regularization?"
    assert payload["cards"][0]["tags"] == ["ai-generated", "regularization"]
    assert payload["cards"][0]["knowledge_unit_ref_id"] is not None
    assert payload["knowledge_units"][0]["unit_id"] == "ku_regularization"
    assert payload["provider_meta"]["trace_id"] == "rag-test-trace"
    assert payload["provider_meta"]["plugin_id"] == "rag-core"
    assert host.last_payload is not None
    assert host.last_payload["provider_profile"] == "openai_compatible"
    forwarded_prefs = host.last_payload["generation_prefs"]
    assert isinstance(forwarded_prefs, dict)
    assert forwarded_prefs["max_final_questions"] == 12
    assert forwarded_prefs["max_candidates"] == 24
    assert forwarded_prefs["extractor_batch_mode"] == "block"
    assert forwarded_prefs["extractor_max_blocks"] == 36
    assert forwarded_prefs["extractor_max_tokens"] == 1200
    assert forwarded_prefs["candidate_unit_batch_size"] == 1

    units_response = memory_client.get(f"/api/ai/knowledge-units?deck_id={payload['deck']['id']}")
    assert units_response.status_code == 200
    units = units_response.json()
    assert len(units) == 1
    assert units[0]["id"] == payload["cards"][0]["knowledge_unit_ref_id"]
    assert units[0]["provider_unit_id"] == "ku_regularization"
    assert units[0]["topic"] == "Regularization"
    assert units[0]["summary"] == "A method that reduces overfitting."
    assert units[0]["raw_payload"]["concept_definition"] == "A method that reduces overfitting."


def test_ai_rag_import_endpoint_imports_into_existing_deck(memory_client) -> None:
    host = FakeHost()
    deck_response = memory_client.post("/api/decks", json={"name": "Current Deck"})
    assert deck_response.status_code == 201
    deck = deck_response.json()

    def override_service() -> Generator[RAGImportService, None, None]:
        yield RAGImportService(plugin_host_service=host)

    app.dependency_overrides[get_rag_import_service] = override_service
    try:
        response = memory_client.post(
            "/api/ai/rag/import-cards",
            json={
                "deck_id": deck["id"],
                "deck_name": "Should Not Create A Deck",
                "documents": [
                    {
                        "filename": "regularization.md",
                        "content_type": "text/markdown",
                        "text": "Regularization reduces overfitting.",
                    }
                ],
                "generation_prefs": {"backend": "llm", "language": "en"},
            },
        )
    finally:
        app.dependency_overrides.pop(get_rag_import_service, None)

    assert response.status_code == 201
    payload = response.json()
    assert payload["deck"]["id"] == deck["id"]
    assert payload["deck"]["name"] == "Current Deck"
    assert payload["imported_count"] == 1
    assert payload["cards"][0]["deck_id"] == deck["id"]
    assert payload["cards"][0]["front"] == "What is regularization?"

    decks = memory_client.get("/api/decks").json()
    assert [item["name"] for item in decks].count("Current Deck") == 1
    assert all(item["name"] != "Should Not Create A Deck" for item in decks)

    assert host.last_payload is not None
    assert host.last_payload["deck"] == {"name": "Current Deck"}


def test_ai_rag_import_endpoint_rejects_blank_document(memory_client) -> None:
    response = memory_client.post(
        "/api/ai/rag/import-cards",
        json={
            "documents": [{"filename": "blank.md", "text": "   "}],
        },
    )

    assert response.status_code == 422


def test_ai_rag_import_endpoint_returns_503_when_plugin_is_not_ready(memory_client) -> None:
    class FailingService(RAGImportService):
        def import_generated_cards(self, session, payload):
            raise RuntimeError("plugin_not_configured")

    app.dependency_overrides[get_rag_import_service] = lambda: FailingService(plugin_host_service=FakeHost())
    try:
        response = memory_client.post(
            "/api/ai/rag/import-cards",
            json={
                "documents": [
                    {
                        "filename": "regularization.md",
                        "content_type": "text/markdown",
                        "text": "Regularization reduces overfitting.",
                    }
                ],
            },
        )
    finally:
        app.dependency_overrides.pop(get_rag_import_service, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "plugin_not_configured"
