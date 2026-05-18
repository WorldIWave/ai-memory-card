from app.db.models import Card, CardReviewState, Deck
from app.db.session import get_session
from app.main import app


def _db_from_memory_client():
    override_get_session = app.dependency_overrides[get_session]
    generator = override_get_session()
    return generator, next(generator)


def test_update_card_changes_content_and_preserves_review_state(memory_client) -> None:
    generator, db = _db_from_memory_client()
    try:
        deck = Deck(name="Cards", default_scheduler_type="sm2_basic")
        db.add(deck)
        db.commit()
        db.refresh(deck)

        card = Card(
            deck_id=deck.id,
            card_type="recall",
            front="Old question",
            back="Old answer",
            render_format="markdown",
            tags=["old"],
            content_version=1,
        )
        db.add(card)
        db.commit()
        db.refresh(card)

        state = CardReviewState(card_id=card.id, interval_days=3, repetition_count=2)
        db.add(state)
        db.commit()
        card_id = card.id
        deck_id = deck.id
    finally:
        generator.close()

    response = memory_client.put(
        f"/api/cards/{card_id}",
        json={
            "deck_id": deck_id,
            "card_type": "cloze",
            "front": "New {{c1::question}}",
            "back": "New answer",
            "render_format": "markdown",
            "tags": ["new", "edited"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["front"] == "New {{c1::question}}"
    assert payload["back"] == "New answer"
    assert payload["card_type"] == "cloze"
    assert payload["tags"] == ["new", "edited"]
    assert payload["content_version"] == 2

    generator, db = _db_from_memory_client()
    try:
        state = db.get(CardReviewState, card.id)
        assert state is not None
        assert state.interval_days == 3
        assert state.repetition_count == 2
    finally:
        generator.close()


def test_update_card_rejects_missing_deck(memory_client) -> None:
    generator, db = _db_from_memory_client()
    try:
        deck = Deck(name="Cards", default_scheduler_type="sm2_basic")
        db.add(deck)
        db.commit()
        db.refresh(deck)
        card = Card(deck_id=deck.id, card_type="recall", front="Q", back="A", render_format="markdown")
        db.add(card)
        db.commit()
        db.refresh(card)
        card_id = card.id
    finally:
        generator.close()

    response = memory_client.put(
        f"/api/cards/{card_id}",
        json={
            "deck_id": 99999,
            "card_type": "recall",
            "front": "Q2",
            "back": "A2",
            "render_format": "markdown",
            "tags": [],
        },
    )

    assert response.status_code == 404


def test_update_archived_card_returns_404(memory_client) -> None:
    generator, db = _db_from_memory_client()
    try:
        deck = Deck(name="Cards", default_scheduler_type="sm2_basic")
        db.add(deck)
        db.commit()
        db.refresh(deck)

        card = Card(
            deck_id=deck.id,
            card_type="recall",
            front="Archived question",
            back="Archived answer",
            render_format="markdown",
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        card.status = "archived"
        card.deleted_at = None
        db.add(card)
        db.commit()
        card_id = card.id
        deck_id = deck.id
    finally:
        generator.close()

    response = memory_client.put(
        f"/api/cards/{card_id}",
        json={
            "deck_id": deck_id,
            "card_type": "recall",
            "front": "Updated question",
            "back": "Updated answer",
            "render_format": "markdown",
            "tags": [],
        },
    )

    assert response.status_code == 404


def test_update_missing_card_returns_404(memory_client) -> None:
    response = memory_client.put(
        "/api/cards/999999",
        json={
            "deck_id": 1,
            "card_type": "recall",
            "front": "Q",
            "back": "A",
            "render_format": "markdown",
            "tags": [],
        },
    )

    assert response.status_code == 404


def test_update_card_noop_does_not_increment_content_version(memory_client) -> None:
    generator, db = _db_from_memory_client()
    try:
        deck = Deck(name="Cards", default_scheduler_type="sm2_basic")
        db.add(deck)
        db.commit()
        db.refresh(deck)

        card = Card(
            deck_id=deck.id,
            card_type="recall",
            front="Same question",
            back="Same answer",
            render_format="markdown",
            tags=["tag"],
            content_version=3,
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        card_id = card.id
        deck_id = deck.id
    finally:
        generator.close()

    response = memory_client.put(
        f"/api/cards/{card_id}",
        json={
            "deck_id": deck_id,
            "card_type": "recall",
            "front": "Same question",
            "back": "Same answer",
            "render_format": "markdown",
            "tags": ["tag"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["content_version"] == 3
