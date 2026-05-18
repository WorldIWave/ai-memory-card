from datetime import datetime, timezone

from sqlmodel import Session
from sqlmodel import select

from app.api.dependencies import get_evaluation_service
import app.db.models as models
from app.db.session import get_session
from app.main import app
from app.schemas.activity import CardActivityItem
from app.services.activity_service import ActivityService
from app.services.evaluation_service import EvaluationService


def _db_from_memory_client():
    override_get_session = app.dependency_overrides[get_session]
    generator = override_get_session()
    return generator, next(generator)


def _evaluation_result() -> dict[str, object]:
    return {
        "mastery_score": 72,
        "accuracy_score": 80,
        "concept_score": 80,
        "mechanism_score": 65,
        "boundary_score": 55,
        "misconception_score": 20,
        "misconception_detected": False,
        "confidence_score": 88,
        "uncertain": False,
        "feedback": "The core idea is mostly correct, but the mechanism is incomplete.",
        "weak_points": ["mechanism", "boundary"],
        "reinforcement_advice": [
            "Explain why the constraint changes model behavior.",
            "Review the assumptions under which the concept applies.",
        ],
        "rubric_version": "v1",
        "provider_meta": {
            "trace_id": "eval-test-trace",
            "provider_name": "openai_compatible",
            "model": "test-model",
            "latency_ms": 12,
            "context_debug": {
                "evidence_strategy": "rag_payload_context",
                "rag_context_present": True,
                "retrieved_context_count": 2,
                "related_provider_unit_ids": ["ku_regularization_neighbor"],
            },
        },
    }


class FakeEvaluationService:
    def __init__(self) -> None:
        self.last_payload = None

    def evaluate(self, payload, *, card=None, knowledge_unit=None):  # type: ignore[no-untyped-def]
        self.last_payload = payload
        return _evaluation_result()

    def close(self) -> None:
        return None


def test_learning_event_persists_for_a_card(session: Session) -> None:
    deck = models.Deck(name="Activity Deck")
    session.add(deck)
    session.flush()
    assert deck.id is not None

    card = models.Card(
        deck_id=deck.id,
        card_type="recall",
        front="What changed?",
        back="A durable event was stored.",
        render_format="markdown",
    )
    session.add(card)
    session.flush()
    assert card.id is not None

    event = models.LearningEvent(
        card_id=card.id,
        deck_id=deck.id,
        event_type="report_error",
        payload_json={"reason": "content", "note": "definition is incomplete"},
    )
    session.add(event)
    session.commit()

    stored = session.exec(select(models.LearningEvent).where(models.LearningEvent.id == event.id)).one()

    assert stored.id == event.id
    assert stored.card_id == card.id
    assert stored.deck_id == deck.id
    assert stored.event_type == "report_error"
    assert stored.payload_json == {"reason": "content", "note": "definition is incomplete"}
    assert stored.created_at is not None


