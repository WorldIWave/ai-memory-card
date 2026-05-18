# Input: Session 与统计时间范围  |  Output: StatsSummaryRead、StatsAnalyticsRead 等聚合结果
# Output: 汇总 review_log/card/deck 数据，生成数据页的趋势、评分分布和牌组活跃度
# Role: 这是后端分析页的核心聚合服务，避免把统计 SQL 散落到 routes
# Use: 新增统计卡片或图表时优先扩这里；注意保持空数据时也返回稳定结构
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from app.db.models import Card, Deck, ReviewLog
from app.schemas.stats import (
    DeckActivityItemRead,
    DeckActivityRead,
    GradeDistributionItemRead,
    GradeDistributionRead,
    StatsAnalyticsRead,
    StatsSummaryRead,
    StatsTrendPointRead,
    StatsTrendRead,
)


class AnalyticsService:
    VALID_RANGE_DAYS = {7, 30}
    GRADE_ORDER = ("again", "hard", "good", "easy")

    def _as_utc_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _reference_time(self) -> datetime:
        return datetime.now(timezone.utc)

    def _normalize_range_days(self, range_days: int | str) -> int:
        try:
            normalized = int(range_days)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="range_days must be 7 or 30")
        if normalized not in self.VALID_RANGE_DAYS:
            raise HTTPException(status_code=400, detail="range_days must be 7 or 30")
        return normalized

    def _build_window(self, now: datetime, *, range_days: int) -> tuple[datetime, datetime, datetime]:
        current = self._as_utc_datetime(now)
        today_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
        window_start = today_start - timedelta(days=range_days - 1)
        tomorrow_start = today_start + timedelta(days=1)
        return today_start, window_start, tomorrow_start

    def _summary_active_filters(self) -> list[object]:
        return [
            Card.status == "active",
            Card.deleted_at.is_(None),
            Deck.visibility != "archived",
            Deck.deleted_at.is_(None),
        ]

    def _review_filters(self, start: datetime, end: datetime) -> list[object]:
        return [
            ReviewLog.trigger_type == "scheduled",
            ReviewLog.is_undone == False,  # noqa: E712
            ReviewLog.reviewed_at >= start,
            ReviewLog.reviewed_at < end,
            Card.status == "active",
            Card.deleted_at.is_(None),
            Deck.visibility != "archived",
            Deck.deleted_at.is_(None),
        ]

    def _count_reviews(self, session: Session, *, start: datetime, end: datetime) -> int:
        return (
            session.exec(
                select(func.count(ReviewLog.id))
                .join(Card, Card.id == ReviewLog.card_id)
                .join(Deck, Deck.id == Card.deck_id)
                .where(*self._review_filters(start, end))
            ).one()
            or 0
        )

    def _load_review_rows(
        self,
        session: Session,
        *,
        window_start: datetime,
        tomorrow_start: datetime,
    ) -> list[tuple[ReviewLog, Card, Deck]]:
        query = (
            select(ReviewLog, Card, Deck)
            .join(Card, Card.id == ReviewLog.card_id)
            .join(Deck, Deck.id == Card.deck_id)
            .where(*self._review_filters(window_start, tomorrow_start))
            .order_by(ReviewLog.reviewed_at.asc(), ReviewLog.id.asc())
        )
        return session.exec(query).all()

    def _build_summary(self, session: Session, *, now: datetime) -> StatsSummaryRead:
        today_start, week_start, tomorrow_start = self._build_window(now, range_days=7)

        total_cards = (
            session.exec(
                select(func.count(Card.id))
                .join(Deck, Deck.id == Card.deck_id)
                .where(*self._summary_active_filters())
            ).one()
            or 0
        )
        today_reviewed = self._count_reviews(session, start=today_start, end=tomorrow_start)
        week_new_cards = (
            session.exec(
                select(func.count(Card.id))
                .join(Deck, Deck.id == Card.deck_id)
                .where(*self._summary_active_filters())
                .where(Card.created_at >= week_start)
                .where(Card.created_at < tomorrow_start)
            ).one()
            or 0
        )
        week_reviews = self._count_reviews(session, start=week_start, end=tomorrow_start)

        return StatsSummaryRead(
            total_cards=total_cards,
            today_reviewed=today_reviewed,
            daily_new_avg=round(week_new_cards / 7, 1),
            daily_review_avg=round(week_reviews / 7, 1),
        )

    def get_summary(self, session: Session) -> StatsSummaryRead:
        return self._build_summary(session, now=self._reference_time())

    def get_analytics(self, session: Session, *, range_days: int) -> StatsAnalyticsRead:
        range_days = self._normalize_range_days(range_days)

        now = self._reference_time()
        summary = self._build_summary(session, now=now)
        _today_start, window_start, tomorrow_start = self._build_window(now, range_days=range_days)
        review_rows = self._load_review_rows(
            session,
            window_start=window_start,
            tomorrow_start=tomorrow_start,
        )
        trend = self._build_trend(window_start=window_start, range_days=range_days, review_rows=review_rows)
        grade_distribution = self._build_grade_distribution(review_rows=review_rows)
        deck_activity = self._build_deck_activity(review_rows=review_rows, range_days=range_days)
        return StatsAnalyticsRead(
            summary=summary,
            trend=trend,
            grade_distribution=grade_distribution,
            deck_activity=deck_activity,
        )

    def _build_trend(
        self,
        *,
        window_start: datetime,
        range_days: int,
        review_rows: list[tuple[ReviewLog, Card, Deck]],
    ) -> StatsTrendRead:
        points_by_date: dict[str, int] = {
            (window_start + timedelta(days=offset)).date().isoformat(): 0 for offset in range(range_days)
        }

        for review_log, _card, _deck in review_rows:
            day_key = self._as_utc_datetime(review_log.reviewed_at).date().isoformat()
            if day_key in points_by_date:
                points_by_date[day_key] += 1

        return StatsTrendRead(
            range_days=range_days,
            points=[
                StatsTrendPointRead(date=date_key, review_count=points_by_date[date_key])
                for date_key in points_by_date
            ],
        )

    def _build_grade_distribution(
        self,
        *,
        review_rows: list[tuple[ReviewLog, Card, Deck]],
    ) -> GradeDistributionRead:
        counts = Counter(review_log.grade for review_log, _card, _deck in review_rows)
        total_reviews = sum(counts.values())
        return GradeDistributionRead(
            total_reviews=total_reviews,
            items=[
                GradeDistributionItemRead(
                    grade=grade,
                    count=counts.get(grade, 0),
                    ratio=(counts.get(grade, 0) / total_reviews) if total_reviews else 0.0,
                )
                for grade in self.GRADE_ORDER
            ],
        )

    def _build_deck_activity(
        self,
        *,
        range_days: int,
        review_rows: list[tuple[ReviewLog, Card, Deck]],
    ) -> DeckActivityRead:
        deck_rows: dict[int, dict[str, object]] = defaultdict(lambda: {"deck_name": "", "review_count": 0, "card_ids": set()})

        for review_log, card, deck in review_rows:
            row = deck_rows[deck.id or 0]
            row["deck_name"] = deck.name
            row["review_count"] = int(row["review_count"]) + 1
            card_ids = row["card_ids"]
            assert isinstance(card_ids, set)
            card_ids.add(card.id or 0)

        items = [
            DeckActivityItemRead(
                deck_id=deck_id,
                deck_name=str(row["deck_name"]),
                review_count=int(row["review_count"]),
                unique_cards=len(row["card_ids"]) if isinstance(row["card_ids"], set) else 0,
            )
            for deck_id, row in deck_rows.items()
        ]
        items.sort(key=lambda item: (-item.review_count, -item.unique_cards, item.deck_name))
        return DeckActivityRead(range_days=range_days, items=items)
