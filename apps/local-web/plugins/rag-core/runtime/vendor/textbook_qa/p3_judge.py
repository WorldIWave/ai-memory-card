# Input: candidate QA pairs and an API-backed OpenAI-compatible judge client.
# Output: final QA pairs plus auditable keep/revise/drop judge decisions.
# Role: filter and correct P3 local-model candidates for quality and faithfulness.
# Note: tests inject fake clients; live API keys are read by callers, not this module.

from __future__ import annotations

import json
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Callable

from textbook_qa.llm_client import ChatClient, ChatMessage
from textbook_qa.llm_json import parse_llm_json_payload
from textbook_qa.schemas import QuestionAnswerPair

_ALLOWED_DECISIONS = {"keep", "revise", "drop"}
_DIMENSION_KEYS = (
    "faithfulness",
    "standalone",
    "learning_value",
    "rigor",
    "completeness",
    "redundancy_risk",
    "support_use",
    "context_grounding",
    "redundancy",
)
_MIN_DIMENSION_SCORES = {
    "faithfulness": 0.65,
    "standalone": 0.55,
    "learning_value": 0.45,
    "rigor": 0.35,
    "completeness": 0.35,
    "support_use": 0.45,
    "context_grounding": 0.45,
}
_MAX_REDUNDANCY_RISK_SCORE = 0.85
_FAILURE_MODES = {
    "extraction_fragment",
    "missing_rag_context",
    "ignored_support_evidence",
    "weak_generation",
    "answer_not_faithful",
    "non_standalone_question",
    "incomplete_answer",
    "redundant_question",
    "non_instructional_content",
}
_MODULE_ATTRIBUTIONS = {"extraction", "rag", "generation", "judge", "postprocess", "none"}


@dataclass
class JudgeDecision:
    index: int
    decision: str
    score: float = 0.0
    rationale: str = ""
    question: str = ""
    answer: str = ""
    dimension_scores: dict[str, float] = field(default_factory=dict)
    failure_modes: list[str] = field(default_factory=list)
    module_attribution: str = ""
    quality_gate_reason: str = ""


@dataclass
class JudgeResult:
    final_pairs: list[QuestionAnswerPair]
    decisions: list[JudgeDecision]
    raw_responses: list[str]


def judge_qa_pairs(
    pairs: Sequence[QuestionAnswerPair],
    client: ChatClient,
    *,
    max_pairs_per_call: int = 12,
    on_decision: Callable[[JudgeDecision], None] | None = None,
    on_final_pair: Callable[[QuestionAnswerPair], None] | None = None,
) -> JudgeResult:
    final_pairs: list[QuestionAnswerPair] = []
    decisions: list[JudgeDecision] = []
    raw_responses: list[str] = []

    for batch_start in range(0, len(pairs), max(1, max_pairs_per_call)):
        batch = list(pairs[batch_start : batch_start + max(1, max_pairs_per_call)])
        response_text = client.complete(
            [
                ChatMessage(role="system", content=_system_prompt()),
                ChatMessage(role="user", content=_batch_prompt(batch, start_index=batch_start)),
            ],
            temperature=0.0,
            max_tokens=_max_tokens_for_judge_batch(len(batch)),
        )
        raw_responses.append(response_text)
        batch_decisions = [_apply_quality_gate(decision) for decision in _parse_decisions(response_text)]
        decisions.extend(batch_decisions)
        if on_decision is not None:
            for decision in batch_decisions:
                on_decision(decision)
        decision_by_index = {decision.index: decision for decision in batch_decisions}
        for offset, pair in enumerate(batch):
            global_index = batch_start + offset
            decision = decision_by_index.get(global_index)
            if decision is None:
                final_pair = _with_judge_metadata(pair, "keep_unjudged", 0.0, "judge omitted this item")
                final_pairs.append(final_pair)
                if on_final_pair is not None:
                    on_final_pair(final_pair)
                continue
            if decision.decision == "drop":
                continue
            final_pair = _apply_decision(pair, decision)
            final_pairs.append(final_pair)
            if on_final_pair is not None:
                on_final_pair(final_pair)

    return JudgeResult(final_pairs=final_pairs, decisions=decisions, raw_responses=raw_responses)


def _max_tokens_for_judge_batch(batch_size: int) -> int:
    return min(5000, 1800 + max(0, batch_size - 1) * 220)


