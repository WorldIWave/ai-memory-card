# Input: FastAPI TestClient + 临时内存数据库  |  Output: 断言复习提交后返回调度决策
# Role: 集成测试，覆盖「创建牌组→创建卡片→提交复习」完整端到端流程
# Note: 依赖 conftest 中的测试数据库配置；验证 SM2 调度结果中 interval_days > 0
# Usage: pytest tests/test_review_flow.py，需先确保 conftest 正确设置测试 DB
from fastapi.testclient import TestClient

from app.main import app


def test_submit_review_flow_creates_schedule_decision() -> None:
    with TestClient(app) as client:
        deck_response = client.post("/api/decks", json={"name": "Review Flow"})
        assert deck_response.status_code == 201
        deck_id = deck_response.json()["id"]

        card_response = client.post(
            "/api/cards",
            json={
                "deck_id": deck_id,
                "card_type": "recall",
                "front": "What is spaced repetition?",
                "back": "A memory technique that schedules reviews.",
                "render_format": "markdown",
            },
        )
        assert card_response.status_code == 201
        card_id = card_response.json()["id"]

        review_response = client.post(
            "/api/review/submit",
            json={
                "card_id": card_id,
                "grade": "good",
                "review_mode": "flip_card",
                "trigger_type": "scheduled",
            },
        )

        assert review_response.status_code == 200
        payload = review_response.json()
        assert payload["scheduler_type"] == "sm2_basic"
        assert payload["interval_days"] > 0


def test_legacy_submit_route_is_marked_deprecated() -> None:
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    submit_operation = response.json()["paths"]["/api/review/submit"]["post"]
    assert submit_operation["deprecated"] is True
