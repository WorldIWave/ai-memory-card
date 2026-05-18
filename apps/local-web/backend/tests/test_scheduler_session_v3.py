from datetime import datetime, timezone

import pytest

from app.db.models import Card, CardReviewState
from app.providers.scheduler.base import SchedulerProvider, SessionSchedulerProvider
from app.providers.scheduler.basic import BasicSchedulerProvider, BasicSessionScheduler
from app.schemas.review import ReviewSessionContext


def context(queue_card_ids: list[int]) -> ReviewSessionContext:
    return ReviewSessionContext(
        now=datetime(2026, 4, 20, 9, 0, tzinfo=timezone.utc),
        session_id="2026-04-20:deck:1",
        session_date="2026-04-20",
        scope="deck",
        deck_id=1,
        remaining_card_ids=queue_card_ids,
    )


def test_again_single_card_stays_in_session() -> None:
    scheduler = BasicSessionScheduler()
    state = CardReviewState(card_id=1, learning_state="new", interval_days=0)

    result = scheduler.apply_grade(state, "again", context([]))

    assert result.session_action == "repeat_now"
    assert result.learning_state == "learning"
    assert result.reinsert_after == 0
    assert result.next_due_at.date().isoformat() == "2026-04-21"


def test_again_long_queue_reinserts_after_three_cards() -> None:
    scheduler = BasicSessionScheduler()
    state = CardReviewState(card_id=1, learning_state="review", interval_days=4, repetition_count=3)

    result = scheduler.apply_grade(state, "again", context([2, 3, 4, 5]))

    assert result.session_action == "reinsert"
    assert result.reinsert_after == 3
    assert result.learning_state == "relearning"
    assert result.lapses_delta == 1


def test_hard_third_attempt_leaves_session() -> None:
    scheduler = BasicSessionScheduler()
    state = CardReviewState(card_id=1, learning_state="learning", hard_attempts_today=2, interval_days=1)

    result = scheduler.apply_grade(state, "hard", context([2, 3]))

    assert result.session_action == "remove"
    assert result.hard_attempts_today == 3
    assert result.interval_days == 1


def test_new_card_first_good_reinserts_for_consolidation() -> None:
    scheduler = BasicSessionScheduler()
    state = CardReviewState(card_id=1, learning_state="new", learning_step=0)

    result = scheduler.apply_grade(state, "good", context([2, 3]))

    assert result.session_action == "reinsert"
    assert result.learning_state == "learning"
    assert result.learning_step == 1


def test_new_card_second_good_graduates() -> None:
    scheduler = BasicSessionScheduler()
    state = CardReviewState(card_id=1, learning_state="learning", learning_step=1)

    result = scheduler.apply_grade(state, "good", context([]))

    assert result.session_action == "remove"
    assert result.learning_state == "review"
    assert result.repetition_delta == 1


def test_easy_graduates_new_card_immediately() -> None:
    scheduler = BasicSessionScheduler()
    state = CardReviewState(card_id=1, learning_state="new")

    result = scheduler.apply_grade(state, "easy", context([2]))

    assert result.session_action == "remove"
    assert result.learning_state == "review"
    assert result.interval_days == 3


def test_apply_grade_rejects_invalid_grade() -> None:
    scheduler = BasicSessionScheduler()
    state = CardReviewState(card_id=1, learning_state="new")

    with pytest.raises(ValueError, match="Unsupported review grade"):
        scheduler.apply_grade(state, "oops", context([]))


def test_build_session_queue_normalizes_context_now_timezone() -> None:
    scheduler = BasicSessionScheduler()
    naive_context = ReviewSessionContext(
        now=datetime(2026, 4, 20, 9, 0),
        session_id="2026-04-20:deck:1",
        session_date="2026-04-20",
        scope="deck",
        deck_id=1,
        remaining_card_ids=[],
    )
    due_card = Card(id=1, deck_id=1, card_type="basic", front="due", back="due")
    future_card = Card(id=2, deck_id=1, card_type="basic", front="future", back="future")
    rows = [
        (
            future_card,
            CardReviewState(
                card_id=2,
                next_due_at=datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc),
            ),
        ),
        (
            due_card,
            CardReviewState(
                card_id=1,
                next_due_at=datetime(2026, 4, 20, 8, 0, tzinfo=timezone.utc),
            ),
        ),
    ]

    result = scheduler.build_session_queue(rows, naive_context)

    assert [card.id for card in result] == [1, 2]


def test_scheduler_protocols_preserve_legacy_and_session_compatibility() -> None:
    assert isinstance(BasicSchedulerProvider(), SchedulerProvider)
    assert isinstance(BasicSessionScheduler(), SessionSchedulerProvider)
