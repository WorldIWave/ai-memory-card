# Input: CardReviewState + ReviewOutcome + ReviewContext  |  Output: 断言调度决策字段
# Role: 单元测试 BasicSchedulerProvider（SM2 算法），覆盖间隔增长、逾期标记、边界校验
# Note: 纯内存测试，无数据库或网络依赖；同时验证无效 grade 与缺失 card.id 的错误处理
# Usage: pytest tests/test_scheduler_basic.py，可独立运行，不依赖 conftest 数据库
from datetime import datetime, timedelta, timezone

import pytest

from app.db.models import Card, CardReviewState


def test_basic_scheduler_increases_interval_on_good_review() -> None:
    from app.providers.scheduler.basic import BasicSchedulerProvider
    from app.schemas.review import ReviewContext, ReviewOutcome

    provider = BasicSchedulerProvider()
    state = CardReviewState(card_id=1, interval_days=1.0, ease_factor=2.5, repetition_count=1)
    outcome = ReviewOutcome(grade="good", lapse=False)
    now = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    context = ReviewContext(
        now=now,
        today_load=5,
        pending_count=10,
        deck_policy={"daily_limit": 30},
        review_mode="flip_card",
        is_new_card=False,
        recent_fail_count=0,
        related_weakness_tags=[],
    )

    decision = provider.plan_next(state, outcome, context)

    assert decision.interval_days == 2.0
    assert decision.next_due_at == now + timedelta(days=2.0)
    assert decision.scheduler_type == "sm2_basic"


def test_preview_due_marks_overdue_cards() -> None:
    from app.providers.scheduler.basic import BasicSchedulerProvider

    provider = BasicSchedulerProvider()
    now = datetime.now(timezone.utc)
    states = [CardReviewState(card_id=1, next_due_at=now - timedelta(days=1))]

    previews = provider.preview_due(states, now)

    assert previews[0].card_id == 1
    assert previews[0].is_due is True
    assert previews[0].bucket == "overdue"


def test_review_outcome_rejects_invalid_grade() -> None:
    from pydantic import ValidationError
    from app.schemas.review import ReviewOutcome

    with pytest.raises(ValidationError):
        ReviewOutcome(grade="bogus", lapse=False)


def test_initialize_state_requires_card_id() -> None:
    from app.providers.scheduler.basic import BasicSchedulerProvider

    provider = BasicSchedulerProvider()
    card = Card(
        deck_id=1,
        card_type="recall",
        front="What is attention?",
        back="A mechanism that weights token relevance.",
    )

    with pytest.raises(ValueError, match="card.id"):
        provider.initialize_state(card)