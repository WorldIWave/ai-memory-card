from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime.app.main import app


def test_capabilities_include_scheduler_plan_review() -> None:
    client = TestClient(app)

    response = client.get("/capabilities")

    assert response.status_code == 200
    capability_names = {item["name"] for item in response.json()["capabilities"]}
    assert capability_names >= {
        "rag.generate_cards",
        "evaluation.score_explanation",
        "scheduler.plan_review",
    }


def test_scheduler_plan_review_shortens_low_understanding_baseline_interval() -> None:
    client = TestClient(app)

    response = client.post(
        "/tasks/scheduler.plan_review",
        json={
            "capability": "scheduler.plan_review",
            "mode": "local",
            "grade": "good",
            "card": {"id": 12, "front": "Why does regularization reduce overfitting?"},
            "state": {"session_repeats_today": 1},
            "review_history": [],
            "understanding": {
                "scores": {
                    "mastery": 42,
                    "mechanism": 48,
                    "boundary": 55,
                }
            },
            "recent_burden": {},
            "baseline_decision": {"interval_days": 8},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    result = payload["result"]
    assert result["scheduler_type"] == "ai_rl_v1"
    assert result["interval_days"] < 8
    assert result["source"] == "uacis_lite"
