from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db.session import get_session
from app.db.models import Card, CardReviewState, Deck, ReviewLog, ReviewSession
from app.services.review_service import ReviewService
from app.main import app


def _db_from_memory_client():
    override_get_session = app.dependency_overrides[get_session]
    generator = override_get_session()
    return generator, next(generator)


def seed_review_card(db: Session, deck_name: str, front: str = "Seed card") -> tuple[int, int]:
    deck = Deck(name=deck_name)
    db.add(deck)
    db.flush()
    assert deck.id is not None

    card = Card(
        deck_id=deck.id,
        card_type="recall",
        front=front,
        back=f"Answer for {front}",
        render_format="markdown",
    )
    db.add(card)
    db.flush()
    assert card.id is not None

    db.add(CardReviewState(card_id=card.id))
    db.commit()
    return deck.id, card.id


def seed_review_cards(db: Session, deck_name: str, count: int) -> tuple[int, list[int]]:
    deck = Deck(name=deck_name)
    db.add(deck)
    db.flush()
    assert deck.id is not None

    card_ids: list[int] = []
    for idx in range(count):
        card = Card(
            deck_id=deck.id,
            card_type="recall",
            front=f"Seed card {idx}",
            back=f"Answer {idx}",
            render_format="markdown",
        )
        db.add(card)
        db.flush()
        assert card.id is not None
        db.add(CardReviewState(card_id=card.id))
        card_ids.append(card.id)
    db.commit()
    return deck.id, card_ids


def create_deck(client: TestClient, name: str) -> int:
    response = client.post("/api/decks", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def create_card(client: TestClient, deck_id: int, front: str) -> int:
    response = client.post(
        "/api/cards",
        json={
            "deck_id": deck_id,
            "card_type": "recall",
            "front": front,
            "back": f"Answer for {front}",
            "render_format": "markdown",
            "tags": [],
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_again_one_card_session_does_not_complete(memory_client: TestClient) -> None:
    deck_id = create_deck(memory_client, "Again Deck")
    card_id = create_card(memory_client, deck_id, "Only card")

    session_response = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck_id}")
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]

    submit_response = memory_client.post(
        f"/api/review/session/{session_id}/submit",
        json={"card_id": card_id, "grade": "again", "review_mode": "flip_card", "trigger_type": "scheduled"},
    )

    assert submit_response.status_code == 200
    payload = submit_response.json()
    assert [card["id"] for card in payload["queue"]] == [card_id]
    assert payload["counts"]["total"] == 1
    assert payload["can_undo"] is True


def test_hard_third_time_removes_card_from_today(memory_client: TestClient) -> None:
    deck_id = create_deck(memory_client, "Hard Deck")
    card_id = create_card(memory_client, deck_id, "Hard card")
    session_id = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck_id}").json()["session_id"]

    for attempt in range(3):
        response = memory_client.post(
            f"/api/review/session/{session_id}/submit",
            json={"card_id": card_id, "grade": "hard", "review_mode": "flip_card", "trigger_type": "scheduled"},
        )
        assert response.status_code == 200
        payload = response.json()

    assert payload["queue"] == []
    assert payload["decision"]["hard_attempts_today"] == 3


def test_new_card_good_requires_second_good_to_graduate(memory_client: TestClient) -> None:
    deck_id = create_deck(memory_client, "Good Deck")
    card_id = create_card(memory_client, deck_id, "Good card")
    session_id = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck_id}").json()["session_id"]

    first = memory_client.post(
        f"/api/review/session/{session_id}/submit",
        json={"card_id": card_id, "grade": "good", "review_mode": "flip_card", "trigger_type": "scheduled"},
    )
    assert [card["id"] for card in first.json()["queue"]] == [card_id]
    assert first.json()["decision"]["learning_state"] == "learning"

    second = memory_client.post(
        f"/api/review/session/{session_id}/submit",
        json={"card_id": card_id, "grade": "good", "review_mode": "flip_card", "trigger_type": "scheduled"},
    )
    assert second.json()["queue"] == []
    assert second.json()["decision"]["learning_state"] == "review"


