from __future__ import annotations

from typing import Any


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _understanding_scores(payload: dict[str, Any]) -> list[float]:
    understanding = payload.get("understanding") or {}
    scores = understanding.get("scores") if isinstance(understanding, dict) else {}
    if not isinstance(scores, dict):
        return []
    return [
        _as_float(scores[name], 100.0)
        for name in ("mastery", "mechanism", "boundary")
        if name in scores
    ]


def plan_review(payload: dict[str, Any]) -> dict[str, Any]:
    baseline_decision = payload.get("baseline_decision") or {}
    baseline_interval = _as_float(
        baseline_decision.get("interval_days") if isinstance(baseline_decision, dict) else None,
        1.0,
    )
    baseline_interval = max(1.0, baseline_interval)
    interval_days = baseline_interval
    confidence = 0.62
    rationale: list[str] = []
    used_signals = ["grade", "baseline_interval"]

    grade = payload.get("grade")
    if grade == "again":
        interval_days = 1.0
        confidence = 0.8
        rationale.append("again grade resets the review interval")
    else:
        scores = _understanding_scores(payload)
        if scores:
            used_signals.append("understanding_scores")
            min_score = min(scores)
            if min_score < 50:
                interval_days *= 0.75
                confidence = 0.72
                rationale.append("low understanding score shortened the baseline interval")
            elif min_score >= 80:
                interval_days *= 1.15
                confidence = 0.68
                rationale.append("high understanding score slightly extended the baseline interval")

        state = payload.get("state") or {}
        session_repeats_today = 0.0
        if isinstance(state, dict):
            session_repeats_today = _as_float(state.get("session_repeats_today"), 0.0)
        if session_repeats_today >= 3:
            interval_days *= 0.85
            used_signals.append("session_repeats_today")
            rationale.append("same-day repeats made the decision more conservative")

        grade_adjustments = {"hard": 0.9, "good": 1.0, "easy": 1.1}
        if grade in grade_adjustments:
            interval_days *= grade_adjustments[grade]
            rationale.append(f"{grade} grade adjusted the interval")

    max_interval = baseline_interval * 1.5
    interval_days = min(max(interval_days, 1.0), max_interval)
    if not rationale:
        rationale.append("baseline interval kept")

    return {
        "scheduler_type": "ai_rl_v1",
        "interval_days": round(interval_days, 2),
        "confidence": round(confidence, 2),
        "source": "uacis_lite",
        "rationale": rationale,
        "used_signals": used_signals,
    }
