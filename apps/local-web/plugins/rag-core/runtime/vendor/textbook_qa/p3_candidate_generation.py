# Input: RAG knowledge units and a local OpenAI-compatible chat client.
# Output: candidate QuestionAnswerPair records grounded in RAG evidence.
# Role: let a local LLM synthesize candidate QA before API judge filtering.
# Note: parsing is deterministic and tests inject fake clients instead of models.

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Callable

from textbook_qa.llm_client import ChatClient, ChatMessage
from textbook_qa.llm_json import parse_llm_json_payload
from textbook_qa.local_rag.knowledge_units import RAGKnowledgeUnit
from textbook_qa.schemas import Difficulty, EvidenceSpan, QuestionAnswerPair, QuestionType

_TYPE_MAP = {
    "definition": QuestionType.DEFINITION,
    "application": QuestionType.APPLICATION,
    "reasoning": QuestionType.REASONING,
    "misconception": QuestionType.MISCONCEPTION,
    "formula": QuestionType.FORMULA,
    "deep": QuestionType.DEEP,
    "deep_reasoning": QuestionType.DEEP,
}
_DIFFICULTY_MAP = {
    "basic": Difficulty.BASIC,
    "medium": Difficulty.MEDIUM,
    "advanced": Difficulty.ADVANCED,
}


def generate_candidate_qa_pairs(
    units: Sequence[RAGKnowledgeUnit],
    client: ChatClient,
    *,
    language: str = "zh",
    max_per_unit: int = 5,
    max_total: int | None = None,
    unit_batch_size: int = 1,
    unit_batch_max_chars: int | None = None,
    unit_context_max_chars: int | None = None,
    prompt_profile: str = "default",
    on_pair: Callable[[QuestionAnswerPair], None] | None = None,
    on_batch: Callable[[dict[str, Any]], None] | None = None,
) -> list[QuestionAnswerPair]:
    pairs: list[QuestionAnswerPair] = []
    for batch_index, batch in enumerate(
        _unit_batches(list(units), unit_batch_size, max_chars=unit_batch_max_chars, context_max_chars=unit_context_max_chars)
    ):
        if max_total is not None and len(pairs) >= max_total:
            break
        units_with_sources = [(unit, _source_for_unit(unit)) for unit in batch]
        units_with_sources = [(unit, source) for unit, source in units_with_sources if source is not None]
        if not units_with_sources:
            continue
        batch_units = [unit for unit, _source in units_with_sources]
        source_by_unit_id = {unit.id: source for unit, source in units_with_sources if source is not None}
        unit_by_id = {unit.id: unit for unit in batch_units}
        prompt = _units_prompt(
            batch_units,
            max_per_unit=max_per_unit,
            context_max_chars=unit_context_max_chars,
            prompt_profile=prompt_profile,
        )
        response_text = client.complete(
            [
                ChatMessage(role="system", content=_system_prompt(language, prompt_profile=prompt_profile)),
                ChatMessage(role="user", content=prompt),
            ],
            temperature=0.2,
            max_tokens=_max_tokens_for_batch(len(batch_units)),
        )
        candidate_items = _candidate_dicts(response_text)
        per_unit_counts: dict[str, int] = {}
        accepted_pair_count = 0
        accepted_pairs_in_batch: list[QuestionAnswerPair] = []
        for item in candidate_items:
            unit = _unit_for_candidate(item, unit_by_id)
            if unit is None:
                continue
            if per_unit_counts.get(unit.id, 0) >= max_per_unit:
                continue
            source = source_by_unit_id.get(unit.id)
            if source is None:
                continue
            pair = _pair_from_candidate(item, unit, source)
            if pair is None:
                continue
            per_unit_counts[unit.id] = per_unit_counts.get(unit.id, 0) + 1
            pairs.append(pair)
            accepted_pairs_in_batch.append(pair)
            accepted_pair_count += 1
            if on_pair is not None:
                on_pair(pair)
            if max_total is not None and len(pairs) >= max_total:
                break
        if on_batch is not None:
            on_batch(
                {
                    "batch_index": batch_index,
                    "unit_ids": [unit.id for unit in batch_units],
                    "unit_count": len(batch_units),
                    "unit_payload_chars": sum(
                        _unit_payload_chars(unit, context_max_chars=unit_context_max_chars) for unit in batch_units
                    ),
                    "full_unit_payload_chars": sum(_unit_payload_chars(unit) for unit in batch_units),
                    "prompt_chars": len(prompt),
                    "raw_candidate_count": len(candidate_items),
                    "accepted_pair_count": accepted_pair_count,
                    **_support_usage_counts(accepted_pairs_in_batch),
                }
            )
    return pairs


