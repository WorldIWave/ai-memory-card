# Input: baseline session scheduling decision and optional AI/RL plugin output
# Output: validated SessionScheduleResult for persistence by ReviewService
# Role: Isolates advisory AI/RL scheduling from review session state mutation
# Use: ReviewService delegates interval adjustment here; this service never writes the DB
from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session

from app.db.models import Card, CardReviewState
from app.schemas.review import ReviewSessionContext, SessionScheduleResult
from app.services.ai_plugin_host_service import AIPluginHostService
from app.services.review_scheduler_context import build_scheduler_plan_payload
from app.services.study_settings_service import StudySettingsService


class AISchedulerDecisionService:
    def __init__(
        self,
        *,
        study_settings_service: StudySettingsService,
        ai_plugin_host_service: AIPluginHostService,
    ) -> None:
        self._study_settings_service = study_settings_service
        self._ai_plugin_host_service = ai_plugin_host_service

    def plan(
        self,
        db: Session,
        *,
        card: Card,
        state: CardReviewState,
        grade: str,
        context: ReviewSessionContext,
        baseline_decision: SessionScheduleResult,
    ) -> SessionScheduleResult:
        settings = self._study_settings_service.get(db)
        if settings.scheduler_mode != "ai_rl":
            return baseline_decision

        payload = build_scheduler_plan_payload(
            db,
            card=card,
            state=state,
            grade=grade,
            context=context,
            baseline_decision=baseline_decision,
        )
        try:
            plugin_result = self._ai_plugin_host_service.run_scheduler_plan_review(payload)
            return self._coerce_ai_rl_decision(
                plugin_result,
                baseline=baseline_decision,
                context=context,
            )
        except Exception as exc:
            return baseline_decision.model_copy(
                update={
                    "reason": f"{baseline_decision.reason}; fallback after ai_rl scheduler error: {exc}",
                    "explainability": {
                        **baseline_decision.explainability,
                        "ai_rl_fallback": 1,
                    },
                }
            )

    def _coerce_ai_rl_decision(
        self,
        result: dict[str, object],
        *,
        baseline: SessionScheduleResult,
        context: ReviewSessionContext,
    ) -> SessionScheduleResult:
        interval_days = self._validated_ai_rl_interval(result.get("interval_days"), baseline)
        next_due_at = context.now + timedelta(days=interval_days)
        confidence = result.get("confidence")
        source = str(result.get("source") or "scheduler.plan_review")
        rationale = result.get("rationale")
        rationale_items = [str(item) for item in rationale] if isinstance(rationale, list) else []
        rationale_text = "; ".join(rationale_items) if rationale_items else source
        confidence_value = float(confidence) if isinstance(confidence, (int, float)) else 0.0
        return baseline.model_copy(
            update={
                "scheduler_type": str(result.get("scheduler_type") or "ai_rl_v1"),
                "interval_days": interval_days,
                "next_due_at": next_due_at,
                "reason": (
                    "ai_rl plugin adjusted interval from "
                    f"{baseline.interval_days} to {interval_days}: {rationale_text}"
                ),
                "state_patch": {
                    **baseline.state_patch,
                    "interval_days": interval_days,
                    "next_due_at": next_due_at.isoformat(),
                    "scheduler_meta": {
                        "source": source,
                        "confidence": confidence_value,
                        "rationale": rationale_items,
                        "baseline_interval_days": baseline.interval_days,
                    },
                },
                "explainability": {
                    **baseline.explainability,
                    "ai_rl_confidence": confidence_value,
                    "baseline_interval_days": baseline.interval_days,
                },
            }
        )

    def _validated_ai_rl_interval(
        self,
        raw_value: object,
        baseline: SessionScheduleResult,
    ) -> float:
        try:
            interval_days = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("AI/RL scheduler returned invalid interval_days") from exc
        lower = 1.0
        upper = max(1.0, baseline.interval_days * 1.5)
        return round(min(max(interval_days, lower), upper), 2)
