# Input: FastAPI TestClient + 内存/磁盘 SQLite  |  Output: HTTP 断言结果
# Role: Deck 与 Card CRUD 及归档/恢复生命周期的集成测试
# Note: 依赖 conftest 的 reset_app_database (autouse) 和 session fixture
# Usage: pytest tests/test_deck_card_api.py
from sqlmodel import Session, select

from app.db.models import Card, CardReviewState, Deck, LearningEvent, ReviewLog
from app.db.session import get_session
from app.db.session import engine
from app.main import app


def _db_from_memory_client():
    override_get_session = app.dependency_overrides[get_session]
    generator = override_get_session()
    return generator, next(generator)


def test_models_can_be_persisted(session) -> None:
    deck = Deck(name="ML Basics", default_scheduler_type="sm2_basic")
    session.add(deck)
    session.commit()
    session.refresh(deck)

    card = Card(
        deck_id=deck.id,
        card_type="recall",
        front="What is attention?",
        back="A mechanism that weights token relevance.",
        render_format="markdown",
        source_type="manual",
        status="active",
        ai_lock_status="user_locked",
        content_version=1,
    )
    session.add(card)
    session.commit()

    assert deck.id is not None
    assert card.id is not None


def test_create_deck_and_card(memory_client) -> None:
    deck_response = memory_client.post("/api/decks", json={"name": "Transformer"})
    assert deck_response.status_code == 201

    deck_id = deck_response.json()["id"]
    card_response = memory_client.post(
        "/api/cards",
        json={
            "deck_id": deck_id,
            "card_type": "recall",
            "front": "What does QKV stand for?",
            "back": "query, key, value",
            "render_format": "markdown",
        },
    )

    assert card_response.status_code == 201
    assert card_response.json()["deck_id"] == deck_id

    card_id = card_response.json()["id"]
    generator, db = _db_from_memory_client()
    try:
        state = db.get(CardReviewState, card_id)
    finally:
        generator.close()

    assert state is not None
    assert state.scheduler_type == "sm2_basic"


def test_archive_and_restore_deck_updates_default_views(memory_client) -> None:
    deck_response = memory_client.post("/api/decks", json={"name": "Lifecycle Deck"})
    assert deck_response.status_code == 201
    deck_id = deck_response.json()["id"]

    card_response = memory_client.post(
        "/api/cards",
        json={
            "deck_id": deck_id,
            "card_type": "recall",
            "front": "Deck lifecycle card",
            "back": "Tracks deck archive flow.",
            "render_format": "markdown",
        },
    )
    assert card_response.status_code == 201
    card_id = card_response.json()["id"]

    archive_response = memory_client.post(f"/api/decks/{deck_id}/archive")
    assert archive_response.status_code == 200
    assert archive_response.json()["visibility"] == "archived"

    decks_response = memory_client.get("/api/decks")
    assert decks_response.status_code == 200
    assert all(deck["id"] != deck_id for deck in decks_response.json())

    all_decks_response = memory_client.get("/api/decks?include_archived=true")
    assert all_decks_response.status_code == 200
    assert any(
        deck["id"] == deck_id and deck["visibility"] == "archived"
        for deck in all_decks_response.json()
    )

    cards_response = memory_client.get("/api/cards")
    assert cards_response.status_code == 200
    assert all(card["id"] != card_id for card in cards_response.json())

    restore_response = memory_client.post(f"/api/decks/{deck_id}/restore")
    assert restore_response.status_code == 200
    assert restore_response.json()["visibility"] == "normal"

    restored_decks_response = memory_client.get("/api/decks")
    assert restored_decks_response.status_code == 200
    assert any(deck["id"] == deck_id for deck in restored_decks_response.json())

    restored_cards_response = memory_client.get("/api/cards")
    assert restored_cards_response.status_code == 200
    assert any(card["id"] == card_id for card in restored_cards_response.json())


def test_delete_deck_permanently_deletes_its_cards_and_related_rows(memory_client) -> None:
    deck_response = memory_client.post("/api/decks", json={"name": "22"})
    assert deck_response.status_code == 201
    deck_id = deck_response.json()["id"]

    card_response = memory_client.post(
        "/api/cards",
        json={
            "deck_id": deck_id,
            "card_type": "recall",
            "front": "What is machine learning?",
            "back": "A system that learns from data.",
            "render_format": "markdown",
        },
    )
    assert card_response.status_code == 201
    card_id = card_response.json()["id"]

    generator, db = _db_from_memory_client()
    try:
        db.add(
            ReviewLog(
                card_id=card_id,
                grade="good",
                interval_days=1,
                ease_factor=2.5,
            )
        )
        db.add(
            LearningEvent(
                card_id=card_id,
                deck_id=deck_id,
                event_type="note",
                payload_json={"note": "delete with deck"},
            )
        )
        db.commit()
    finally:
        generator.close()

    delete_response = memory_client.delete(f"/api/decks/{deck_id}")
    assert delete_response.status_code == 204

    new_deck_response = memory_client.post("/api/decks", json={"name": "11"})
    assert new_deck_response.status_code == 201
    new_deck_id = new_deck_response.json()["id"]

    cards_response = memory_client.get("/api/cards")
    assert cards_response.status_code == 200
    assert all(card["id"] != card_id for card in cards_response.json())
    assert all(card["deck_id"] != new_deck_id for card in cards_response.json())

    generator, db = _db_from_memory_client()
    try:
        assert db.get(Card, card_id) is None
        assert db.get(CardReviewState, card_id) is None
        assert db.exec(select(ReviewLog).where(ReviewLog.card_id == card_id)).first() is None
        assert db.exec(select(LearningEvent).where(LearningEvent.card_id == card_id)).first() is None
    finally:
        generator.close()
