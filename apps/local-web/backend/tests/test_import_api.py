# Input: FastAPI TestClient + JSON 格式导入载荷  |  Output: /api/imports/cards 的 HTTP 断言
# Role: 卡片导入 API 的集成测试，验证端点能正确创建 Deck 和 Card
# Note: 依赖 conftest 的 reset_app_database (autouse)，无需额外 fixture 参数
# Usage: pytest tests/test_import_api.py
from fastapi.testclient import TestClient

from app.main import app


def test_import_cards_endpoint_creates_deck_and_cards() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/imports/cards",
            json={
                "format": "json",
                "payload": '{"deck":{"name":"Imported ML"},"cards":[{"card_type":"recall","front":"What is RAG?","back":"Retrieval augmented generation.","render_format":"markdown"}]}'
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["deck"]["name"] == "Imported ML"
    assert body["imported_count"] == 1
    assert body["cards"][0]["front"] == "What is RAG?"