def test_undo_restores_current_session_state(memory_client: TestClient) -> None:
    deck_id = create_deck(memory_client, "Undo Deck")
    card_id = create_card(memory_client, deck_id, "Undo card")
    session_id = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck_id}").json()["session_id"]

    memory_client.post(
        f"/api/review/session/{session_id}/submit",
        json={"card_id": card_id, "grade": "easy", "review_mode": "flip_card", "trigger_type": "scheduled"},
    )
    undo = memory_client.post(f"/api/review/session/{session_id}/undo")

    assert undo.status_code == 200
    payload = undo.json()
    assert payload["restored_card_id"] == card_id
    assert [card["id"] for card in payload["queue"]] == [card_id]
    assert payload["can_undo"] is False


def test_deck_sessions_are_isolated(memory_client: TestClient) -> None:
    deck_a = create_deck(memory_client, "Deck A")
    deck_b = create_deck(memory_client, "Deck B")
    card_a = create_card(memory_client, deck_a, "A")
    card_b = create_card(memory_client, deck_b, "B")

    session_a = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck_a}").json()
    session_b = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck_b}").json()

    assert [card["id"] for card in session_a["queue"]] == [card_a]
    assert [card["id"] for card in session_b["queue"]] == [card_b]


def test_again_reinserts_after_three_remaining_cards(memory_client: TestClient) -> None:
    deck_id = create_deck(memory_client, "Reinsert Deck")
    card_ids = [create_card(memory_client, deck_id, f"Card {idx}") for idx in range(5)]
    session_id = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck_id}").json()["session_id"]

    response = memory_client.post(
        f"/api/review/session/{session_id}/submit",
        json={"card_id": card_ids[0], "grade": "again", "review_mode": "flip_card", "trigger_type": "scheduled"},
    )

    assert response.status_code == 200
    assert [card["id"] for card in response.json()["queue"]] == [
        card_ids[1],
        card_ids[2],
        card_ids[3],
        card_ids[0],
        card_ids[4],
    ]


def test_multiple_again_reinserts_preserve_visible_queue_order(memory_client: TestClient) -> None:
    deck_id = create_deck(memory_client, "Multi Reinsert Deck")
    card_ids = [create_card(memory_client, deck_id, f"Multi card {idx}") for idx in range(5)]
    session = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck_id}").json()

    assert [card["id"] for card in session["queue"]] == card_ids

    first = memory_client.post(
        f"/api/review/session/{session['session_id']}/submit",
        json={"card_id": card_ids[0], "grade": "again", "review_mode": "flip_card", "trigger_type": "scheduled"},
    )
    assert [card["id"] for card in first.json()["queue"]] == [
        card_ids[1],
        card_ids[2],
        card_ids[3],
        card_ids[0],
        card_ids[4],
    ]

    second = memory_client.post(
        f"/api/review/session/{session['session_id']}/submit",
        json={"card_id": card_ids[1], "grade": "again", "review_mode": "flip_card", "trigger_type": "scheduled"},
    )

    assert [card["id"] for card in second.json()["queue"]] == [
        card_ids[2],
        card_ids[3],
        card_ids[0],
        card_ids[1],
        card_ids[4],
    ]


def test_session_queue_applies_review_and_new_limits_to_first_admission(memory_client: TestClient) -> None:
    memory_client.put(
        "/api/settings/study",
        json={"daily_new_limit": 1, "daily_review_limit": 1},
    )

    generator, db = _db_from_memory_client()
    try:
        deck_id = create_deck(memory_client, "Admission Limits Deck")
        reviewed_ids = [create_card(memory_client, deck_id, f"Reviewed {idx}") for idx in range(2)]
        new_ids = [create_card(memory_client, deck_id, f"New {idx}") for idx in range(2)]

        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        for card_id in reviewed_ids:
            state = db.get(CardReviewState, card_id)
            assert state is not None
            state.next_due_at = yesterday
            state.last_reviewed_at = yesterday
            state.interval_days = 3
            state.repetition_count = 2
            db.add(state)
        db.commit()

        session_payload = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck_id}").json()
        queue_ids = [card["id"] for card in session_payload["queue"]]

        assert reviewed_ids[0] in queue_ids
        assert reviewed_ids[1] not in queue_ids
        assert new_ids[0] in queue_ids
        assert new_ids[1] not in queue_ids
        assert len(queue_ids) == 2
    finally:
        generator.close()


