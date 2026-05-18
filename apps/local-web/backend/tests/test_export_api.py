# Input: FastAPI TestClient（内置 app）  |  Output: JSON/CSV 导出格式的 HTTP 断言
# Role: 卡片导出 API（/api/exports/cards）的集成测试，覆盖 json 和 csv 两种格式
# Note: 依赖 conftest 的 reset_app_database (autouse)，无需额外 fixture 参数
# Usage: pytest tests/test_export_api.py
from fastapi.testclient import TestClient

from app.main import app


def test_export_cards_as_json_contains_decks_and_cards() -> None:
    with TestClient(app) as client:
        deck_resp = client.post("/api/decks", json={"name": "Export Deck"})
        assert deck_resp.status_code == 201
        deck_id = deck_resp.json()["id"]

        card_resp = client.post(
            "/api/cards",
            json={
                "deck_id": deck_id,
                "card_type": "recall",
                "front": "What is AI?",
                "back": "A field of computer science.",
                "render_format": "markdown",
            },
        )
        assert card_resp.status_code == 201

        export_resp = client.get("/api/exports/cards", params={"format": "json"})

        assert export_resp.status_code == 200
        payload = export_resp.json()
        assert payload["format"] == "json"
        deck_names = [row["name"] for row in payload["payload"]["decks"]]
        fronts = [row["front"] for row in payload["payload"]["cards"]]
        assert "Export Deck" in deck_names
        assert "What is AI?" in fronts


def test_export_cards_as_csv_returns_rows() -> None:
    with TestClient(app) as client:
        deck_resp = client.post("/api/decks", json={"name": "Export CSV"})
        assert deck_resp.status_code == 201
        deck_id = deck_resp.json()["id"]

        card_resp = client.post(
            "/api/cards",
            json={
                "deck_id": deck_id,
                "card_type": "recall",
                "front": "Q",
                "back": "A",
                "render_format": "markdown",
            },
        )
        assert card_resp.status_code == 201

        export_resp = client.get("/api/exports/cards", params={"format": "csv"})

        assert export_resp.status_code == 200
        payload = export_resp.json()
        assert payload["format"] == "csv"
        assert "front,back" in payload["payload"]
        assert "Q,A" in payload["payload"]
