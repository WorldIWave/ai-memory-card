from datetime import datetime, timedelta, timezone

from app.db.models import Card, Deck, LearningEvent, ReviewLog
from app.db.session import get_session
from app.main import app
from app.services.analytics_service import AnalyticsService


def test_summary_daily_new_avg_uses_card_created_at(memory_client) -> None:
    override_get_session = app.dependency_overrides[get_session]
    session_generator = override_get_session()
    db = next(session_generator)
    try:
        deck = Deck(name="Stats Deck", default_scheduler_type="sm2_basic")
        db.add(deck)
        db.commit()
        db.refresh(deck)

        now = datetime.now(timezone.utc)
        today = now.replace(hour=12, minute=0, second=0, microsecond=0)
        two_days_ago = today - timedelta(days=2)
        old = today - timedelta(days=10)

        recent_card = Card(
            deck_id=deck.id,
            card_type="recall",
            front="A",
            back="A",
            render_format="markdown",
            created_at=today,
        )
        second_recent_card = Card(
            deck_id=deck.id,
            card_type="recall",
            front="B",
            back="B",
            render_format="markdown",
            created_at=two_days_ago,
        )
        old_card = Card(
            deck_id=deck.id,
            card_type="recall",
            front="C",
            back="C",
            render_format="markdown",
            created_at=old,
        )
        db.add(recent_card)
        db.add(second_recent_card)
        db.add(old_card)
        db.commit()
        db.refresh(recent_card)
        assert recent_card.id is not None

        for _ in range(5):
            db.add(
                ReviewLog(
                    card_id=recent_card.id,
                    grade="good",
                    interval_days=1,
                    ease_factor=2.5,
                    reviewed_at=today,
                )
            )
        db.commit()
    finally:
        session_generator.close()

    response = memory_client.get("/api/stats/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["daily_new_avg"] == 0.3
    assert payload["daily_review_avg"] == 0.7


def test_analytics_returns_zero_filled_trend_grade_distribution_and_deck_activity(memory_client) -> None:
    override_get_session = app.dependency_overrides[get_session]
    session_generator = override_get_session()
    db = next(session_generator)
    try:
        algorithms = Deck(name="Algorithms", default_scheduler_type="sm2_basic")
        biology = Deck(name="Biology", default_scheduler_type="sm2_basic")
        chemistry = Deck(name="Chemistry", default_scheduler_type="sm2_basic")
        design = Deck(name="Design", default_scheduler_type="sm2_basic")
        db.add(algorithms)
        db.add(biology)
        db.add(chemistry)
        db.add(design)
        db.commit()
        db.refresh(algorithms)
        db.refresh(biology)
        db.refresh(chemistry)
        db.refresh(design)

        now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_6 = today_start - timedelta(days=6)
        day_4 = today_start - timedelta(days=4)
        day_2 = today_start - timedelta(days=2)
        day_1 = today_start - timedelta(days=1)

        alg_primary = Card(
            deck_id=algorithms.id,
            card_type="recall",
            front="Alg 1",
            back="Alg 1",
            render_format="markdown",
            created_at=day_6,
        )
        alg_secondary = Card(
            deck_id=algorithms.id,
            card_type="recall",
            front="Alg 2",
            back="Alg 2",
            render_format="markdown",
            created_at=day_1,
        )
        bio_card = Card(
            deck_id=biology.id,
            card_type="recall",
            front="Bio 1",
            back="Bio 1",
            render_format="markdown",
            created_at=day_4,
        )
        chem_card = Card(
            deck_id=chemistry.id,
            card_type="recall",
            front="Chem 1",
            back="Chem 1",
            render_format="markdown",
            created_at=day_2,
        )
        design_card = Card(
            deck_id=design.id,
            card_type="recall",
            front="Design 1",
            back="Design 1",
            render_format="markdown",
            created_at=day_1,
        )
        db.add(alg_primary)
        db.add(alg_secondary)
        db.add(bio_card)
        db.add(chem_card)
        db.add(design_card)
        db.commit()
        db.refresh(alg_primary)
        db.refresh(alg_secondary)
        db.refresh(bio_card)
        db.refresh(chem_card)
        db.refresh(design_card)

        db.add(ReviewLog(card_id=alg_primary.id, grade="again", interval_days=1, ease_factor=2.5, reviewed_at=day_6))
        db.add(ReviewLog(card_id=alg_secondary.id, grade="good", interval_days=2, ease_factor=2.5, reviewed_at=day_1))
        db.add(ReviewLog(card_id=alg_primary.id, grade="easy", interval_days=3, ease_factor=2.5, reviewed_at=now))
        db.add(ReviewLog(card_id=bio_card.id, grade="hard", interval_days=1, ease_factor=2.5, reviewed_at=day_4))
        db.add(ReviewLog(card_id=bio_card.id, grade="good", interval_days=2, ease_factor=2.5, reviewed_at=day_2))
        db.add(ReviewLog(card_id=chem_card.id, grade="hard", interval_days=1, ease_factor=2.5, reviewed_at=day_2))
        db.add(ReviewLog(card_id=chem_card.id, grade="again", interval_days=4, ease_factor=2.5, reviewed_at=now))
        db.add(ReviewLog(card_id=design_card.id, grade="easy", interval_days=5, ease_factor=2.5, reviewed_at=now))
        db.add(ReviewLog(card_id=alg_primary.id, grade="again", interval_days=6, ease_factor=2.5, reviewed_at=now, trigger_type="manual"))
        db.add(ReviewLog(card_id=bio_card.id, grade="hard", interval_days=7, ease_factor=2.5, reviewed_at=now, is_undone=True))
        db.add(
            LearningEvent(
                card_id=alg_primary.id,
                deck_id=algorithms.id,
                event_type="report_error",
                payload_json={"reason": "typo", "note": "ignore"},
                created_at=now,
            )
        )
        db.commit()
    finally:
        session_generator.close()

    response = memory_client.get("/api/stats/analytics?range_days=7")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "total_cards": 5,
        "today_reviewed": 3,
        "daily_new_avg": 0.7,
        "daily_review_avg": 1.1,
    }
    assert payload["trend"]["range_days"] == 7
    assert [point["date"] for point in payload["trend"]["points"]] == [
        (today_start - timedelta(days=offset)).date().isoformat()
        for offset in range(6, -1, -1)
    ]
    assert [point["review_count"] for point in payload["trend"]["points"]] == [1, 0, 1, 0, 2, 1, 3]
    assert [item["grade"] for item in payload["grade_distribution"]["items"]] == ["again", "hard", "good", "easy"]
    assert [item["count"] for item in payload["grade_distribution"]["items"]] == [2, 2, 2, 2]
    assert payload["grade_distribution"]["total_reviews"] == 8
    assert [item["deck_name"] for item in payload["deck_activity"]["items"]] == [
        "Algorithms",
        "Biology",
        "Chemistry",
        "Design",
    ]
    assert [item["review_count"] for item in payload["deck_activity"]["items"]] == [3, 2, 2, 1]
    assert [item["unique_cards"] for item in payload["deck_activity"]["items"]] == [2, 1, 1, 1]