def test_report_error_creates_learning_event_without_review_log(memory_client) -> None:
    deck = memory_client.post("/api/decks", json={"name": "Algorithms"}).json()
    card = memory_client.post(
        "/api/cards",
        json={
            "deck_id": deck["id"],
            "card_type": "recall",
            "front": "What is overfitting?",
            "back": "When a model memorizes noise.",
            "render_format": "markdown",
            "tags": [],
        },
    ).json()

    response = memory_client.post(
        f"/api/cards/{card['id']}/report",
        json={"reason": "content", "note": "needs a stronger definition"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["event_type"] == "report_error"
    assert payload["summary"] == "Reported issue: content"
    assert payload["payload"] == {"reason": "content", "note": "needs a stronger definition"}

    activity = memory_client.get(f"/api/cards/{card['id']}/activity").json()
    assert activity[0]["event_type"] == "report_error"
    assert activity[0]["payload"] == {"reason": "content", "note": "needs a stronger definition"}

    generator, db = _db_from_memory_client()
    try:
        assert db.exec(select(models.LearningEvent).where(models.LearningEvent.card_id == card["id"])).all() != []
        assert db.exec(select(models.ReviewLog).where(models.ReviewLog.card_id == card["id"])).all() == []
    finally:
        generator.close()


def test_create_note_persists_learning_event_without_review_log(memory_client) -> None:
    deck = memory_client.post("/api/decks", json={"name": "Notes Deck"}).json()
    card = memory_client.post(
        "/api/cards",
        json={
            "deck_id": deck["id"],
            "card_type": "recall",
            "front": "What is batch normalization?",
            "back": "A technique for stabilizing neural network training.",
            "render_format": "markdown",
            "tags": [],
        },
    ).json()

    response = memory_client.post(
        f"/api/cards/{card['id']}/notes",
        json={"note": "Remember to compare with batch norm.", "source": "review"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["event_type"] == "note"
    assert payload["summary"] == "Note added"
    assert payload["payload"] == {"note": "Remember to compare with batch norm.", "source": "review"}

    activity = memory_client.get(f"/api/cards/{card['id']}/activity").json()
    assert activity[0]["event_type"] == "note"


def test_create_note_does_not_mutate_review_state(memory_client) -> None:
    deck = memory_client.post("/api/decks", json={"name": "Note State Deck"}).json()
    card = memory_client.post(
        "/api/cards",
        json={
            "deck_id": deck["id"],
            "card_type": "recall",
            "front": "What is layer normalization?",
            "back": "A normalization method applied across features.",
            "render_format": "markdown",
            "tags": [],
        },
    ).json()

    generator, db = _db_from_memory_client()
    try:
        state = db.exec(select(models.CardReviewState).where(models.CardReviewState.card_id == card["id"])).one()
        snapshot = {
            "interval_days": state.interval_days,
            "repetition_count": state.repetition_count,
            "session_repeats_today": state.session_repeats_today,
            "next_due_at": state.next_due_at,
        }
    finally:
        generator.close()

    response = memory_client.post(
        f"/api/cards/{card['id']}/notes",
        json={"note": "Only a note.", "source": "review"},
    )

    assert response.status_code == 201

    generator, db = _db_from_memory_client()
    try:
        refreshed = db.exec(select(models.CardReviewState).where(models.CardReviewState.card_id == card["id"])).one()
        assert refreshed.interval_days == snapshot["interval_days"]
        assert refreshed.repetition_count == snapshot["repetition_count"]
        assert refreshed.session_repeats_today == snapshot["session_repeats_today"]
        assert refreshed.next_due_at == snapshot["next_due_at"]
        assert db.exec(select(models.ReviewLog).where(models.ReviewLog.card_id == card["id"])).all() == []
    finally:
        generator.close()


def test_evaluation_endpoint_persists_learning_event(memory_client) -> None:
    fake_service = FakeEvaluationService()
    app.dependency_overrides[get_evaluation_service] = lambda: fake_service
    deck = memory_client.post("/api/decks", json={"name": "Evaluation Deck"}).json()
    card = memory_client.post(
        "/api/cards",
        json={
            "deck_id": deck["id"],
            "card_type": "recall",
            "front": "What is regularization?",
            "back": "A technique that reduces overfitting.",
            "render_format": "markdown",
            "tags": [],
        },
    ).json()
    generator, db = _db_from_memory_client()
    try:
        unit = models.KnowledgeUnit(
            deck_id=deck["id"],
            provider_unit_id="ku_regularization",
            topic="Regularization",
            summary="Regularization reduces overfitting by constraining model complexity.",
            source_span={"line_start": 10, "line_end": 18, "text": "regularization"},
            raw_payload={
                "conditions": ["training objective includes a penalty term"],
                "formulas": ["L = L_data + lambda R(theta)"],
                "misconceptions": ["regularization always improves training accuracy"],
            },
        )
        db.add(unit)
        db.flush()
        stored_card = db.get(models.Card, card["id"])
        assert stored_card is not None
        stored_card.knowledge_unit_ref_id = unit.id
        db.add(stored_card)
        db.commit()
        knowledge_unit_id = unit.id
    finally:
        generator.close()

    try:
        response = memory_client.post(
            "/api/evaluations",
            json={
                "card_id": card["id"],
                "target_unit": {"text": "frontend fallback should be replaced"},
                "learner_explanation": "It adds constraints to prevent overfitting.",
            },
        )
    finally:
        app.dependency_overrides.pop(get_evaluation_service, None)

    assert response.status_code == 200
    result = response.json()
    assert result["mastery_score"] == 72
    assert result["accuracy_score"] == 80
    assert result["concept_score"] == 80
    assert result["feedback"] == "The core idea is mostly correct, but the mechanism is incomplete."
    assert fake_service.last_payload is not None
    assert fake_service.last_payload.target_card["front"] == "What is regularization?"
    assert fake_service.last_payload.target_unit["provider_unit_id"] == "ku_regularization"

    activity = memory_client.get(f"/api/cards/{card['id']}/activity").json()
    evaluation_item = next(item for item in activity if item["event_type"] == "evaluation")
    assert evaluation_item["payload"]["kind"] == "understanding_evaluation"
    assert evaluation_item["payload"]["rubric_version"] == "v1"
    assert evaluation_item["payload"]["card_id"] == card["id"]
    assert evaluation_item["payload"]["knowledge_unit_id"] == knowledge_unit_id
    assert evaluation_item["payload"]["knowledge_unit_provider_id"] == "ku_regularization"
    assert evaluation_item["payload"]["learner_explanation"] == "It adds constraints to prevent overfitting."
    assert evaluation_item["payload"]["scores"] == {
        "mastery": 72,
        "accuracy": 80,
        "mechanism": 65,
        "boundary": 55,
        "misconception": 20,
    }
    assert evaluation_item["payload"]["diagnosis"]["weak_points"] == ["mechanism", "boundary"]
    assert evaluation_item["payload"]["diagnosis"]["confidence_score"] == 88
    assert evaluation_item["payload"]["diagnosis"]["uncertain"] is False
    assert evaluation_item["payload"]["provider_meta"]["trace_id"] == "eval-test-trace"
    assert evaluation_item["payload"]["evidence_snapshot"]["evidence_strategy"] == "rag_payload_context"
    assert evaluation_item["payload"]["evidence_snapshot"]["rag_context_present"] is True

    generator, db = _db_from_memory_client()
    try:
        assert db.exec(select(models.ReviewLog).where(models.ReviewLog.card_id == card["id"])).all() == []
    finally:
        generator.close()


def test_evaluation_signal_summary_aggregates_learning_events(session: Session) -> None:
    deck = models.Deck(name="Signal Deck")
    session.add(deck)
    session.flush()
    assert deck.id is not None
    card = models.Card(
        deck_id=deck.id,
        card_type="understanding",
        front="Explain the mechanism.",
        back="Mechanism answer.",
        render_format="markdown",
    )
    session.add(card)
    session.flush()
    assert card.id is not None
    events = [
        models.LearningEvent(
            card_id=card.id,
            deck_id=deck.id,
            event_type="evaluation",
            payload_json={
                "kind": "understanding_evaluation",
                "scores": {"mastery": 40, "accuracy": 50, "mechanism": 30, "boundary": 45, "misconception": 70},
                "diagnosis": {
                    "misconception_detected": True,
                    "confidence_score": 55,
                    "uncertain": True,
                    "weak_points": ["mechanism", "boundary"],
                },
            },
        ),
        models.LearningEvent(
            card_id=card.id,
            deck_id=deck.id,
            event_type="evaluation",
            payload_json={
                "kind": "understanding_evaluation",
                "scores": {"mastery": 80, "accuracy": 85, "mechanism": 75, "boundary": 60, "misconception": 10},
                "diagnosis": {
                    "misconception_detected": False,
                    "confidence_score": 90,
                    "uncertain": False,
                    "weak_points": ["boundary"],
                },
            },
        ),
    ]
    session.add_all(events)
    session.commit()

    summary = ActivityService().evaluation_signal_summary(session, card_id=card.id)

    assert summary["evaluation_count"] == 2
    assert summary["average_scores"]["mastery"] == 60
    assert summary["latest_scores"]["mastery"] == 80
    assert summary["latest_misconception_detected"] is False
    assert summary["weak_point_counts"] == {"boundary": 2, "mechanism": 1}
    assert summary["uncertain_count"] == 1


def test_evaluation_endpoint_enriches_with_related_knowledge_units(memory_client) -> None:
    fake_service = FakeEvaluationService()
    app.dependency_overrides[get_evaluation_service] = lambda: fake_service
    deck = memory_client.post("/api/decks", json={"name": "Evaluation Context"}).json()
    card = memory_client.post(
        "/api/cards",
        json={
            "deck_id": deck["id"],
            "card_type": "recall",
            "front": "What does the score function combine?",
            "back": "A statistical association term and a physical-gradient term.",
            "render_format": "markdown",
            "tags": [],
        },
    ).json()

    generator, db = _db_from_memory_client()
    try:
        main_unit = models.KnowledgeUnit(
            deck_id=deck["id"],
            provider_unit_id="ku_score_function",
            topic="Score function",
            summary="The score function combines statistical association and physical-gradient terms.",
            source_span={"line_start": 50, "line_end": 60, "text": "score function"},
            raw_payload={
                "source_document": "WMidea.md",
                "rag_context": "RAG context says the score function is grounded by data statistics and physics gradients.",
                "retrieved_contexts": [
                    {
                        "source_id": "WMidea.md",
                        "text": "The statistical term and physical-gradient term jointly define the score.",
                    }
                ],
                "question_plans": [{"id": "plan_score_components", "type": "mechanism"}],
                "support_linked_members": [{"id": "support_stats", "text": "Statistical association support"}],
                "relation_linked_members": [{"id": "relation_physics", "text": "Physics gradient relation"}],
            },
        )
        neighbor_unit = models.KnowledgeUnit(
            deck_id=deck["id"],
            provider_unit_id="ku_entropy",
            topic="Entropy term",
            summary="The entropy term constrains the physical-gradient contribution.",
            source_span={"line_start": 61, "line_end": 68, "text": "entropy term"},
            raw_payload={"source_document": "WMidea.md"},
        )
        unrelated_unit = models.KnowledgeUnit(
            deck_id=deck["id"],
            provider_unit_id="ku_other_source",
            topic="Other source",
            summary="This belongs to a different source document.",
            source_span={"line_start": 1, "line_end": 3, "text": "other"},
            raw_payload={"source_document": "other.md"},
        )
        db.add(main_unit)
        db.add(neighbor_unit)
        db.add(unrelated_unit)
        db.flush()
        stored_card = db.get(models.Card, card["id"])
        assert stored_card is not None
        stored_card.knowledge_unit_ref_id = main_unit.id
        db.add(stored_card)
        db.commit()
    finally:
        generator.close()

    try:
        response = memory_client.post(
            "/api/evaluations",
            json={
                "card_id": card["id"],
                "target_unit": {"text": "frontend fallback should be replaced"},
                "learner_explanation": "It combines statistics and a learned physical term.",
                "persist": False,
            },
        )
    finally:
        app.dependency_overrides.pop(get_evaluation_service, None)

    assert response.status_code == 200
    assert fake_service.last_payload is not None
    related_units = fake_service.last_payload.target_unit["related_units"]
    assert [unit["provider_unit_id"] for unit in related_units] == ["ku_entropy"]
    assert related_units[0]["summary"] == "The entropy term constrains the physical-gradient contribution."
    assert fake_service.last_payload.target_unit["rag_context"].startswith("RAG context says")
    assert fake_service.last_payload.target_unit["retrieved_contexts"][0]["source_id"] == "WMidea.md"
    assert fake_service.last_payload.target_unit["question_plans"][0]["id"] == "plan_score_components"
    assert fake_service.last_payload.target_unit["support_linked_members"][0]["id"] == "support_stats"
    assert fake_service.last_payload.target_unit["relation_linked_members"][0]["id"] == "relation_physics"
    assert fake_service.last_payload.target_unit["context_debug"]["evidence_strategy"] == "rag_payload_context"
    assert "related_evidence" in fake_service.last_payload.target_unit["context_debug"]


def test_evaluation_preview_does_not_persist_until_saved(memory_client) -> None:
    fake_service = FakeEvaluationService()
    app.dependency_overrides[get_evaluation_service] = lambda: fake_service
    deck = memory_client.post("/api/decks", json={"name": "Evaluation Preview"}).json()
    card = memory_client.post(
        "/api/cards",
        json={
            "deck_id": deck["id"],
            "card_type": "recall",
            "front": "What is regularization?",
            "back": "A technique that reduces overfitting.",
            "render_format": "markdown",
            "tags": [],
        },
    ).json()

    try:
        preview_response = memory_client.post(
            "/api/evaluations",
            json={
                "card_id": card["id"],
                "target_unit": {"text": card["front"]},
                "learner_explanation": "It adds constraints to prevent overfitting.",
                "persist": False,
            },
        )
    finally:
        app.dependency_overrides.pop(get_evaluation_service, None)

    assert preview_response.status_code == 200
    activity = memory_client.get(f"/api/cards/{card['id']}/activity").json()
    assert [item for item in activity if item["event_type"] == "evaluation"] == []

    save_response = memory_client.post(
        "/api/evaluations/records",
        json={
            "card_id": card["id"],
            "learner_explanation": "It adds constraints to prevent overfitting.",
            "result": preview_response.json(),
        },
    )

    assert save_response.status_code == 201
    saved = save_response.json()
    assert saved["event_type"] == "evaluation"
    assert saved["payload"]["learner_explanation"] == "It adds constraints to prevent overfitting."
    assert saved["payload"]["scores"]["mastery"] == 72


def test_evaluation_endpoint_rejects_missing_card_before_provider_call(memory_client, monkeypatch) -> None:
    def fail_if_called(self, payload):  # type: ignore[no-untyped-def]
        raise AssertionError("evaluation provider should not be called for a missing card")

    monkeypatch.setattr(EvaluationService, "evaluate", fail_if_called)

    response = memory_client.post(
        "/api/evaluations",
        json={
            "card_id": 999999,
            "target_unit": {"text": "missing"},
            "learner_explanation": "This should never reach the provider.",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Card not found"


def test_evaluation_endpoint_returns_stable_plugin_errors(memory_client) -> None:
    class FailingEvaluationService:
        def evaluate(self, payload, *, card=None, knowledge_unit=None):  # type: ignore[no-untyped-def]
            raise RuntimeError("plugin_not_configured: AI plugin is enabled but provider settings are incomplete.")

    app.dependency_overrides[get_evaluation_service] = lambda: FailingEvaluationService()
    deck = memory_client.post("/api/decks", json={"name": "Evaluation Failure"}).json()
    card = memory_client.post(
        "/api/cards",
        json={
            "deck_id": deck["id"],
            "card_type": "recall",
            "front": "What is dropout?",
            "back": "A regularization technique.",
            "render_format": "markdown",
            "tags": [],
        },
    ).json()

    try:
        response = memory_client.post(
            "/api/evaluations",
            json={
                "card_id": card["id"],
                "target_unit": {"text": card["front"]},
                "learner_explanation": "It randomly masks activations.",
            },
        )
    finally:
        app.dependency_overrides.pop(get_evaluation_service, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "plugin_not_configured"


def test_evaluation_events_do_not_appear_in_review_history(memory_client) -> None:
    app.dependency_overrides[get_evaluation_service] = lambda: FakeEvaluationService()
    deck = memory_client.post("/api/decks", json={"name": "Evaluation History"}).json()
    card = memory_client.post(
        "/api/cards",
        json={
            "deck_id": deck["id"],
            "card_type": "recall",
            "front": "What is underfitting?",
            "back": "When a model is too simple to capture patterns.",
            "render_format": "markdown",
            "tags": [],
        },
    ).json()

    response = memory_client.post(
        "/api/evaluations",
        json={
            "card_id": card["id"],
            "target_unit": {"text": card["front"]},
            "learner_explanation": "The model is too simple.",
        },
    )
    app.dependency_overrides.pop(get_evaluation_service, None)
    assert response.status_code == 200

    history = memory_client.get("/api/review/history").json()
    assert history == []


def test_review_history_returns_scheduled_reviews_only(memory_client) -> None:
    app.dependency_overrides[get_evaluation_service] = lambda: FakeEvaluationService()
    deck = memory_client.post("/api/decks", json={"name": "ML"}).json()
    card = memory_client.post(
        "/api/cards",
        json={
            "deck_id": deck["id"],
            "card_type": "recall",
            "front": "Bias vs variance?",
            "back": "Trade-off between error sources.",
            "render_format": "markdown",
            "tags": [],
        },
    ).json()

    session = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck['id']}").json()
    submit_response = memory_client.post(
        f"/api/review/session/{session['session_id']}/submit",
        json={"card_id": card["id"], "grade": "good", "review_mode": "flip_card", "trigger_type": "scheduled"},
    )
    assert submit_response.status_code == 200
    memory_client.post(
        "/api/evaluations",
        json={
            "card_id": card["id"],
            "target_unit": {"text": card["front"]},
            "learner_explanation": "It is the opposite problem of overfitting.",
        },
    )
    app.dependency_overrides.pop(get_evaluation_service, None)
    memory_client.post(
        f"/api/cards/{card['id']}/report",
        json={"reason": "answer", "note": "needs example"},
    )

    history = memory_client.get("/api/review/history").json()
    assert len(history) == 1
    assert history[0]["grade"] == "good"
    assert history[0]["card_id"] == card["id"]
    assert history[0]["deck_id"] == deck["id"]
    assert history[0]["card_front"] == "Bias vs variance?"


def test_report_error_returns_created_event_directly(memory_client, monkeypatch) -> None:
    deck = memory_client.post("/api/decks", json={"name": "Report Direct"}).json()
    card = memory_client.post(
        "/api/cards",
        json={
            "deck_id": deck["id"],
            "card_type": "recall",
            "front": "What is a loss function?",
            "back": "A measure of model error.",
            "render_format": "markdown",
            "tags": [],
        },
    ).json()

    fake_item = CardActivityItem(
        id="fake:1",
        event_type="note",
        created_at=datetime.now(timezone.utc),
        summary="fake activity item",
        payload={"kind": "fake"},
    )
    monkeypatch.setattr(ActivityService, "list_card_activity", lambda self, session, card_id: [fake_item])

    response = memory_client.post(
        f"/api/cards/{card['id']}/report",
        json={"reason": "content", "note": "needs a stronger definition"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["event_type"] == "report_error"
    assert payload["id"].startswith("learning_event:")
    assert payload["summary"] == "Reported issue: content"
    assert payload["payload"] == {"reason": "content", "note": "needs a stronger definition"}

    monkeypatch.undo()
    activity = memory_client.get(f"/api/cards/{card['id']}/activity").json()
    assert activity[0]["id"] == payload["id"]
    assert activity[0]["event_type"] == "report_error"


def test_undone_reviews_are_excluded_from_card_activity_and_history(memory_client) -> None:
    deck = memory_client.post("/api/decks", json={"name": "Undo Visibility"}).json()
    card = memory_client.post(
        "/api/cards",
        json={
            "deck_id": deck["id"],
            "card_type": "recall",
            "front": "What is a gradient?",
            "back": "A direction of steepest ascent.",
            "render_format": "markdown",
            "tags": [],
        },
    ).json()

    session = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck['id']}").json()
    submit_response = memory_client.post(
        f"/api/review/session/{session['session_id']}/submit",
        json={"card_id": card["id"], "grade": "good", "review_mode": "flip_card", "trigger_type": "scheduled"},
    )
    assert submit_response.status_code == 200

    undo_response = memory_client.post(f"/api/review/session/{session['session_id']}/undo")
    assert undo_response.status_code == 200

    activity = memory_client.get(f"/api/cards/{card['id']}/activity").json()
    assert activity == []

    history = memory_client.get("/api/review/history").json()
    assert history == []


def test_review_history_limit_is_bounded(memory_client) -> None:
    response = memory_client.get("/api/review/history?limit=0")
    assert response.status_code == 422

    response = memory_client.get("/api/review/history?limit=201")
    assert response.status_code == 422


def test_report_error_requires_reason(memory_client) -> None:
    deck = memory_client.post("/api/decks", json={"name": "Report Validation"}).json()
    card = memory_client.post(
        "/api/cards",
        json={
            "deck_id": deck["id"],
            "card_type": "recall",
            "front": "What is regularization?",
            "back": "A technique that reduces overfitting.",
            "render_format": "markdown",
            "tags": [],
        },
    ).json()

    response = memory_client.post(
        f"/api/cards/{card['id']}/report",
        json={"note": "needs example"},
    )

    assert response.status_code == 422
