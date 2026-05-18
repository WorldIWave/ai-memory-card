from app.db.models import Deck, Folder
from app.db.session import get_session
from app.main import app


def _db_from_memory_client():
    override_get_session = app.dependency_overrides[get_session]
    generator = override_get_session()
    return generator, next(generator)


def test_update_deck_changes_name_description_and_folder(memory_client) -> None:
    generator, db = _db_from_memory_client()
    try:
        source = Folder(name="Source")
        target = Folder(name="Target")
        db.add(source)
        db.add(target)
        db.commit()
        db.refresh(source)
        db.refresh(target)
        source_id = source.id
        target_id = target.id

        deck = Deck(name="Old Deck", description="", folder_id=source_id)
        db.add(deck)
        db.commit()
        db.refresh(deck)
        deck_id = deck.id
    finally:
        generator.close()

    response = memory_client.put(
        f"/api/decks/{deck_id}",
        json={"name": "New Deck", "description": "Updated", "folder_id": target_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "New Deck"
    assert payload["description"] == "Updated"
    assert payload["folder_id"] == target_id


def test_update_deck_rejects_duplicate_active_name(memory_client) -> None:
    generator, db = _db_from_memory_client()
    try:
        folder = Folder(name="Root")
        db.add(folder)
        db.commit()
        db.refresh(folder)
        folder_id = folder.id

        first = Deck(name="First", folder_id=1)
        second = Deck(name="Second", folder_id=folder_id)
        db.add(first)
        db.add(second)
        db.commit()
        db.refresh(first)
        db.refresh(second)
        second_id = second.id
    finally:
        generator.close()

    response = memory_client.put(
        f"/api/decks/{second_id}",
        json={"name": "First", "description": "", "folder_id": folder_id},
    )

    assert response.status_code == 409


def test_update_deck_ignores_archived_duplicate_name(memory_client) -> None:
    generator, db = _db_from_memory_client()
    try:
        folder = Folder(name="Root")
        db.add(folder)
        db.commit()
        db.refresh(folder)
        folder_id = folder.id

        archived = Deck(name="Archived", folder_id=folder_id)
        active = Deck(name="Second", folder_id=folder_id)
        db.add(archived)
        db.add(active)
        db.commit()
        db.refresh(archived)
        db.refresh(active)
        archived.visibility = "archived"
        archived.deleted_at = None
        db.add(archived)
        db.commit()
        active_id = active.id
    finally:
        generator.close()

    response = memory_client.put(
        f"/api/decks/{active_id}",
        json={"name": "Archived", "description": "", "folder_id": folder_id},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Archived"


def test_create_deck_allows_name_used_by_archived_deck(memory_client) -> None:
    generator, db = _db_from_memory_client()
    try:
        archived = Deck(name="Archived Name", folder_id=1)
        db.add(archived)
        db.commit()
        db.refresh(archived)
        archived.visibility = "archived"
        archived.deleted_at = None
        db.add(archived)
        db.commit()
    finally:
        generator.close()

    response = memory_client.post("/api/decks", json={"name": "Archived Name"})

    assert response.status_code == 201
    assert response.json()["name"] == "Archived Name"
