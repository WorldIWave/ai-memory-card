# Input: structured knowledge points and retrieved local RAG contexts.
# Output: assembled RAG knowledge units with primary evidence and merged context text.
# Role: normalize retrieval output into one prompt-ready unit per structured point.
# Note: assembly is CPU-only and has no model-loading side effects.

from __future__ import annotations

from collections.abc import Iterable, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from textbook_qa.local_rag.concept_units import concept_key
from textbook_qa.local_rag.retrieval import RetrievedContext
from textbook_qa.schemas import EvidenceSpan
from textbook_qa.structured_kp import KnowledgePointType, StructuredKnowledgePoint, VariableDefinition


@dataclass
class RAGKnowledgeUnit:
    id: str
    title: str
    type: KnowledgePointType
    seed_point: StructuredKnowledgePoint
    primary_evidence: EvidenceSpan | None
    retrieved_contexts: list[RetrievedContext]
    merged_context_text: str
    formulas: list[str]
    variables: list[VariableDefinition]
    conditions: list[str]
    results: list[str]
    misconceptions: list[str]
    examples: list[str] = field(default_factory=list)
    concept_id: str = ""
    question_plans: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def assemble_rag_unit(point: StructuredKnowledgePoint, contexts: Sequence[RetrievedContext]) -> RAGKnowledgeUnit:
    """Assemble one structured point and its retrieved contexts into a RAG unit."""

    copied_contexts = deepcopy(list(contexts))
    metadata = deepcopy(point.metadata)
    metadata["source_block_ids"] = list(point.source_block_ids)
    concept_id = _concept_id(point)
    question_plans = _question_plans(point, concept_id)
    examples = _examples(point)
    merged_context_text, grounding_context_metadata = _grounding_context_text(point, copied_contexts, examples)
    metadata["concept_id"] = concept_id
    metadata["question_plan_count"] = len(question_plans)
    metadata["grounding_context"] = grounding_context_metadata

    return RAGKnowledgeUnit(
        id="rag_" + point.id,
        title=point.title,
        type=point.type,
        seed_point=deepcopy(point),
        primary_evidence=_primary_evidence(point, copied_contexts),
        retrieved_contexts=copied_contexts,
        merged_context_text=merged_context_text,
        formulas=[point.formula] if point.formula.strip() else [],
        variables=deepcopy(point.variables),
        conditions=list(point.conditions),
        results=[point.statement] if point.statement.strip() else [],
        misconceptions=list(point.common_mistakes),
        examples=examples,
        concept_id=concept_id,
        question_plans=question_plans,
        metadata=metadata,
    )


def _concept_id(point: StructuredKnowledgePoint) -> str:
    concept_unit = point.metadata.get("concept_unit")
    if isinstance(concept_unit, dict):
        key = concept_unit.get("concept_key")
        if isinstance(key, str) and key.strip():
            return key.strip()

    metadata_concept_id = point.metadata.get("concept_id")
    if isinstance(metadata_concept_id, str) and metadata_concept_id.strip():
        return metadata_concept_id.strip()

    return concept_key(point.title)


def _examples(point: StructuredKnowledgePoint) -> list[str]:
    concept_unit = point.metadata.get("concept_unit")
    if not isinstance(concept_unit, dict):
        return []
    examples = concept_unit.get("examples")
    if not isinstance(examples, list):
        return []
    return _unique(str(example).strip() for example in examples if str(example).strip())


def _support_member_ids(point: StructuredKnowledgePoint, support_role: str) -> list[str]:
    concept_unit = point.metadata.get("concept_unit")
    if not isinstance(concept_unit, dict):
        return []
    raw_members = concept_unit.get("support_linked_members")
    if not isinstance(raw_members, list):
        return []

    member_ids: list[str] = []
    for item in raw_members:
        if not isinstance(item, dict):
            continue
        role = str(item.get("support_role", "") or "").strip().casefold()
        if role != support_role:
            continue
        member_id = str(item.get("member_id", "") or "").strip()
        if member_id:
            member_ids.append(member_id)
    return _unique(member_ids)


