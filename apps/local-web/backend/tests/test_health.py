# Input: FastAPI TestClient（内置 app）  |  Output: /api/health 端点的 HTTP 断言
# Role: 最小冒烟测试，验证后端服务启动正常并能响应健康检查
# Note: 依赖 conftest 的 reset_app_database (autouse)，无其他 fixture 依赖
# Usage: pytest tests/test_health.py
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
