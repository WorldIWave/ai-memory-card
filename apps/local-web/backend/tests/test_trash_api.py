# Input: 内存 SQLite 数据库、FastAPI app  |  Output: 无（pytest 断言副作用）
# Role: 集成测试卡片软删除流程（archive → trash → restore）及边界情况
# Note: 使用 client_with_memory_db 上下文管理器隔离数据库，测试间互不影响
# Usage: pytest tests/test_trash_api.py
from contextlib import contextmanager
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.db.models import Card, Deck
from app.db.session import get_session
from app.main import app


@contextmanager
def client_with_memory_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    previous_override = app.dependency_overrides.get(get_session)

    def override_get_session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_session] = override_get_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous_override
        engine.dispose()


def test_card_deleted_at_nullable_timestamp_persists(session) -> None:
    deck = Deck(name="Trash", default_scheduler_type="sm2_basic")
    session.add(deck)
    session.commit()
    session.refresh(deck)

    deleted_at = datetime(2026, 4, 3, 9, 0)
    card = Card(
        deck_id=deck.id,
        card_type="recall",
        front="What is soft delete?",
        back="A logical delete that marks rows as archived.",
        render_format="markdown",
        source_type="manual",
        status="active",
        ai_lock_status="user_locked",
        content_version=1,
        deleted_at=None,
    )

    session.add(card)
    session.commit()
    session.refresh(card)
    assert card.deleted_at is None

    card.deleted_at = deleted_at
    session.add(card)
    session.commit()
    session.refresh(card)
    assert card.deleted_at == deleted_at


def test_archive_restore_trash_flow() -> None:
    with client_with_memory_db() as client:
        deck_response = client.post("/api/decks", json={"name": "Trash"})
        assert deck_response.status_code == 201
        deck_id = deck_response.json()["id"]

        card_response = client.post(
            "/api/cards",
            json={
                "deck_id": deck_id,
                "card_type": "recall",
                "front": "What is soft delete?",
                "back": "A logical delete that marks rows as archived.",
                "render_format": "markdown",
            },
        )
        assert card_response.status_code == 201
        card_id = card_response.json()["id"]

        archive_response = client.post(f"/api/cards/{card_id}/archive")
        assert archive_response.status_code == 200

        trash_response = client.get("/api/trash")
        assert trash_response.status_code == 200
        assert any(row["id"] == card_id for row in trash_response.json())

        cards_response = client.get("/api/cards")
        assert cards_response.status_code == 200
        assert all(row["id"] != card_id for row in cards_response.json())

        restore_response = client.post(f"/api/cards/{card_id}/restore")
        assert restore_response.status_code == 200

        restored_cards_response = client.get("/api/cards")
        assert restored_cards_response.status_code == 200
        assert any(row["id"] == card_id for row in restored_cards_response.json())

        restored_trash_response = client.get("/api/trash")
        assert restored_trash_response.status_code == 200
        assert all(row["id"] != card_id for row in restored_trash_response.json())


def test_archived_cards_are_hidden_from_default_card_list() -> None:
    with client_with_memory_db() as client:
        deck_response = client.post("/api/decks", json={"name": "Trash"})
        assert deck_response.status_code == 201

        deck_id = deck_response.json()["id"]
        card_response = client.post(
            "/api/cards",
            json={
                "deck_id": deck_id,
                "card_type": "recall",
                "front": "What is soft delete?",
                "back": "A logical delete that marks rows as archived.",
                "render_format": "markdown",
            },
        )
        assert card_response.status_code == 201

        card_id = card_response.json()["id"]
        archive_response = client.post(f"/api/cards/{card_id}/archive")
        assert archive_response.status_code == 200

        cards_response = client.get("/api/cards")
        assert cards_response.status_code == 200
        assert all(row["id"] != card_id for row in cards_response.json())


def test_archive_card_returns_404_for_unknown_card() -> None:
    with client_with_memory_db() as client:
        response = client.post("/api/cards/9999/archive")
    assert response.status_code == 404


def test_restore_card_returns_404_for_unknown_card() -> None:
    with client_with_memory_db() as client:
        response = client.post("/api/cards/9999/restore")
    assert response.status_code == 404


def test_permanently_delete_archived_card_from_trash() -> None:
    with client_with_memory_db() as client:
        deck_response = client.post("/api/decks", json={"name": "Trash"})
        assert deck_response.status_code == 201
        deck_id = deck_response.json()["id"]

        card_response = client.post(
            "/api/cards",
            json={
                "deck_id": deck_id,
                "card_type": "recall",
                "front": "Hard delete me",
                "back": "Gone for good.",
                "render_format": "markdown",
            },
        )
        assert card_response.status_code == 201
        card_id = card_response.json()["id"]

        assert client.post(f"/api/cards/{card_id}/archive").status_code == 200

        delete_response = client.delete(f"/api/trash/{card_id}")
        assert delete_response.status_code == 204

        trash_response = client.get("/api/trash")
        assert trash_response.status_code == 200
        assert all(row["id"] != card_id for row in trash_response.json())

        restore_response = client.post(f"/api/cards/{card_id}/restore")
        assert restore_response.status_code == 404


def test_clear_trash_permanently_deletes_only_archived_cards() -> None:
    with client_with_memory_db() as client:
        deck_response = client.post("/api/decks", json={"name": "Trash"})
        assert deck_response.status_code == 201
        deck_id = deck_response.json()["id"]

        active_response = client.post(
            "/api/cards",
            json={
                "deck_id": deck_id,
                "card_type": "recall",
                "front": "Keep me",
                "back": "Still active.",
                "render_format": "markdown",
            },
        )
        archived_response = client.post(
            "/api/cards",
            json={
                "deck_id": deck_id,
                "card_type": "recall",
                "front": "Delete me",
                "back": "Archived.",
                "render_format": "markdown",
            },
        )
        assert active_response.status_code == 201
        assert archived_response.status_code == 201
        active_id = active_response.json()["id"]
        archived_id = archived_response.json()["id"]

        assert client.post(f"/api/cards/{archived_id}/archive").status_code == 200

        clear_response = client.delete("/api/trash")
        assert clear_response.status_code == 200
        assert clear_response.json() == {"deleted_count": 1}

        cards_response = client.get("/api/cards")
        assert cards_response.status_code == 200
        card_ids = {row["id"] for row in cards_response.json()}
        assert active_id in card_ids
        assert archived_id not in card_ids