def _system_prompt() -> str:
    return (
        "You are a strict textbook QA judge. Return JSON only. "
        "For each item decide keep, revise, or drop based on source faithfulness, standalone clarity, reusable learning value, answer rigor, completeness, and redundancy risk. "
        "Also provide dimension_scores with faithfulness, standalone, learning_value, rigor, completeness, redundancy_risk, support_use, and context_grounding in the 0.0-1.0 range. "
        "For redundancy_risk, 0.0 means unique or non-duplicative, and 1.0 means highly redundant with other candidates. "
        "For support_use, score whether the answer used required support evidence; if no support evidence is required, set support_use to 1.0 unless the answer ignores visible support that should be used. "
        "Also provide failure_modes and module_attribution. failure_modes should use only: extraction_fragment, missing_rag_context, ignored_support_evidence, weak_generation, answer_not_faithful, non_standalone_question, incomplete_answer, redundant_question, non_instructional_content. "
        "module_attribution must be one of extraction, rag, generation, judge, postprocess, or none, indicating the main source of the problem. "
        "Drop items whose evidence is non-instructional rather than core textbook knowledge. "
        "Drop or revise questions that are not standalone, including vague references like in the text, above, this example, \u6587\u4e2d, \u4e0a\u8ff0, \u8fd9\u4e2a, or \u7ed9\u51fa\u7684."
    )