def test_analytics_rejects_invalid_range(memory_client) -> None:
    response = memory_client.get("/api/stats/analytics?range_days=14")

    assert response.status_code == 400
    assert response.json()["detail"] == "range_days must be 7 or 30"


def test_analytics_rejects_non_integer_range(memory_client) -> None:
    response = memory_client.get("/api/stats/analytics?range_days=foo")

    assert response.status_code == 400
    assert response.json()["detail"] == "range_days must be 7 or 30"


def test_summary_uses_a_true_bounded_seven_day_window(memory_client) -> None:
    override_get_session = app.dependency_overrides[get_session]
    session_generator = override_get_session()
    db = next(session_generator)
    try:
        deck = Deck(name="Window Deck", default_scheduler_type="sm2_basic")
        db.add(deck)
        db.commit()
        db.refresh(deck)

        now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        within_window_day = today_start - timedelta(days=6)
        boundary_day = today_start - timedelta(days=7)
        future_day = today_start + timedelta(days=1)

        in_window_card = Card(
            deck_id=deck.id,
            card_type="recall",
            front="Inside",
            back="Inside",
            render_format="markdown",
            created_at=within_window_day,
        )
        boundary_card = Card(
            deck_id=deck.id,
            card_type="recall",
            front="Boundary",
            back="Boundary",
            render_format="markdown",
            created_at=boundary_day,
        )
        future_card = Card(
            deck_id=deck.id,
            card_type="recall",
            front="Future",
            back="Future",
            render_format="markdown",
            created_at=future_day,
        )
        db.add(in_window_card)
        db.add(boundary_card)
        db.add(future_card)
        db.commit()
        db.refresh(in_window_card)
        db.refresh(boundary_card)
        db.refresh(future_card)

        db.add(
            ReviewLog(
                card_id=in_window_card.id,
                grade="good",
                interval_days=1,
                ease_factor=2.5,
                reviewed_at=within_window_day,
            )
        )
        db.add(
            ReviewLog(
                card_id=in_window_card.id,
                grade="easy",
                interval_days=1,
                ease_factor=2.5,
                reviewed_at=now,
            )
        )
        db.add(
            ReviewLog(
                card_id=boundary_card.id,
                grade="hard",
                interval_days=1,
                ease_factor=2.5,
                reviewed_at=boundary_day,
            )
        )
        db.add(
            ReviewLog(
                card_id=future_card.id,
                grade="again",
                interval_days=1,
                ease_factor=2.5,
                reviewed_at=future_day,
            )
        )
        db.commit()
    finally:
        session_generator.close()

    response = memory_client.get("/api/stats/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_cards"] == 3
    assert payload["today_reviewed"] == 1
    assert payload["daily_new_avg"] == 0.1
    assert payload["daily_review_avg"] == 0.3


