from sqlmodel import select

from app.db.models import Card, CardReviewState, Deck, Folder, LearningEvent, ReviewLog
from app.db.session import get_session
from app.main import app


def _db_from_memory_client():
    override_get_session = app.dependency_overrides[get_session]
    generator = override_get_session()
    return generator, next(generator)


def test_update_folder_renames_non_default_folder(memory_client) -> None:
    generator, db = _db_from_memory_client()
    try:
        root = Folder(name="Root")
        db.add(root)
        db.commit()
        db.refresh(root)

        folder = Folder(name="Old Folder")
        db.add(folder)
        db.commit()
        db.refresh(folder)
        folder_id = folder.id
    finally:
        generator.close()

    response = memory_client.put(f"/api/folders/{folder_id}", json={"name": "New Folder"})

    assert response.status_code == 200
    assert response.json()["name"] == "New Folder"


def test_update_folder_rejects_default_folder(memory_client) -> None:
    response = memory_client.put("/api/folders/1", json={"name": "Renamed Root"})

    assert response.status_code == 400


def test_update_folder_rejects_duplicate_name(memory_client) -> None:
    generator, db = _db_from_memory_client()
    try:
        first = Folder(name="First")
        second = Folder(name="Second")
        db.add(first)
        db.add(second)
        db.commit()
        db.refresh(first)
        db.refresh(second)
        second_id = second.id
    finally:
        generator.close()

    response = memory_client.put(f"/api/folders/{second_id}", json={"name": "First"})

    assert response.status_code == 409


def test_delete_folder_permanently_deletes_its_decks_cards_and_related_rows(memory_client) -> None:
    generator, db = _db_from_memory_client()
    try:
        root = Folder(name="Root")
        db.add(root)
        db.commit()

        folder = Folder(name="Temporary")
        db.add(folder)
        db.commit()
        db.refresh(folder)

        deck = Deck(name="Folder Deck", folder_id=folder.id)
        db.add(deck)
        db.commit()
        db.refresh(deck)

        card = Card(
            deck_id=deck.id,
            card_type="recall",
            front="Folder card",
            back="Deleted with folder.",
            render_format="markdown",
        )
        db.add(card)
        db.commit()
        db.refresh(card)

        db.add(
            ReviewLog(
                card_id=card.id,
                grade="good",
                interval_days=1,
                ease_factor=2.5,
            )
        )
        db.add(
            LearningEvent(
                card_id=card.id,
                deck_id=deck.id,
                event_type="note",
                payload_json={"note": "delete with folder"},
            )
        )
        db.commit()
        folder_id = folder.id
        deck_id = deck.id
        card_id = card.id
    finally:
        generator.close()

    response = memory_client.delete(f"/api/folders/{folder_id}")

    assert response.status_code == 204

    generator, db = _db_from_memory_client()
    try:
        assert db.get(Folder, folder_id) is None
        assert db.get(Deck, deck_id) is None
        assert db.get(Card, card_id) is None
        assert db.get(CardReviewState, card_id) is None
        assert db.exec(select(ReviewLog).where(ReviewLog.card_id == card_id)).first() is None
        assert db.exec(select(LearningEvent).where(LearningEvent.deck_id == deck_id)).first() is None
    finally:
        generator.close()