def _question_plans(point: StructuredKnowledgePoint, concept_id: str) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    title = point.title.strip()
    statement = point.statement.strip()
    formula = point.formula.strip()
    conditions = [condition.strip() for condition in point.conditions if condition and condition.strip()]
    variable_symbols = [variable.symbol.strip() for variable in point.variables if variable.symbol.strip()]
    relation_evidence = [relation.evidence_text.strip() for relation in point.relations if relation.evidence_text.strip()]
    examples = _examples(point)

    if title and statement:
        _append_question_plan(plans, concept_id, "definition", [title, statement])
    if formula:
        _append_question_plan(plans, concept_id, "formula", [title, formula, *variable_symbols])
    if _supports_application(point, formula, conditions, examples):
        _append_question_plan(
            plans,
            concept_id,
            "application",
            [title, formula, statement, *conditions, *variable_symbols, *examples],
            required_support_roles=["example"] if examples else [],
            support_member_ids=_support_member_ids(point, "example"),
            support_snippets=examples,
        )
    if point.common_mistakes:
        _append_question_plan(
            plans,
            concept_id,
            "misconception",
            [title, *point.common_mistakes],
            required_support_roles=["misconception"],
            support_member_ids=_support_member_ids(point, "misconception"),
            support_snippets=point.common_mistakes,
        )
    if _supports_reasoning(point, formula, conditions, variable_symbols, relation_evidence):
        _append_question_plan(plans, concept_id, "reasoning", [title, statement, formula, *conditions, *relation_evidence])
    if _supports_deep_question(point, formula, conditions, variable_symbols, relation_evidence):
        _append_question_plan(plans, concept_id, "deep", [title, statement, formula, *conditions, *variable_symbols, *relation_evidence])

    return plans


def _supports_application(
    point: StructuredKnowledgePoint,
    formula: str,
    conditions: Sequence[str],
    examples: Sequence[str],
) -> bool:
    if point.type in {KnowledgePointType.APPLICATION, KnowledgePointType.PROCEDURE}:
        return bool(point.title.strip() and (point.statement.strip() or conditions or formula or examples))
    return bool(point.title.strip() and (examples or (formula and (conditions or point.variables))))


def _supports_reasoning(
    point: StructuredKnowledgePoint,
    formula: str,
    conditions: Sequence[str],
    variable_symbols: Sequence[str],
    relation_evidence: Sequence[str],
) -> bool:
    if point.type in {KnowledgePointType.PROCEDURE, KnowledgePointType.DEEP_REASONING}:
        return bool(point.title.strip() and (point.statement.strip() or conditions or relation_evidence))
    return bool(point.title.strip() and point.statement.strip() and (formula or conditions or variable_symbols or relation_evidence))


def _supports_deep_question(
    point: StructuredKnowledgePoint,
    formula: str,
    conditions: Sequence[str],
    variable_symbols: Sequence[str],
    relation_evidence: Sequence[str],
) -> bool:
    if not point.title.strip():
        return False
    support_count = sum(
        1
        for supported in (
            bool(formula),
            bool(conditions),
            bool(variable_symbols),
            bool(point.common_mistakes),
            bool(relation_evidence),
            point.type == KnowledgePointType.DEEP_REASONING,
        )
        if supported
    )
    return bool(point.statement.strip()) and support_count >= 2


def _append_question_plan(
    plans: list[dict[str, Any]],
    concept_id: str,
    plan_type: str,
    must_include: Sequence[str],
    *,
    required_support_roles: Sequence[str] = (),
    support_member_ids: Sequence[str] = (),
    support_snippets: Sequence[str] = (),
) -> None:
    plan = _question_plan(
        concept_id,
        plan_type,
        must_include,
        required_support_roles=required_support_roles,
        support_member_ids=support_member_ids,
        support_snippets=support_snippets,
    )
    if plan is not None:
        plans.append(plan)


