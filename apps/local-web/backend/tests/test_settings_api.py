# Input: FastAPI app instance  |  Output: settings API pytest coverage
# Role: Validate /api/settings/test-ai-provider and /api/settings/study behavior
# Note: Covers missing base_url validation plus global study settings read/write
# Usage: pytest tests/test_settings_api.py
from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.db.models import AppStudySettings
from fastapi.testclient import TestClient

from app.main import app
from app.services.study_settings_service import StudySettingsService


def test_test_ai_provider_requires_base_url() -> None:
    with TestClient(app) as client:
        response = client.post("/api/settings/test-ai-provider", json={})

    assert response.status_code == 400
    assert response.json()["detail"] == "base_url is required to test a remote AI provider"


def test_get_study_settings_returns_default_singleton(memory_client: TestClient) -> None:
    response = memory_client.get("/api/settings/study")

    assert response.status_code == 200
    payload = response.json()
    assert payload["daily_new_limit"] == 20
    assert payload["daily_review_limit"] == 100
    assert payload["scheduler_mode"] == "traditional"
    assert payload["updated_at"] is not None


def test_update_study_settings_persists_global_limits(memory_client: TestClient) -> None:
    response = memory_client.put(
        "/api/settings/study",
        json={"daily_new_limit": 7, "daily_review_limit": 33},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["daily_new_limit"] == 7
    assert payload["daily_review_limit"] == 33

    follow_up = memory_client.get("/api/settings/study")
    assert follow_up.status_code == 200
    persisted = follow_up.json()
    assert persisted["daily_new_limit"] == 7
    assert persisted["daily_review_limit"] == 33


def test_update_study_settings_persists_scheduler_mode(memory_client: TestClient) -> None:
    response = memory_client.put(
        "/api/settings/study",
        json={"daily_new_limit": 7, "daily_review_limit": 33, "scheduler_mode": "ai_rl"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["daily_new_limit"] == 7
    assert payload["daily_review_limit"] == 33
    assert payload["scheduler_mode"] == "ai_rl"

    follow_up = memory_client.get("/api/settings/study")
    assert follow_up.status_code == 200
    persisted = follow_up.json()
    assert persisted["scheduler_mode"] == "ai_rl"


def test_update_study_settings_preserves_scheduler_mode_when_omitted(memory_client: TestClient) -> None:
    initial = memory_client.put(
        "/api/settings/study",
        json={"daily_new_limit": 7, "daily_review_limit": 33, "scheduler_mode": "ai_rl"},
    )
    assert initial.status_code == 200

    legacy_update = memory_client.put(
        "/api/settings/study",
        json={"daily_new_limit": 9, "daily_review_limit": 44},
    )

    assert legacy_update.status_code == 200
    payload = legacy_update.json()
    assert payload["daily_new_limit"] == 9
    assert payload["daily_review_limit"] == 44
    assert payload["scheduler_mode"] == "ai_rl"

    follow_up = memory_client.get("/api/settings/study")
    assert follow_up.status_code == 200
    persisted = follow_up.json()
    assert persisted["scheduler_mode"] == "ai_rl"


def test_update_study_settings_rejects_negative_values(memory_client: TestClient) -> None:
    response = memory_client.put(
        "/api/settings/study",
        json={"daily_new_limit": -1, "daily_review_limit": 10},
    )

    assert response.status_code == 422


def test_update_study_settings_rejects_unknown_scheduler_mode(memory_client: TestClient) -> None:
    response = memory_client.put(
        "/api/settings/study",
        json={
            "daily_new_limit": 7,
            "daily_review_limit": 33,
            "scheduler_mode": "experimental_bad_value",
        },
    )

    assert response.status_code == 422


def test_ensure_recovers_from_singleton_insert_race(session: Session) -> None:
    service = StudySettingsService()
    original_commit = session.commit
    insert_raced = {"done": False}

    def commit_with_race() -> None:
        if not insert_raced["done"]:
            insert_raced["done"] = True
            engine = session.get_bind()
            assert engine is not None
            with Session(engine) as raced_session:
                raced_session.add(
                    AppStudySettings(
                        id=1,
                        daily_new_limit=20,
                        daily_review_limit=100,
                        scheduler_mode="traditional",
                    )
                )
                raced_session.commit()
            raise IntegrityError("INSERT INTO app_study_settings", {}, Exception("duplicate key"))
        return original_commit()

    session.commit = commit_with_race  # type: ignore[method-assign]

    try:
        settings = service.ensure(session)
    finally:
        session.commit = original_commit  # type: ignore[method-assign]

    assert settings.id == 1
    assert settings.daily_new_limit == 20
    assert settings.daily_review_limit == 100
    assert settings.scheduler_mode == "traditional"
