# Input: 3 张卡片（due_at 各不同）+ 手动操纵 CardReviewState  |  Output: 断言队列排序正确
# Role: 集成测试，验证 /api/review/queue 按到期时间先后返回逾期卡片优先的排序
# Note: 直接操作 Session 修改 next_due_at，绕过业务层；测试结束后数据随内存 DB 清除
# Usage: pytest tests/test_review_queue.py，依赖 conftest 提供隔离的测试数据库
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db.models import CardReviewState
from app.db.session import engine
from app.main import app


def test_review_queue_returns_due_cards_first() -> None:
    with TestClient(app) as client:
        deck_response = client.post("/api/decks", json={"name": "Queue Deck"})
        assert deck_response.status_code == 201
        deck_id = deck_response.json()["id"]

        card_ids: list[int] = []
        for idx in range(3):
            card_response = client.post(
                "/api/cards",
                json={
                    "deck_id": deck_id,
                    "card_type": "recall",
                    "front": f"q{idx}",
                    "back": f"a{idx}",
                    "render_format": "markdown",
                },
            )
            assert card_response.status_code == 201
            card_ids.append(card_response.json()["id"])

        now = datetime.now(timezone.utc)
        with Session(engine) as session:
            states = list(
                session.exec(
                    select(CardReviewState).where(CardReviewState.card_id.in_(card_ids))
                ).all()
            )
            for state in states:
                if state.card_id == card_ids[0]:
                    state.next_due_at = now - timedelta(days=2)
                elif state.card_id == card_ids[1]:
                    state.next_due_at = now + timedelta(days=1)
                else:
                    state.next_due_at = now - timedelta(hours=1)
                session.add(state)
            session.commit()

        queue_response = client.get("/api/review/queue")

    assert queue_response.status_code == 200
    queue_ids = [row["id"] for row in queue_response.json()]
    selected = [card_id for card_id in queue_ids if card_id in card_ids]
    assert selected == [card_ids[0], card_ids[2], card_ids[1]]