def _support_usage_counts(pairs: Sequence[QuestionAnswerPair]) -> dict[str, int]:
    required = 0
    used = 0
    unused = 0
    for pair in pairs:
        status = str(pair.metadata.get("support_usage_status", "") or "")
        has_requirement = bool(
            pair.metadata.get("required_support_roles")
            or pair.metadata.get("required_support_member_ids")
            or pair.metadata.get("support_snippets")
        )
        if has_requirement:
            required += 1
        if status == "used":
            used += 1
        elif status == "unused_required_support":
            unused += 1
    return {
        "support_required_pair_count": required,
        "support_used_pair_count": used,
        "support_unused_pair_count": unused,
    }


def _system_prompt(language: str, *, prompt_profile: str = "default") -> str:
    if prompt_profile == "api_simple":
        return (
            "You generate grounded textbook QA pairs from one instructional knowledge unit at a time. "
            "Return JSON only. Prefer one clear standalone question per visible question plan. "
            "Keep the answer short, faithful to the provided statement, formula, conditions, and context, and copy question_plan_id exactly when plans are present. "
            f"Preferred language: {language}."
        )
    return (
        "You generate textbook study QA candidates from grounded instructional knowledge units. "
        "Return JSON only. Keep answers supported by the provided evidence. "
        "Every question must be standalone, use the complete concept phrase or formula/symbol from the unit, and avoid vague references to surrounding text. "
        "When question_plans are provided, prioritize the visible target plans and preserve their question_plan_id values exactly. "
        f"Preferred language: {language}."
    )