def _batch_prompt(pairs: Sequence[QuestionAnswerPair], *, start_index: int) -> str:
    items = []
    for offset, pair in enumerate(pairs):
        items.append(
            {
                "index": start_index + offset,
                "question": pair.question,
                "answer": pair.answer,
                "question_type": pair.question_type.value,
                "difficulty": pair.difficulty.value,
                "concepts": pair.concepts,
                "content_role": str(pair.metadata.get("content_role") or ""),
                "generation_metadata": _generation_metadata(pair),
                "evidence": {
                    "source": pair.source.source,
                    "line_start": pair.source.line_start,
                    "line_end": pair.source.line_end,
                    "text": pair.source.text,
                    "rag_context": str(pair.metadata.get("rag_context") or pair.source.text),
                },
            }
        )
    payload = {
        "schema": {
            "decisions": [
                {
                    "index": 0,
                    "decision": "keep|revise|drop",
                    "question": "required only for revise",
                    "answer": "required only for revise",
                    "score": 0.0,
                    "dimension_scores": {
                        "faithfulness": 0.0,
                        "standalone": 0.0,
                        "learning_value": 0.0,
                        "rigor": 0.0,
                        "completeness": 0.0,
                        "redundancy_risk": 0.0,
                        "support_use": 0.0,
                        "context_grounding": 0.0,
                    },
                    "failure_modes": [
                        "extraction_fragment|missing_rag_context|ignored_support_evidence|weak_generation|answer_not_faithful|non_standalone_question|incomplete_answer|redundant_question|non_instructional_content"
                    ],
                    "module_attribution": "extraction|rag|generation|judge|postprocess|none",
                    "rationale": "short reason",
                }
            ]
        },
        "items": items,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _generation_metadata(pair: QuestionAnswerPair) -> dict[str, object]:
    metadata = pair.metadata
    keys = (
        "rag_unit_id",
        "concept_id",
        "question_plan_id",
        "question_plan_type",
        "required_support_roles",
        "required_support_member_ids",
        "support_snippets",
        "support_usage_status",
        "used_support_roles",
        "used_support_member_ids",
        "matched_support_snippets",
        "unused_support_roles",
        "kp_type",
        "content_role",
    )
    return {key: deepcopy(metadata.get(key)) for key in keys if key in metadata}


def _parse_decisions(text: str) -> list[JudgeDecision]:
    try:
        payload = parse_llm_json_payload(text)
    except (json.JSONDecodeError, ValueError):
        return []
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = payload.get("decisions", [])
    else:
        raw_items = []
    decisions: list[JudgeDecision] = []
    if not isinstance(raw_items, list):
        return decisions
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        decision = str(item.get("decision") or "").strip().casefold()
        if decision not in _ALLOWED_DECISIONS:
            continue
        decisions.append(
            JudgeDecision(
                index=_int_value(item.get("index"), -1),
                decision=decision,
                score=_float_value(item.get("score"), 0.0),
                rationale=str(item.get("rationale") or "").strip(),
                question=str(item.get("question") or "").strip(),
                answer=str(item.get("answer") or "").strip(),
                dimension_scores=_dimension_scores(item),
                failure_modes=_failure_modes(item),
                module_attribution=_module_attribution(item),
            )
        )
    return [decision for decision in decisions if decision.index >= 0]



def _apply_quality_gate(decision: JudgeDecision) -> JudgeDecision:
    if decision.decision == "drop":
        return decision
    reason = _quality_gate_reason(decision.dimension_scores)
    if not reason:
        return decision
    decision.decision = "drop"
    decision.quality_gate_reason = reason
    gate_note = f"quality_gate:{reason}"
    decision.rationale = f"{decision.rationale}; {gate_note}" if decision.rationale else gate_note
    return decision


def _quality_gate_reason(scores: dict[str, float]) -> str:
    if not scores:
        return ""
    for key, minimum in _MIN_DIMENSION_SCORES.items():
        if key in scores and scores[key] < minimum:
            return f"low_{key}"
    if scores.get("redundancy_risk", 0.0) > _MAX_REDUNDANCY_RISK_SCORE:
        return "high_redundancy_risk"
    return ""


def _apply_decision(pair: QuestionAnswerPair, decision: JudgeDecision) -> QuestionAnswerPair:
    if decision.decision == "revise":
        question = decision.question or pair.question
        answer = decision.answer or pair.answer
        return _with_judge_metadata(
            replace(pair, question=question, answer=answer),
            decision.decision,
            decision.score,
            decision.rationale,
            decision.dimension_scores,
            decision.failure_modes,
            decision.module_attribution,
        )
    return _with_judge_metadata(
        pair,
        decision.decision,
        decision.score,
        decision.rationale,
        decision.dimension_scores,
        decision.failure_modes,
        decision.module_attribution,
    )


def _with_judge_metadata(
    pair: QuestionAnswerPair,
    decision: str,
    score: float,
    rationale: str,
    dimension_scores: dict[str, float] | None = None,
    failure_modes: Sequence[str] | None = None,
    module_attribution: str = "",
) -> QuestionAnswerPair:
    metadata = deepcopy(pair.metadata)
    metadata.update(
        {
            "judge_decision": decision,
            "judge_score": score,
            "judge_rationale": rationale,
        }
    )
    dimensions = dict(dimension_scores or {})
    if dimensions:
        metadata["judge_dimension_scores"] = dimensions
        for key, value in dimensions.items():
            metadata[f"judge_{key}"] = value
    cleaned_failure_modes = list(failure_modes or [])
    if cleaned_failure_modes:
        metadata["judge_failure_modes"] = cleaned_failure_modes
    if module_attribution:
        metadata["judge_module_attribution"] = module_attribution
    return replace(pair, metadata=metadata)


def _failure_modes(item: dict[str, object]) -> list[str]:
    raw_modes = item.get("failure_modes") or item.get("failure_mode") or item.get("diagnostic_tags")
    if isinstance(raw_modes, str):
        values = [raw_modes]
    elif isinstance(raw_modes, list):
        values = [str(value) for value in raw_modes]
    else:
        values = []
    modes: list[str] = []
    for value in values:
        mode = value.strip().casefold().replace("-", "_").replace(" ", "_")
        if mode in _FAILURE_MODES and mode not in modes:
            modes.append(mode)
    return modes


def _module_attribution(item: dict[str, object]) -> str:
    value = str(item.get("module_attribution") or item.get("primary_module") or "").strip().casefold()
    value = value.replace("-", "_").replace(" ", "_")
    if value == "candidate_generation":
        value = "generation"
    if value == "retrieval":
        value = "rag"
    return value if value in _MODULE_ATTRIBUTIONS else ""


def _dimension_scores(item: dict[str, object]) -> dict[str, float]:
    raw_scores = item.get("dimension_scores") or item.get("dimensions") or item.get("scores")
    if not isinstance(raw_scores, dict):
        return {}
    scores: dict[str, float] = {}
    for key in _DIMENSION_KEYS:
        if key in raw_scores:
            scores[key] = _float_value(raw_scores.get(key), 0.0)
    return scores


def _int_value(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _float_value(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