def test_same_day_reinsert_does_not_consume_extra_quota(memory_client: TestClient) -> None:
    memory_client.put(
        "/api/settings/study",
        json={"daily_new_limit": 0, "daily_review_limit": 1},
    )

    generator, db = _db_from_memory_client()
    try:
        deck_id = create_deck(memory_client, "Same Day Reinsertion Deck")
        card_ids = [create_card(memory_client, deck_id, f"Review {idx}") for idx in range(2)]

        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        for card_id in card_ids:
            state = db.get(CardReviewState, card_id)
            assert state is not None
            state.next_due_at = yesterday
            state.last_reviewed_at = yesterday
            state.interval_days = 2
            state.repetition_count = 2
            db.add(state)
        db.commit()

        session_payload = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck_id}").json()
        queue_ids = [card["id"] for card in session_payload["queue"]]
        assert queue_ids == [card_ids[0]]

        submit_response = memory_client.post(
            f"/api/review/session/{session_payload['session_id']}/submit",
            json={
                "card_id": card_ids[0],
                "grade": "again",
                "review_mode": "flip_card",
                "trigger_type": "scheduled",
            },
        )
        assert submit_response.status_code == 200
        submit_payload = submit_response.json()
        assert [card["id"] for card in submit_payload["queue"]] == [card_ids[0]]
        assert card_ids[1] not in [card["id"] for card in submit_payload["queue"]]
    finally:
        generator.close()


def test_stale_review_carry_over_respects_zero_daily_review_limit(memory_client: TestClient) -> None:
    memory_client.put(
        "/api/settings/study",
        json={"daily_new_limit": 0, "daily_review_limit": 0},
    )

    generator, db = _db_from_memory_client()
    try:
        deck_id = create_deck(memory_client, "Rollover Review Deck")
        card_id = create_card(memory_client, deck_id, "Stale review card")

        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        state = db.get(CardReviewState, card_id)
        assert state is not None
        state.next_due_at = yesterday
        state.session_due_at = yesterday
        state.last_session_date = yesterday.date()
        state.last_reviewed_at = yesterday
        state.interval_days = 4
        state.repetition_count = 2
        db.add(state)
        db.commit()

        first_payload = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck_id}").json()
        second_payload = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck_id}").json()

        assert first_payload["queue"] == []
        assert second_payload["queue"] == []
    finally:
        generator.close()


def test_future_card_not_in_session_queue_cannot_be_submitted(memory_client: TestClient) -> None:
    deck_id = create_deck(memory_client, "Future Deck")
    card_id = create_card(memory_client, deck_id, "Future card")

    legacy_submit = memory_client.post(
        "/api/review/submit",
        json={"card_id": card_id, "grade": "easy", "review_mode": "flip_card", "trigger_type": "scheduled"},
    )
    assert legacy_submit.status_code == 200

    session_response = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck_id}")
    assert session_response.status_code == 200
    session_payload = session_response.json()
    assert [card["id"] for card in session_payload["queue"]] == []

    submit_response = memory_client.post(
        f"/api/review/session/{session_payload['session_id']}/submit",
        json={"card_id": card_id, "grade": "good", "review_mode": "flip_card", "trigger_type": "scheduled"},
    )

    assert submit_response.status_code == 400
    assert "current review session" in submit_response.json()["detail"]


