from datetime import datetime, timezone

from sqlmodel import Session

from app.db.models import AppStudySettings, Card, CardReviewState, Deck, LearningEvent, ReviewLog
from app.schemas.review import ReviewSessionContext, SessionScheduleResult
from app.services.review_service import ReviewService
from app.services.review_scheduler_context import build_scheduler_plan_payload


def test_scheduler_payload_includes_latest_evaluation_and_recent_history(session: Session) -> None:
    deck = Deck(name="AI Scheduling")
    session.add(deck)
    session.flush()
    card = Card(
        deck_id=deck.id,
        card_type="understanding",
        front="F",
        back="B",
        render_format="markdown",
        tags=["ml"],
    )
    session.add(card)
    session.flush()
    state = CardReviewState(
        card_id=card.id,
        interval_days=2,
        repetition_count=2,
        learning_state="review",
    )
    session.add(state)
    session.add(
        LearningEvent(
            card_id=card.id,
            deck_id=deck.id,
            event_type="evaluation",
            payload_json={
                "scores": {"mastery": 45, "mechanism": 30, "boundary": 50},
                "diagnosis": {"misconception_detected": False, "weak_points": ["mechanism"]},
            },
        )
    )
    session.add(ReviewLog(card_id=card.id, grade="hard", interval_days=2))
    session.commit()

    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    context = ReviewSessionContext(
        now=now,
        session_id="2026-05-18:deck:1",
        session_date=now.date(),
        scope="deck",
        deck_id=deck.id,
        remaining_card_ids=[99],
    )
    baseline = SessionScheduleResult(
        card_id=card.id,
        scheduler_type="sm2_basic_v3",
        next_due_at=datetime(2026, 5, 22, tzinfo=timezone.utc),
        interval_days=4,
        reason="session v3 grade=good",
        session_action="remove",
        reinsert_after=None,
        learning_state="review",
        learning_step=0,
        session_repeats_today=1,
        hard_attempts_today=0,
        repetition_delta=1,
        lapses_delta=0,
    )

    payload = build_scheduler_plan_payload(
        session,
        card=card,
        state=state,
        grade="good",
        context=context,
        baseline_decision=baseline,
    )

    assert payload["capability"] == "scheduler.plan_review"
    assert payload["mode"] == "local"
    assert payload["card"]["id"] == card.id
    assert payload["understanding"]["scores"]["mechanism"] == 30
    assert payload["review_history"][0]["grade"] == "hard"
    assert payload["baseline_decision"]["interval_days"] == 4


class FailingPluginHost:
    def run_scheduler_plan_review(self, payload: dict[str, object]) -> dict[str, object]:
        raise AssertionError("plugin should not be called in traditional mode")


class SuccessfulPluginHost:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def run_scheduler_plan_review(self, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append(payload)
        return {
            "scheduler_type": "ai_rl_v1",
            "interval_days": 2,
            "confidence": 0.7,
            "source": "uacis_lite",
            "rationale": ["test adjustment"],
            "used_signals": ["grade", "baseline_decision"],
        }


class ExtremeIntervalPluginHost:
    def run_scheduler_plan_review(self, payload: dict[str, object]) -> dict[str, object]:
        return {
            "scheduler_type": "ai_rl_v1",
            "interval_days": 999,
            "confidence": 0.9,
            "source": "uacis_lite",
            "rationale": ["extreme interval should be clamped"],
            "used_signals": ["baseline_decision"],
        }


class BrokenPluginHost:
    def run_scheduler_plan_review(self, payload: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("plugin unavailable")


def _seed_review_card(
    session: Session,
    *,
    deck_name: str,
    interval_days: float = 0.0,
    repetition_count: int = 0,
    learning_state: str = "new",
) -> tuple[Deck, Card, CardReviewState]:
    deck = Deck(name=deck_name)
    session.add(deck)
    session.flush()
    assert deck.id is not None
    card = Card(
        deck_id=deck.id,
        card_type="recall",
        front="F",
        back="B",
        render_format="markdown",
    )
    session.add(card)
    session.flush()
    assert card.id is not None
    state = CardReviewState(
        card_id=card.id,
        interval_days=interval_days,
        repetition_count=repetition_count,
        learning_state=learning_state,
    )
    session.add(state)
    session.commit()
    return deck, card, state


def _set_ai_rl_mode(session: Session) -> None:
    session.merge(
        AppStudySettings(
            id=1,
            daily_new_limit=20,
            daily_review_limit=100,
            scheduler_mode="ai_rl",
        )
    )
    session.commit()


def test_traditional_scheduler_mode_does_not_call_plugin(session: Session) -> None:
    deck, card, _state = _seed_review_card(session, deck_name="Traditional")

    service = ReviewService(ai_plugin_host_service=FailingPluginHost())
    review_session = service.get_session(session, scope="deck", deck_id=deck.id)
    response = service.submit_session(
        session,
        session_id=review_session.session_id,
        card_id=card.id,
        grade="easy",
        review_mode="flip_card",
        trigger_type="scheduled",
    )

    assert response.decision.scheduler_type == "sm2_basic_v3"


def test_ai_rl_scheduler_mode_uses_plugin_interval_but_keeps_session_action(session: Session) -> None:
    _set_ai_rl_mode(session)
    deck, card, _state = _seed_review_card(
        session,
        deck_name="AI RL",
        interval_days=4,
        repetition_count=2,
        learning_state="review",
    )

    plugin = SuccessfulPluginHost()
    service = ReviewService(ai_plugin_host_service=plugin)
    review_session = service.get_session(session, scope="deck", deck_id=deck.id)
    response = service.submit_session(
        session,
        session_id=review_session.session_id,
        card_id=card.id,
        grade="good",
        review_mode="flip_card",
        trigger_type="scheduled",
    )

    assert len(plugin.payloads) == 1
    assert response.decision.scheduler_type == "ai_rl_v1"
    assert response.decision.interval_days == 2
    assert response.decision.session_action == "remove"
    refreshed = session.get(CardReviewState, card.id)
    assert refreshed is not None
    assert refreshed.scheduler_type == "ai_rl_v1"
    assert refreshed.interval_days == 2


def test_ai_rl_scheduler_falls_back_to_basic_when_plugin_fails(session: Session) -> None:
    _set_ai_rl_mode(session)
    deck, card, _state = _seed_review_card(
        session,
        deck_name="Fallback",
        interval_days=3,
        repetition_count=2,
        learning_state="review",
    )

    service = ReviewService(ai_plugin_host_service=BrokenPluginHost())
    review_session = service.get_session(session, scope="deck", deck_id=deck.id)
    response = service.submit_session(
        session,
        session_id=review_session.session_id,
        card_id=card.id,
        grade="good",
        review_mode="flip_card",
        trigger_type="scheduled",
    )

    assert response.decision.scheduler_type == "sm2_basic_v3"
    assert "fallback" in response.decision.reason


def test_ai_rl_scheduler_clamps_plugin_interval(session: Session) -> None:
    _set_ai_rl_mode(session)
    deck, card, _state = _seed_review_card(
        session,
        deck_name="Clamp",
        interval_days=4,
        repetition_count=2,
        learning_state="review",
    )

    service = ReviewService(ai_plugin_host_service=ExtremeIntervalPluginHost())
    review_session = service.get_session(session, scope="deck", deck_id=deck.id)
    response = service.submit_session(
        session,
        session_id=review_session.session_id,
        card_id=card.id,
        grade="good",
        review_mode="flip_card",
        trigger_type="scheduled",
    )

    assert response.decision.scheduler_type == "ai_rl_v1"
    assert response.decision.interval_days == 12