def _question_plan(
    concept_id: str,
    plan_type: str,
    must_include: Sequence[str],
    *,
    required_support_roles: Sequence[str] = (),
    support_member_ids: Sequence[str] = (),
    support_snippets: Sequence[str] = (),
) -> dict[str, Any] | None:
    cleaned_must_include = _unique(value.strip() for value in must_include if value and value.strip())
    if not cleaned_must_include:
        return None

    plan = {
        "id": f"{concept_id}:{plan_type}",
        "type": plan_type,
        "concept_id": concept_id,
        "must_include": cleaned_must_include,
    }
    cleaned_roles = _unique(value.strip() for value in required_support_roles if value and value.strip())
    cleaned_member_ids = _unique(value.strip() for value in support_member_ids if value and value.strip())
    cleaned_snippets = _unique(value.strip() for value in support_snippets if value and value.strip())
    if cleaned_roles:
        plan["required_support_roles"] = cleaned_roles
    if cleaned_member_ids:
        plan["support_member_ids"] = cleaned_member_ids
    if cleaned_snippets:
        plan["support_snippets"] = cleaned_snippets
    return plan


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _primary_evidence(point: StructuredKnowledgePoint, contexts: Sequence[RetrievedContext]) -> EvidenceSpan | None:
    if point.evidence:
        return deepcopy(point.evidence[0])
    if not contexts:
        return None

    first_context = contexts[0]
    metadata = deepcopy(first_context.metadata)
    metadata["block_id"] = first_context.block_id
    metadata["source_id"] = first_context.source_id
    return EvidenceSpan(
        source=first_context.source_id,
        text=first_context.text,
        line_start=first_context.line_start,
        line_end=first_context.line_end,
        section_title=_section_title(first_context),
        metadata=metadata,
    )


def _section_title(context: RetrievedContext) -> str | None:
    heading_parts = [part.strip() for part in context.heading_path if part.strip()]
    if not heading_parts:
        return None
    return " > ".join(heading_parts)


def _grounding_context_text(
    point: StructuredKnowledgePoint,
    contexts: Sequence[RetrievedContext],
    examples: Sequence[str],
) -> tuple[str, dict[str, Any]]:
    lines: list[str] = []
    seen_values: set[str] = set()
    counts = {
        "structured_item_count": 0,
        "source_evidence_count": 0,
        "retrieved_context_count": 0,
    }

    def add(label: str, value: str, *, kind: str) -> None:
        text = value.strip()
        if not text:
            return
        dedupe_key = f"{label}:{text}"
        if dedupe_key in seen_values:
            return
        seen_values.add(dedupe_key)
        lines.append(f"{label}: {text}")
        counts[kind] += 1

    add("Concept", point.title, kind="structured_item_count")
    add("Statement", point.statement, kind="structured_item_count")
    add("Formula", point.formula, kind="structured_item_count")
    for variable in point.variables:
        label, value = _variable_context_parts(variable)
        add(label, value, kind="structured_item_count")
    for condition in point.conditions:
        add("Condition", condition, kind="structured_item_count")
    for example in examples:
        add("Example", example, kind="structured_item_count")
    for mistake in point.common_mistakes:
        add("Common mistake", mistake, kind="structured_item_count")
    for relation in point.relations:
        evidence_text = str(getattr(relation, "evidence_text", "") or "").strip()
        if evidence_text:
            label = f"Relation {getattr(relation, 'type', '')}".strip()
            add(label, evidence_text, kind="structured_item_count")
    for evidence in point.evidence:
        add("Source evidence", evidence.text, kind="source_evidence_count")
    for context in contexts:
        add("Retrieved context", context.text, kind="retrieved_context_count")

    return "\n".join(lines), counts


def _variable_context_parts(variable: VariableDefinition) -> tuple[str, str]:
    symbol = variable.symbol.strip()
    meaning = variable.meaning.strip()
    label = f"Variable {symbol}" if symbol else "Variable"
    value = meaning or symbol
    if variable.condition.strip():
        value = f"{value}; condition: {variable.condition.strip()}" if value else f"condition: {variable.condition.strip()}"
    return label, value