def test_removed_card_cannot_be_resubmitted_to_same_session(memory_client: TestClient) -> None:
    deck_id = create_deck(memory_client, "Removed Deck")
    card_id = create_card(memory_client, deck_id, "Removed card")
    session_id = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck_id}").json()["session_id"]

    first = memory_client.post(
        f"/api/review/session/{session_id}/submit",
        json={"card_id": card_id, "grade": "easy", "review_mode": "flip_card", "trigger_type": "scheduled"},
    )
    assert first.status_code == 200
    assert first.json()["queue"] == []

    second = memory_client.post(
        f"/api/review/session/{session_id}/submit",
        json={"card_id": card_id, "grade": "easy", "review_mode": "flip_card", "trigger_type": "scheduled"},
    )

    assert second.status_code == 400
    assert "current review session" in second.json()["detail"]


def test_session_submit_rejects_note_trigger(memory_client: TestClient) -> None:
    deck_id = create_deck(memory_client, "Note Trigger Deck")
    card_id = create_card(memory_client, deck_id, "Note trigger card")
    session_id = memory_client.get(f"/api/review/session?scope=deck&deck_id={deck_id}").json()["session_id"]

    response = memory_client.post(
        f"/api/review/session/{session_id}/submit",
        json={
            "card_id": card_id,
            "grade": "good",
            "review_mode": "flip_card",
            "trigger_type": "note",
            "note": "Keep this as a note only later",
        },
    )

    assert response.status_code == 400
    assert "scheduled" in response.json()["detail"]


def test_submit_to_yesterdays_session_is_rejected_without_mutation(session: Session) -> None:
    deck_id, card_id = seed_review_card(session, "Stale Submit Deck")
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    stale_session = ReviewSession(
        id=f"{yesterday.isoformat()}:deck:{deck_id}",
        session_date=yesterday,
        scope="deck",
        deck_id=deck_id,
    )
    state = session.get(CardReviewState, card_id)
    assert state is not None
    state.interval_days = 2
    state.repetition_count = 4
    state.last_session_date = yesterday
    state.session_repeats_today = 3
    state.hard_attempts_today = 1
    session.add(stale_session)
    session.add(state)
    session.commit()

    with pytest.raises(HTTPException) as exc_info:
        ReviewService().submit_session(
            session,
            session_id=stale_session.id,
            card_id=card_id,
            grade="easy",
            review_mode="flip_card",
            trigger_type="scheduled",
        )

    assert exc_info.value.status_code == 409
    session.rollback()
    refreshed = session.get(CardReviewState, card_id)
    assert refreshed is not None
    assert refreshed.interval_days == 2
    assert refreshed.repetition_count == 4
    assert refreshed.last_session_date == yesterday
    assert refreshed.session_repeats_today == 3
    assert refreshed.hard_attempts_today == 1
    assert session.exec(select(ReviewLog)).all() == []


def test_note_trigger_rejection_does_not_mutate_state_or_create_log(session: Session) -> None:
    deck_id, card_id = seed_review_card(session, "Note Rejected Deck")
    service = ReviewService()
    review_session = service.get_session(session, scope="deck", deck_id=deck_id)
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)

    state = session.get(CardReviewState, card_id)
    assert state is not None
    state.interval_days = 2
    state.last_session_date = yesterday
    state.session_repeats_today = 4
    state.hard_attempts_today = 2
    session.add(state)
    session.commit()

    with pytest.raises(HTTPException) as exc_info:
        service.submit_session(
            session,
            session_id=review_session.session_id,
            card_id=card_id,
            grade="good",
            review_mode="flip_card",
            trigger_type="note",
            note="Not scheduling in Task 3",
        )

    assert exc_info.value.status_code == 400
    session.rollback()
    refreshed = session.get(CardReviewState, card_id)
    assert refreshed is not None
    assert refreshed.interval_days == 2
    assert refreshed.last_session_date == yesterday
    assert refreshed.session_repeats_today == 4
    assert refreshed.hard_attempts_today == 2
    assert session.exec(select(ReviewLog)).all() == []