def _units_prompt(
    units: Sequence[RAGKnowledgeUnit],
    *,
    max_per_unit: int,
    context_max_chars: int | None = None,
    prompt_profile: str = "default",
) -> str:
    target_plans_by_unit = _target_question_plans_by_unit(units, max_per_unit=max_per_unit)
    if prompt_profile == "api_simple":
        payload = {
            "instruction": (
                "Return a JSON object with top-level key candidates. Each candidate must include unit_id, question, answer, question_type, difficulty, concepts, and question_plan_id when question_plans is non-empty. "
                "Generate concise standalone textbook QA grounded directly in the provided statement, formula, conditions, and context. "
                "Avoid vague references to surrounding text. If a visible question plan is present, choose one and copy its id exactly. "
                "If the unit does not support a clear question, return {\"candidates\": []}."
            ),
            "output_shape": {
                "candidates": [
                    {
                        "unit_id": "copy from knowledge_units[].id",
                        "question_plan_id": "copy from question_plans[].id when question_plans is non-empty",
                        "question": "...",
                        "answer": "...",
                        "question_type": "definition|application|reasoning|misconception|formula|deep",
                        "difficulty": "basic|medium|advanced",
                        "concepts": ["..."],
                    }
                ]
            },
            "max_candidates_per_unit": max_per_unit,
            "knowledge_units": [
                _unit_payload(
                    unit,
                    context_max_chars=context_max_chars,
                    question_plans=target_plans_by_unit.get(unit.id),
                    prompt_profile=prompt_profile,
                )
                for unit in units
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    payload = {
        "instruction": (
            "Return a JSON object with top-level key candidates. Each candidate must include unit_id. "
            "Use only units whose content_role is instructional or empty. "
            "Avoid vague references such as in the text, above, this example, 文中, 上述, 这个, or 给出的. "
            "Each question must be answerable without opening the original passage. "
            "Do not shorten a multi-character or multi-word concept into a fragment. "
            "Use typed relations only when they are present in knowledge_units[].relations. "
            "Use relation_linked_members as supporting context for conditions, parts, prerequisites, and contrasts; "
            "Use support_linked_members and examples as grounded support for application and misconception questions. "
            "relation_resolution explains when a relation target name was resolved to the canonical concept unit. "
            "Do not turn support members into separate vague questions. "
            "knowledge_units[].question_plans contains the target plans for this call. "
            "If a selected question plan includes required_support_roles, support_member_ids, or support_snippets, "
            "the candidate must use that support in the answer and report used_support_roles, used_support_member_ids, and support_usage_note. "
            "If the support cannot be used faithfully, skip that plan instead of fabricating an answer. "
            "If a selected knowledge_units item has non-empty question_plans, each candidate for that unit "
            "must include question_plan_id copied exactly from one of that unit's question_plans[].id values."
        ),
        "output_shape": {
            "candidates": [
                {
                    "unit_id": "copy from knowledge_units[].id",
                    "question": "...",
                    "answer": "...",
                    "question_plan_id": "required when knowledge_units[].question_plans is non-empty; copy from question_plans[].id",
                    "question_type": "definition|application|reasoning|misconception|formula|deep",
                    "difficulty": "basic|medium|advanced",
                    "concepts": ["..."],
                    "used_support_roles": ["example|misconception"],
                    "used_support_member_ids": ["copy from question_plans[].support_member_ids when used"],
                    "support_usage_note": "how support evidence was used, or empty when not required",
                    "rationale": "short grounding note",
                }
            ]
        },
        "max_candidates_per_unit": max_per_unit,
        "knowledge_units": [
            _unit_payload(
                unit,
                context_max_chars=context_max_chars,
                question_plans=target_plans_by_unit.get(unit.id),
                prompt_profile=prompt_profile,
            )
            for unit in units
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _unit_prompt(unit: RAGKnowledgeUnit, *, max_per_unit: int) -> str:
    return _units_prompt([unit], max_per_unit=max_per_unit)


def _unit_payload(
    unit: RAGKnowledgeUnit,
    *,
    context_max_chars: int | None = None,
    question_plans: Sequence[dict[str, Any]] | None = None,
    prompt_profile: str = "default",
) -> dict[str, Any]:
    visible_question_plans = list(question_plans) if question_plans is not None else list(unit.question_plans)
    payload = {
        "id": unit.id,
        "title": unit.title,
        "type": unit.type.value,
        "content_role": _content_role_for_unit(unit),
        "formulas": unit.formulas,
        "variables": [_variable_payload(variable) for variable in unit.variables],
        "conditions": unit.conditions,
        "results": unit.results,
        "misconceptions": unit.misconceptions,
        "context": _compress_context(unit.merged_context_text, context_max_chars),
    }
    if prompt_profile == "api_simple":
        payload.update(
            {
                "statement": unit.seed_point.statement,
                "question_plans": _minimal_question_plans_payload(visible_question_plans),
            }
        )
        return payload

    payload.update(
        {
            "concept_id": unit.concept_id,
            "question_plans": visible_question_plans,
            "all_question_plan_count": len(unit.question_plans),
            "examples": list(getattr(unit, "examples", [])),
            "relations": [_relation_payload(relation) for relation in unit.seed_point.relations],
            "support_linked_members": _support_linked_members_payload(unit),
            "relation_linked_members": _relation_linked_members_payload(unit),
            "relation_resolution": _relation_resolution_payload(unit),
        }
    )
    return payload


def _minimal_question_plans_payload(plans: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for item in plans:
        if not isinstance(item, dict):
            continue
        payload: dict[str, Any] = {
            "id": str(item.get("id", "") or ""),
            "type": str(item.get("type", "") or ""),
        }
        must_include = item.get("must_include")
        if isinstance(must_include, list):
            payload["must_include"] = [str(value) for value in must_include if str(value).strip()]
        payloads.append(payload)
    return payloads


def _support_linked_members_payload(unit: RAGKnowledgeUnit) -> list[dict[str, str]]:
    concept_unit = unit.metadata.get("concept_unit")
    if not isinstance(concept_unit, dict):
        return []
    raw_members = concept_unit.get("support_linked_members")
    if not isinstance(raw_members, list):
        return []

    members: list[dict[str, str]] = []
    for item in raw_members:
        if not isinstance(item, dict):
            continue
        payload = {
            "member_id": str(item.get("member_id", "") or ""),
            "member_title": str(item.get("member_title", "") or ""),
            "support_role": str(item.get("support_role", "") or ""),
            "target_concept": str(item.get("target_concept", "") or ""),
        }
        resolved_key = str(item.get("resolved_concept_key", "") or "")
        resolution_method = str(item.get("resolution_method", "") or "")
        if resolved_key:
            payload["resolved_concept_key"] = resolved_key
        if resolution_method:
            payload["resolution_method"] = resolution_method
        members.append(payload)
    return members


def _relation_resolution_payload(unit: RAGKnowledgeUnit) -> list[dict[str, str]]:
    concept_unit = unit.metadata.get("concept_unit")
    if not isinstance(concept_unit, dict):
        return []
    raw_items = concept_unit.get("relation_resolution")
    if not isinstance(raw_items, list):
        return []

    resolutions: list[dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        resolutions.append(
            {
                "requested_concept": str(item.get("requested_concept", "") or ""),
                "resolved_concept_key": str(item.get("resolved_concept_key", "") or ""),
                "method": str(item.get("method", "") or ""),
            }
        )
    return resolutions


def _relation_linked_members_payload(unit: RAGKnowledgeUnit) -> list[dict[str, str]]:
    concept_unit = unit.metadata.get("concept_unit")
    if not isinstance(concept_unit, dict):
        return []
    raw_members = concept_unit.get("relation_linked_members")
    if not isinstance(raw_members, list):
        return []

    members: list[dict[str, str]] = []
    for item in raw_members:
        if not isinstance(item, dict):
            continue
        members.append(
            {
                "member_id": str(item.get("member_id", "") or ""),
                "member_title": str(item.get("member_title", "") or ""),
                "relation_type": str(item.get("relation_type", "") or ""),
                "source_concept": str(item.get("source_concept", "") or ""),
                "target_concept": str(item.get("target_concept", "") or ""),
                "direction": str(item.get("direction", "") or ""),
            }
        )
    return members


def _minimal_question_plans_payload(plans: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for item in plans:
        if not isinstance(item, dict):
            continue
        payload: dict[str, Any] = {
            "id": str(item.get("id", "") or ""),
            "type": str(item.get("type", "") or ""),
        }
        must_include = item.get("must_include")
        if isinstance(must_include, list):
            payload["must_include"] = [str(value) for value in must_include if str(value).strip()]
        payloads.append(payload)
    return payloads


def _variable_payload(variable: Any) -> dict[str, str]:
    return {
        "symbol": str(getattr(variable, "symbol", "") or ""),
        "meaning": str(getattr(variable, "meaning", "") or ""),
        "condition": str(getattr(variable, "condition", "") or ""),
    }


def _relation_payload(relation: Any) -> dict[str, object]:
    return {
        "type": str(getattr(relation, "type", "") or ""),
        "source_concept": str(getattr(relation, "source_concept", "") or ""),
        "target_concept": str(getattr(relation, "target_concept", "") or ""),
        "evidence_text": str(getattr(relation, "evidence_text", "") or ""),
        "confidence": float(getattr(relation, "confidence", 0.0) or 0.0),
    }


def _compress_context(text: str, max_chars: int | None) -> str:
    if max_chars is None or len(text) <= max_chars:
        return text
    budget = max(1, max_chars)
    marker = "\n...[context truncated]...\n"
    if budget <= len(marker) + 2:
        return text[:budget]
    head_chars = max(1, int((budget - len(marker)) * 0.55))
    tail_chars = max(1, budget - len(marker) - head_chars)
    return text[:head_chars].rstrip() + marker + text[-tail_chars:].lstrip()


_QUESTION_PLAN_TYPE_PRIORITY = {
    "misconception": 0,
    "application": 1,
    "reasoning": 2,
    "deep": 3,
    "deep_reasoning": 3,
    "formula": 4,
    "definition": 5,
}


def _target_question_plans_by_unit(
    units: Sequence[RAGKnowledgeUnit], *, max_per_unit: int
) -> dict[str, list[dict[str, Any]]]:
    target_count = max(1, max_per_unit)
    type_counts: dict[str, int] = {}
    targets: dict[str, list[dict[str, Any]]] = {}
    for unit in units:
        available = [plan for plan in unit.question_plans if isinstance(plan, dict)]
        selected: list[dict[str, Any]] = []
        for _ in range(target_count):
            if not available:
                break
            best_index, best_plan = min(
                enumerate(available),
                key=lambda item: (
                    type_counts.get(_plan_type(item[1]), 0),
                    _QUESTION_PLAN_TYPE_PRIORITY.get(_plan_type(item[1]), 100),
                    item[0],
                ),
            )
            selected.append(best_plan)
            plan_type = _plan_type(best_plan)
            type_counts[plan_type] = type_counts.get(plan_type, 0) + 1
            del available[best_index]
        if selected:
            targets[unit.id] = selected
    return targets


def _plan_type(plan: dict[str, Any]) -> str:
    return _string(plan.get("question_type") or plan.get("type")).casefold()


def _content_role_for_unit(unit: RAGKnowledgeUnit) -> str:
    role = unit.metadata.get("content_role") or unit.seed_point.metadata.get("content_role")
    if not role:
        attrs = unit.seed_point.metadata.get("candidate_attributes")
        if isinstance(attrs, dict):
            role = attrs.get("content_role")
    return str(role or "").strip().casefold().replace("-", "_").replace(" ", "_")


def _max_tokens_for_batch(batch_size: int) -> int:
    return min(5000, 1600 + max(0, batch_size - 1) * 900)


def _unit_batches(
    units: Sequence[RAGKnowledgeUnit],
    size: int,
    *,
    max_chars: int | None = None,
    context_max_chars: int | None = None,
) -> list[list[RAGKnowledgeUnit]]:
    batch_size = max(1, size)
    char_budget = max(1, max_chars) if max_chars is not None else None
    batches: list[list[RAGKnowledgeUnit]] = []
    current: list[RAGKnowledgeUnit] = []
    current_chars = 0
    for unit in units:
        unit_chars = _unit_payload_chars(unit, context_max_chars=context_max_chars)
        if current and (
            len(current) >= batch_size or (char_budget is not None and current_chars + unit_chars > char_budget)
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(unit)
        current_chars += unit_chars
        if len(current) >= batch_size:
            batches.append(current)
            current = []
            current_chars = 0
    if current:
        batches.append(current)
    return batches


def _unit_payload_chars(unit: RAGKnowledgeUnit, *, context_max_chars: int | None = None) -> int:
    return len(
        json.dumps(
            _unit_payload(unit, context_max_chars=context_max_chars),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


def _candidate_dicts(text: str) -> list[dict[str, Any]]:
    try:
        payload = parse_llm_json_payload(text)
    except (json.JSONDecodeError, ValueError):
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        schema = payload.get("schema")
        if isinstance(schema, dict):
            candidates = schema.get("candidates", [])
    return [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []


def _unit_for_candidate(item: dict[str, Any], unit_by_id: dict[str, RAGKnowledgeUnit]) -> RAGKnowledgeUnit | None:
    unit_id = _string(item.get("unit_id") or item.get("rag_unit_id") or item.get("source_unit_id"))
    if unit_id:
        return unit_by_id.get(unit_id)
    if len(unit_by_id) == 1:
        return next(iter(unit_by_id.values()))
    return None


def _pair_from_candidate(
    item: dict[str, Any], unit: RAGKnowledgeUnit, source: EvidenceSpan
) -> QuestionAnswerPair | None:
    question = _string(item.get("question"))
    answer = _string(item.get("answer"))
    if not question or not answer:
        return None

    plan_id = _string(item.get("question_plan_id") or item.get("plan_id"))
    plan = _question_plan_for_candidate(unit, plan_id)
    if unit.question_plans and plan is None:
        return None

    concepts = _string_list(item.get("concepts")) or [unit.title]
    question_type_key = _string(item.get("question_type")).casefold()
    if plan is not None:
        question_type_key = _string(plan.get("question_type") or plan.get("type")).casefold()
    question_type = _TYPE_MAP.get(question_type_key, QuestionType.DEFINITION)
    difficulty = _DIFFICULTY_MAP.get(_string(item.get("difficulty")).casefold(), Difficulty.BASIC)
    metadata = {
        "generation_method": "p3_local_llm_candidate",
        "rag_unit_id": unit.id,
        "seed_point_id": unit.seed_point.id,
        "kp_type": unit.type.value,
        "content_role": _string(item.get("content_role")) or _content_role_for_unit(unit),
        "candidate_rationale": _string(item.get("rationale")),
        "rag_context": unit.merged_context_text,
    }
    if plan is not None:
        metadata.update(_support_usage_metadata(item, plan, question=question, answer=answer))
    if unit.concept_id:
        metadata["concept_id"] = unit.concept_id
    if plan is not None:
        metadata["question_plan_id"] = plan_id
    return QuestionAnswerPair(
        question=question,
        answer=answer,
        question_type=question_type,
        difficulty=difficulty,
        source=source,
        concepts=concepts,
        metadata=metadata,
    )


def _support_usage_metadata(
    item: dict[str, Any],
    plan: dict[str, Any],
    *,
    question: str,
    answer: str,
) -> dict[str, Any]:
    required_roles = _string_list(plan.get("required_support_roles"))
    required_member_ids = _string_list(plan.get("support_member_ids"))
    support_snippets = _string_list(plan.get("support_snippets"))
    declared_roles = _string_list(item.get("used_support_roles") or item.get("support_roles"))
    declared_member_ids = _string_list(
        item.get("used_support_member_ids") or item.get("used_support_ids") or item.get("support_member_ids")
    )
    note = _string(item.get("support_usage_note") or item.get("support_rationale"))
    candidate_text = " ".join(
        value for value in [question, answer, _string(item.get("rationale")), note] if value
    )
    matched_snippets = _matched_support_snippets(support_snippets, candidate_text)
    detected_roles = required_roles if matched_snippets and required_roles else []
    detected_member_ids = required_member_ids if matched_snippets and len(required_member_ids) == 1 else []
    used_roles = _unique_strings([*declared_roles, *detected_roles])
    used_member_ids = _unique_strings([*declared_member_ids, *detected_member_ids])
    support_required = bool(required_roles or required_member_ids or support_snippets)
    support_used = bool(
        set(required_roles) & set(used_roles)
        or set(required_member_ids) & set(used_member_ids)
        or matched_snippets
    )
    unused_roles = [role for role in required_roles if role not in used_roles]
    if support_required and support_used:
        status = "used"
        unused_roles = []
    elif support_required:
        status = "unused_required_support"
    else:
        status = "not_required"

    return {
        "question_plan_type": _string(plan.get("type") or plan.get("question_type")),
        "required_support_roles": required_roles,
        "required_support_member_ids": required_member_ids,
        "support_snippets": support_snippets,
        "used_support_roles": used_roles,
        "used_support_member_ids": used_member_ids,
        "matched_support_snippets": matched_snippets,
        "unused_support_roles": unused_roles,
        "support_usage_status": status,
        "support_usage_note": note,
    }


def _matched_support_snippets(snippets: Sequence[str], candidate_text: str) -> list[str]:
    normalized_candidate = _normalize_for_overlap(candidate_text)
    if not normalized_candidate:
        return []
    matches: list[str] = []
    for snippet in snippets:
        normalized_snippet = _normalize_for_overlap(snippet)
        if not normalized_snippet:
            continue
        if normalized_snippet in normalized_candidate:
            matches.append(snippet)
            continue
        snippet_tokens = set(_overlap_tokens(normalized_snippet))
        if not snippet_tokens:
            continue
        candidate_tokens = set(_overlap_tokens(normalized_candidate))
        overlap = len(snippet_tokens & candidate_tokens) / max(1, len(snippet_tokens))
        if overlap >= 0.6:
            matches.append(snippet)
    return _unique_strings(matches)


def _normalize_for_overlap(text: str) -> str:
    return " ".join(str(text or "").casefold().replace("\\", " ").split())


def _overlap_tokens(text: str) -> list[str]:
    return [token.strip(".,;:!?()[]{}$") for token in text.split() if len(token.strip(".,;:!?()[]{}$")) >= 2]


def _question_plan_for_candidate(unit: RAGKnowledgeUnit, plan_id: str) -> dict[str, Any] | None:
    if not plan_id:
        return None
    for plan in unit.question_plans:
        if isinstance(plan, dict) and _string(plan.get("id")) == plan_id:
            return plan
    return None


def _source_for_unit(unit: RAGKnowledgeUnit) -> EvidenceSpan | None:
    if unit.primary_evidence is not None:
        return unit.primary_evidence
    if not unit.retrieved_contexts:
        return None
    context = unit.retrieved_contexts[0]
    return EvidenceSpan(
        source=context.source_id,
        text=context.text,
        line_start=context.line_start,
        line_end=context.line_end,
        section_title=" > ".join(context.heading_path) if context.heading_path else None,
        metadata={"block_id": context.block_id, **context.metadata},
    )


def _unique_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _string(value: object) -> str:
    return "" if value is None else str(value).strip()


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = _string(value)
    return [text] if text else []