def test_analytics_excludes_archived_and_deleted_content(memory_client) -> None:
    override_get_session = app.dependency_overrides[get_session]
    session_generator = override_get_session()
    db = next(session_generator)
    try:
        active_deck = Deck(name="Active Deck", default_scheduler_type="sm2_basic")
        archived_deck = Deck(
            name="Archived Deck",
            default_scheduler_type="sm2_basic",
            visibility="archived",
        )
        deleted_deck = Deck(
            name="Deleted Deck",
            default_scheduler_type="sm2_basic",
            deleted_at=datetime.now(timezone.utc),
        )
        db.add(active_deck)
        db.add(archived_deck)
        db.add(deleted_deck)
        db.commit()
        db.refresh(active_deck)
        db.refresh(archived_deck)
        db.refresh(deleted_deck)

        now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)

        active_card = Card(
            deck_id=active_deck.id,
            card_type="recall",
            front="Active",
            back="Active",
            render_format="markdown",
            created_at=now,
        )
        archived_card = Card(
            deck_id=active_deck.id,
            card_type="recall",
            front="Archived",
            back="Archived",
            render_format="markdown",
            status="archived",
            deleted_at=now,
            created_at=now,
        )
        deleted_card = Card(
            deck_id=active_deck.id,
            card_type="recall",
            front="Deleted",
            back="Deleted",
            render_format="markdown",
            deleted_at=now,
            created_at=now,
        )
        archived_deck_card = Card(
            deck_id=archived_deck.id,
            card_type="recall",
            front="Archived deck",
            back="Archived deck",
            render_format="markdown",
            created_at=now,
        )
        deleted_deck_card = Card(
            deck_id=deleted_deck.id,
            card_type="recall",
            front="Deleted deck",
            back="Deleted deck",
            render_format="markdown",
            created_at=now,
        )
        db.add(active_card)
        db.add(archived_card)
        db.add(deleted_card)
        db.add(archived_deck_card)
        db.add(deleted_deck_card)
        db.commit()
        db.refresh(active_card)
        db.refresh(archived_card)
        db.refresh(deleted_card)
        db.refresh(archived_deck_card)
        db.refresh(deleted_deck_card)
        active_deck_id = active_deck.id

        db.add(ReviewLog(card_id=active_card.id, grade="good", interval_days=1, ease_factor=2.5, reviewed_at=now))
        db.add(ReviewLog(card_id=archived_card.id, grade="again", interval_days=1, ease_factor=2.5, reviewed_at=now))
        db.add(ReviewLog(card_id=deleted_card.id, grade="hard", interval_days=1, ease_factor=2.5, reviewed_at=now))
        db.add(ReviewLog(card_id=archived_deck_card.id, grade="easy", interval_days=1, ease_factor=2.5, reviewed_at=now))
        db.add(ReviewLog(card_id=deleted_deck_card.id, grade="good", interval_days=1, ease_factor=2.5, reviewed_at=now))
        db.commit()
    finally:
        session_generator.close()

    response = memory_client.get("/api/stats/analytics?range_days=7")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "total_cards": 1,
        "today_reviewed": 1,
        "daily_new_avg": 0.1,
        "daily_review_avg": 0.1,
    }
    assert payload["trend"]["points"][-1]["review_count"] == 1
    assert payload["grade_distribution"]["total_reviews"] == 1
    assert [item["grade"] for item in payload["grade_distribution"]["items"]] == ["again", "hard", "good", "easy"]
    assert [item["count"] for item in payload["grade_distribution"]["items"]] == [0, 0, 1, 0]
    assert payload["deck_activity"]["items"] == [
        {"deck_id": active_deck_id, "deck_name": "Active Deck", "review_count": 1, "unique_cards": 1}
    ]


def test_analytics_uses_one_reference_time_per_response(session) -> None:
    service = AnalyticsService()
    now = datetime(2026, 4, 21, 23, 59, tzinfo=timezone.utc)

    deck = Deck(name="Time Deck", default_scheduler_type="sm2_basic")
    session.add(deck)
    session.commit()
    session.refresh(deck)

    card = Card(
        deck_id=deck.id,
        card_type="recall",
        front="Time",
        back="Time",
        render_format="markdown",
        created_at=now,
    )
    session.add(card)
    session.commit()
    session.refresh(card)
    session.add(ReviewLog(card_id=card.id, grade="good", interval_days=1, ease_factor=2.5, reviewed_at=now))
    session.commit()

    calls: list[datetime] = []

    def fake_reference_time() -> datetime:
        calls.append(now)
        return now

    setattr(service, "_reference_time", fake_reference_time)

    payload = service.get_analytics(session, range_days=7)

    assert len(calls) == 1
    assert payload.summary.total_cards == 1