def test_invalid_grade_rejection_does_not_mutate_state_or_create_log(session: Session) -> None:
    deck_id, card_id = seed_review_card(session, "Invalid Grade Deck")
    service = ReviewService()
    review_session = service.get_session(session, scope="deck", deck_id=deck_id)
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)

    state = session.get(CardReviewState, card_id)
    assert state is not None
    state.interval_days = 3
    state.last_session_date = yesterday
    state.session_repeats_today = 5
    state.hard_attempts_today = 1
    session.add(state)
    session.commit()

    with pytest.raises(HTTPException) as exc_info:
        service.submit_session(
            session,
            session_id=review_session.session_id,
            card_id=card_id,
            grade="bogus",
            review_mode="flip_card",
            trigger_type="scheduled",
        )

    assert exc_info.value.status_code == 400
    session.rollback()
    refreshed = session.get(CardReviewState, card_id)
    assert refreshed is not None
    assert refreshed.interval_days == 3
    assert refreshed.last_session_date == yesterday
    assert refreshed.session_repeats_today == 5
    assert refreshed.hard_attempts_today == 1
    assert session.exec(select(ReviewLog)).all() == []


def test_undo_on_yesterdays_session_is_rejected(session: Session) -> None:
    deck_id, card_id = seed_review_card(session, "Stale Undo Deck")
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    stale_session = ReviewSession(
        id=f"{yesterday.isoformat()}:deck:{deck_id}",
        session_date=yesterday,
        scope="deck",
        deck_id=deck_id,
    )
    log = ReviewLog(
        card_id=card_id,
        grade="easy",
        interval_days=3,
        session_id=stale_session.id,
        trigger_type="scheduled",
        state_before={"card_id": card_id, "interval_days": 0},
    )
    session.add(stale_session)
    session.add(log)
    session.commit()

    with pytest.raises(HTTPException) as exc_info:
        ReviewService().undo_session(session, session_id=stale_session.id)

    assert exc_info.value.status_code == 409
    session.rollback()
    refreshed_log = session.get(ReviewLog, log.id)
    assert refreshed_log is not None
    assert refreshed_log.is_undone is False
    assert refreshed_log.undone_at is None


def test_rejected_future_submit_does_not_mutate_state_or_create_log(session: Session) -> None:
    deck_id, target_card_id = seed_review_card(session, "Rejected Future Deck", "Future target")
    _deck_id, due_card_id = seed_review_card(session, "Rejected Future Deck", "Due neighbor")
    due_card = session.get(Card, due_card_id)
    assert due_card is not None
    due_card.deck_id = deck_id

    now = datetime.now(timezone.utc)
    yesterday = now.date() - timedelta(days=1)
    review_session = ReviewSession(
        id=f"{now.date().isoformat()}:deck:{deck_id}",
        session_date=now.date(),
        scope="deck",
        deck_id=deck_id,
    )
    target_state = session.get(CardReviewState, target_card_id)
    due_state = session.get(CardReviewState, due_card_id)
    assert target_state is not None
    assert due_state is not None
    future_due_at = now + timedelta(days=7)
    target_state.next_due_at = future_due_at
    target_state.last_session_date = yesterday
    target_state.session_repeats_today = 5
    target_state.hard_attempts_today = 2
    target_state.interval_days = 8
    due_state.last_session_date = yesterday
    due_state.session_repeats_today = 4
    session.add(review_session)
    session.add(due_card)
    session.add(target_state)
    session.add(due_state)
    session.commit()

    with pytest.raises(HTTPException) as exc_info:
        ReviewService().submit_session(
            session,
            session_id=review_session.id,
            card_id=target_card_id,
            grade="good",
            review_mode="flip_card",
            trigger_type="scheduled",
        )

    assert exc_info.value.status_code == 400
    session.rollback()
    refreshed = session.get(CardReviewState, target_card_id)
    due_refreshed = session.get(CardReviewState, due_card_id)
    assert refreshed is not None
    assert due_refreshed is not None
    assert refreshed.next_due_at == future_due_at.replace(tzinfo=None)
    assert refreshed.last_session_date == yesterday
    assert refreshed.session_repeats_today == 5
    assert refreshed.hard_attempts_today == 2
    assert refreshed.interval_days == 8
    assert due_refreshed.last_session_date == yesterday
    assert due_refreshed.session_repeats_today == 4
    assert session.exec(select(ReviewLog)).all() == []


def test_stale_daily_metadata_due_card_can_still_submit(session: Session) -> None:
    deck_id, card_id = seed_review_card(session, "Stale Accepted Deck")
    service = ReviewService()
    review_session = service.get_session(session, scope="deck", deck_id=deck_id)
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    stale_due = datetime.now(timezone.utc) - timedelta(days=1)
    stale_session_due = datetime.now(timezone.utc) - timedelta(hours=12)

    state = session.get(CardReviewState, card_id)
    assert state is not None
    state.next_due_at = stale_due
    state.session_due_at = stale_session_due
    state.last_session_date = yesterday
    state.session_repeats_today = 4
    state.hard_attempts_today = 2
    state.scheduler_state_blob = {"session_order": {review_session.session_id: 99}}
    session.add(state)
    session.commit()

    visible = service.get_session(session, scope="deck", deck_id=deck_id)
    assert [card.id for card in visible.queue] == [card_id]

    # Re-stale the state after GET so submit validation must perform a non-mutating
    # reset-for-read instead of depending on GET's persisted reset.
    state = session.get(CardReviewState, card_id)
    assert state is not None
    state.session_due_at = stale_session_due
    state.last_session_date = yesterday
    state.session_repeats_today = 4
    state.hard_attempts_today = 2
    session.add(state)
    session.commit()

    response = service.submit_session(
        session,
        session_id=review_session.session_id,
        card_id=card_id,
        grade="easy",
        review_mode="flip_card",
        trigger_type="scheduled",
    )

    assert response.decision.card_id == card_id
    assert response.queue == []


def test_undo_restores_queue_order_metadata_for_all_affected_cards(session: Session) -> None:
    deck_id, card_ids = seed_review_cards(session, "Undo Order Deck", 5)
    service = ReviewService()
    review_session = service.get_session(session, scope="deck", deck_id=deck_id)
    session_id = review_session.session_id

    assert [card.id for card in review_session.queue] == card_ids

    submitted = service.submit_session(
        session,
        session_id=session_id,
        card_id=card_ids[0],
        grade="again",
        review_mode="flip_card",
        trigger_type="scheduled",
    )
    assert [card.id for card in submitted.queue] == [
        card_ids[1],
        card_ids[2],
        card_ids[3],
        card_ids[0],
        card_ids[4],
    ]
    ordered_states = session.exec(
        select(CardReviewState).where(CardReviewState.card_id.in_(card_ids))
    ).all()
    assert any(
        session_id in (state.scheduler_state_blob or {}).get("session_order", {})
        for state in ordered_states
    )

    undone = service.undo_session(session, session_id=session_id)

    assert [card.id for card in undone.queue] == card_ids
    restored_states = session.exec(
        select(CardReviewState).where(CardReviewState.card_id.in_(card_ids))
    ).all()
    assert all(
        session_id not in (state.scheduler_state_blob or {}).get("session_order", {})
        for state in restored_states
    )


def test_session_with_unknown_deck_returns_404(memory_client: TestClient) -> None:
    response = memory_client.get("/api/review/session?scope=deck&deck_id=999999")

    assert response.status_code == 404


def test_submit_with_unknown_session_returns_404(memory_client: TestClient) -> None:
    response = memory_client.post(
        "/api/review/session/unknown-session/submit",
        json={"card_id": 1, "grade": "good", "review_mode": "flip_card", "trigger_type": "scheduled"},
    )

    assert response.status_code == 404


def test_undo_with_unknown_session_returns_404(memory_client: TestClient) -> None:
    response = memory_client.post("/api/review/session/unknown-session/undo")

    assert response.status_code == 404
