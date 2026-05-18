from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Mapping, Sequence
from uuid import uuid4

import httpx

_VENDOR_ROOT = Path(__file__).resolve().parents[1] / "vendor"
if str(_VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_VENDOR_ROOT))

from textbook_qa.llm_client import ChatClient  # noqa: E402
from textbook_qa.model_extractors.api_llm import ApiLlmProvider  # noqa: E402
from textbook_qa.p3_pipeline import run_p3_file_pipeline  # noqa: E402
from textbook_qa.service_api import (  # noqa: E402
    filter_cards_and_units_by_topics,
    normalize_cards_from_pairs,
    normalize_knowledge_units,
)
from textbook_qa.service_contract import GenerateCardsDocument  # noqa: E402

from .document_budget import optimize_generation_prefs
from .errors import RuntimeTaskFailure


def probe_provider(*, provider_settings: Mapping[str, str]) -> dict[str, Any]:
    provider_meta = _provider_settings(provider_settings)
    _request_openai_json(
        provider_meta,
        [
            {
                "role": "system",
                "content": "You are a connectivity probe for an OpenAI-compatible API. Return JSON only.",
            },
            {
                "role": "user",
                "content": 'Return exactly this JSON object: {"ok": true}',
            },
        ],
    )
    return {
        "ok": True,
        "provider_name": "openai_compatible_local",
        "model": provider_meta["model"],
    }


def generate_cards_from_documents(
    *,
    documents: Sequence[Mapping[str, Any]],
    deck_name: str,
    topics: Sequence[str] | None,
    generation_prefs: Mapping[str, Any] | None,
    provider_settings: Mapping[str, str],
) -> dict[str, Any]:
    provider_meta = _provider_settings(provider_settings)
    request_documents = _request_documents(documents)
    preferences = optimize_generation_prefs(
        [document.model_dump() for document in request_documents],
        generation_prefs,
    )
    job_dir = _create_job_dir()
    input_path = job_dir / _request_filename(request_documents)
    output_dir = job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    input_path.write_text(_combined_markdown(request_documents), encoding="utf-8")

    run = run_p3_file_pipeline(
        input_path,
        output_dir,
        extractor_provider=ApiLlmProvider(_api_extractor_settings(provider_meta, preferences)),
        local_client=ChatClient(
            base_url=provider_meta["base_url"],
            model=provider_meta["model"],
            api_key=provider_meta["api_key"],
            timeout=provider_meta["timeout"],
        ),
        judge_client=None,
        language=_text_pref(preferences, "language", "zh"),
        max_candidates=_int_pref(preferences, "max_candidates", 80, minimum=1),
        max_candidates_per_unit=_int_pref(preferences, "max_cards_per_unit", 5, minimum=1, maximum=10),
        max_final_questions=_int_pref(preferences, "max_final_questions", 40, minimum=1),
        prefer_aggregate_units=_bool_pref(preferences, "prefer_aggregate_units", False),
        judge_max_pairs_per_call=_int_pref(preferences, "judge_max_pairs_per_call", 12, minimum=1),
        candidate_unit_batch_size=_int_pref(preferences, "candidate_unit_batch_size", 1, minimum=1),
        candidate_unit_batch_max_chars=_optional_int_pref(preferences, "candidate_batch_max_chars"),
        candidate_unit_context_max_chars=_optional_int_pref(preferences, "candidate_context_max_chars"),
        candidate_prompt_profile="api_simple",
        candidate_filter_profile="skip_qa_guard",
        event_callback=_jsonl_event_callback(output_dir / "events.jsonl"),
    )

    knowledge_units, unit_id_by_key = normalize_knowledge_units(
        run.generation_rag_units or run.rag_units,
        source_documents=request_documents,
    )
    cards = normalize_cards_from_pairs(
        run.result.qa_pairs,
        unit_id_by_key=unit_id_by_key,
        knowledge_units=knowledge_units,
        allowed_card_types=_allowed_card_types(preferences),
    )
    unfiltered_cards = list(cards)
    unfiltered_knowledge_units = list(knowledge_units)
    cards, knowledge_units = filter_cards_and_units_by_topics(cards, knowledge_units, topics=topics)

    warnings = list(getattr(run.result.artifacts, "warnings", []) or [])
    if topics and unfiltered_cards and not cards:
        cards = unfiltered_cards
        knowledge_units = unfiltered_knowledge_units
        warnings.append("topic filter matched no generated cards; kept the full generated result")
    if run.result.qa_pairs and not cards and _allowed_card_types(preferences) is not None:
        warnings.append("all generated cards were filtered out by the requested card_types")
    if topics and unfiltered_knowledge_units and not cards:
        warnings.append("no generated cards matched the requested topics")

    return {
        "deck": {"name": deck_name},
        "cards": cards,
        "knowledge_units": knowledge_units,
        "warnings": warnings,
        "provider_meta": {
            "mode": "api",
            "provider_name": "openai_compatible_local",
            "model": provider_meta["model"],
            "trace_id": job_dir.name,
            "job_dir": str(job_dir),
            "adaptive_batching": preferences.get("adaptive_batching"),
            "runtime_metrics": run.runtime_metrics,
        },
    }


def score_explanation(
    *,
    target_card: Mapping[str, Any],
    target_unit: Mapping[str, Any] | None,
    learner_explanation: str,
    rubric_version: str,
    provider_settings: Mapping[str, str],
) -> dict[str, Any]:
    provider_meta = _provider_settings(provider_settings)
    trace_id = f"eval-{uuid4().hex[:12]}"
    started_at = time.perf_counter()
    raw_result = _request_openai_json(
        provider_meta,
        _evaluation_messages(
            target_card=target_card,
            target_unit=target_unit,
            learner_explanation=learner_explanation,
            rubric_version=rubric_version,
        ),
    )
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    return _normalize_evaluation_result(
        raw_result,
        rubric_version=rubric_version,
        provider_meta={
            "trace_id": trace_id,
            "provider_name": "openai_compatible",
            "model": provider_meta["model"],
            "latency_ms": latency_ms,
            "context_debug": _evaluation_context_debug(target_unit),
        },
        context_missing=target_unit is None,
    )


def _evaluation_messages(
    *,
    target_card: Mapping[str, Any],
    target_unit: Mapping[str, Any] | None,
    learner_explanation: str,
    rubric_version: str,
) -> list[dict[str, str]]:
    system_prompt = (
        "You are a strict but helpful cognitive diagnosis judge. "
        "Evaluate only against the supplied card and knowledge-unit context. "
        "The knowledge-unit context and RAG-derived context are the primary evidence; target_card.back is only a reference answer, "
        "not the sole grading key. Use retrieved contexts, linked members, and related knowledge units as supporting context when the current unit is terse. "
        "Accept semantically correct paraphrases that match the knowledge unit. "
        "Only mark misconception when the learner contradicts the context, swaps key entities, or assigns the wrong role to a formula term. "
        "Do not reward unsupported elaboration. Return JSON only."
    )
    context = {
        "rubric_version": rubric_version,
        "target_card": dict(target_card),
        "target_unit": dict(target_unit) if target_unit is not None else None,
        "learner_explanation": learner_explanation,
        "evaluation_policy": {
            "primary_evidence_order": [
                "target_unit.summary",
                "target_unit.rag_context",
                "target_unit.retrieved_contexts",
                "target_unit.support_linked_members",
                "target_unit.relation_linked_members",
                "target_unit.source_span.text",
                "target_unit.raw_payload",
                "target_card.front",
            ],
            "reference_answer_role": "target_card.back is a reference answer with lower weight than the supplied knowledge-unit context.",
            "rag_context_role": "Use RAG-derived context fields on target_unit as the strongest grounding when they are present.",
            "related_context_role": "Use target_unit.related_units as supporting evidence for adjacent definitions, formulas, assumptions, and source-span context; do not override the current target_unit with unrelated material.",
            "semantic_grading": "Credit learner explanations that preserve the meaning of the knowledge unit even when wording differs from target_card.back.",
            "misconception_threshold": "Only mark misconception_detected=true for clear conceptual contradictions, wrong entity-role assignment, or formula-term confusion.",
        },
        "required_output": {
            "mastery_score": "0-100 aggregate mastery estimate",
            "accuracy_score": "0-100 correctness of concept/entities/definitions",
            "mechanism_score": "0-100 causal, algorithmic, mathematical, or operational explanation",
            "boundary_score": "0-100 prerequisites, assumptions, failure modes, limits",
            "misconception_score": "0-100 severity where higher means more severe misconception risk",
            "misconception_detected": "boolean",
            "confidence_score": "0-100 confidence in this diagnosis based on supplied evidence",
            "uncertain": "boolean, true when evidence is insufficient or the diagnosis is borderline",
            "feedback": "short helpful feedback",
            "weak_points": ["dimension names that need work"],
            "reinforcement_advice": ["specific next review actions"],
        },
    }
    if target_unit is None:
        context["warning"] = "knowledge_unit_context_missing"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]


def _evaluation_context_debug(target_unit: Mapping[str, Any] | None) -> dict[str, Any]:
    if target_unit is None:
        return {
            "target_unit_provider_id": None,
            "related_evidence_count": 0,
            "related_provider_unit_ids": [],
            "rag_context_present": False,
            "retrieved_context_count": 0,
            "support_linked_member_count": 0,
            "relation_linked_member_count": 0,
        }
    related_units = target_unit.get("related_units")
    if not isinstance(related_units, list):
        related_units = []
    related_ids = [
        str(unit.get("provider_unit_id"))
        for unit in related_units
        if isinstance(unit, Mapping) and unit.get("provider_unit_id")
    ]
    return {
        "target_unit_provider_id": target_unit.get("provider_unit_id"),
        "target_unit_topic": target_unit.get("topic"),
        "related_evidence_count": len(related_units),
        "related_provider_unit_ids": related_ids,
        "rag_context_present": bool(target_unit.get("rag_context")),
        "retrieved_context_count": _list_count(target_unit.get("retrieved_contexts")),
        "support_linked_member_count": _list_count(target_unit.get("support_linked_members")),
        "relation_linked_member_count": _list_count(target_unit.get("relation_linked_members")),
    }


def _list_count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


def _normalize_evaluation_result(
    payload: Mapping[str, Any],
    *,
    rubric_version: str,
    provider_meta: Mapping[str, Any],
    context_missing: bool,
) -> dict[str, Any]:
    try:
        accuracy_score = _score_value(payload, "accuracy_score")
        confidence_score = _score_value(
            payload,
            "confidence_score",
            default=55.0 if context_missing else 75.0,
        )
        result = {
            "mastery_score": _score_value(payload, "mastery_score"),
            "accuracy_score": accuracy_score,
            "concept_score": _score_value(payload, "concept_score", default=accuracy_score),
            "mechanism_score": _score_value(payload, "mechanism_score"),
            "boundary_score": _score_value(payload, "boundary_score"),
            "misconception_score": _score_value(payload, "misconception_score"),
            "misconception_detected": bool(payload.get("misconception_detected")),
            "confidence_score": confidence_score,
            "uncertain": _bool_value(payload.get("uncertain"), default=confidence_score < 60.0 or context_missing),
            "feedback": _required_text(payload, "feedback"),
            "weak_points": _text_list(payload.get("weak_points")),
            "reinforcement_advice": _text_list(payload.get("reinforcement_advice")),
            "rubric_version": str(payload.get("rubric_version") or rubric_version),
            "provider_meta": dict(provider_meta),
        }
    except (TypeError, ValueError) as exc:
        raise RuntimeTaskFailure(code="evaluation_parse_failed", message=str(exc)) from exc
    if context_missing:
        result["warnings"] = ["knowledge_unit_context_missing"]
    return result


def _score_value(payload: Mapping[str, Any], key: str, *, default: float | None = None) -> float:
    raw_value = payload.get(key, default)
    if raw_value is None:
        raise ValueError(f"Provider evaluation response missing {key}")
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Provider evaluation response field {key} must be numeric") from exc
    return max(0.0, min(100.0, value))


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Provider evaluation response missing {key}")
    return text


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _bool_value(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _provider_settings(provider_settings: Mapping[str, str]) -> dict[str, Any]:
    base_url = str(provider_settings.get("base_url") or "").strip().rstrip("/")
    api_key = str(provider_settings.get("api_key") or "").strip()
    model = str(provider_settings.get("model") or "").strip()
    if not base_url or not api_key or not model:
        raise ValueError("provider_settings must include base_url, api_key, and model")
    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "timeout": _float_value(provider_settings.get("timeout"), default=300.0),
    }


def _api_extractor_settings(provider_meta: Mapping[str, Any], preferences: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "base_url": provider_meta["base_url"],
        "model": provider_meta["model"],
        "api_key": provider_meta["api_key"],
        "timeout": provider_meta["timeout"],
        "max_blocks": _optional_int_pref(preferences, "extractor_max_blocks"),
        "max_chars": _optional_int_pref(preferences, "extractor_max_chars"),
        "max_tokens": _optional_int_pref(preferences, "extractor_max_tokens"),
        "batch_mode": _text_pref(preferences, "extractor_batch_mode", "block"),
        "batch_max_chars": _optional_int_pref(preferences, "extractor_batch_max_chars"),
        "preselect_enabled": not _bool_pref(preferences, "disable_extractor_preselect", False),
        "preselect_max_blocks": _optional_int_pref(preferences, "extractor_preselect_max_blocks"),
        "preselect_min_score": _optional_float_pref(preferences, "extractor_preselect_min_score"),
        "adaptive_max_blocks_enabled": not _bool_pref(preferences, "disable_extractor_adaptive_max_blocks", False),
        "adaptive_min_blocks": _int_pref(preferences, "extractor_adaptive_min_blocks", 12, minimum=1),
        "adaptive_max_blocks": _int_pref(preferences, "extractor_adaptive_max_blocks_limit", 20, minimum=1),
    }


def _request_documents(documents: Sequence[Mapping[str, Any]]) -> list[GenerateCardsDocument]:
    return [
        GenerateCardsDocument(
            filename=_sanitize_request_filename(str(document.get("filename") or f"document-{index}.md")),
            content_type=str(document.get("content_type") or "text/plain"),
            text=str(document.get("text") or ""),
        )
        for index, document in enumerate(documents, start=1)
    ]


def _request_filename(documents: Sequence[GenerateCardsDocument]) -> str:
    if len(documents) == 1:
        return _sanitize_request_filename(documents[0].filename or "document.md")
    return "service-request.md"


def _sanitize_request_filename(filename: str) -> str:
    collapsed = filename.replace("\\", "/").split("/")[-1].strip()
    if not collapsed or collapsed in {".", ".."}:
        return "document.md"

    safe_chars: list[str] = []
    for char in collapsed:
        if char.isalnum() or char in {".", "_", "-"}:
            safe_chars.append(char)
        else:
            safe_chars.append("_")

    sanitized = "".join(safe_chars).strip("._")
    if not sanitized:
        return "document.md"
    if "." not in sanitized:
        sanitized = f"{sanitized}.md"
    return sanitized


def _combined_markdown(documents: Sequence[GenerateCardsDocument]) -> str:
    parts: list[str] = []
    for index, document in enumerate(documents, start=1):
        title = Path(document.filename or f"document-{index}.md").stem.strip() or f"Document {index}"
        parts.append(f"# {title}")
        parts.append("")
        parts.append(document.text.strip())
        parts.append("")
    combined = "\n".join(parts).strip()
    if not combined:
        raise ValueError("documents must include at least one non-empty text payload")
    return combined + "\n"


def _allowed_card_types(preferences: Mapping[str, Any]) -> set[str] | None:
    raw_value = preferences.get("card_types")
    if not isinstance(raw_value, list):
        return None
    allowed = {str(item).strip() for item in raw_value if str(item).strip()}
    return allowed or None


def _create_job_dir() -> Path:
    root = _job_root()
    root.mkdir(parents=True, exist_ok=True)
    job_dir = root / f"rag-{uuid4().hex[:12]}"
    job_dir.mkdir(parents=True, exist_ok=False)
    return job_dir


def _job_root() -> Path:
    configured = os.environ.get("LMCA_RAG_JOB_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    config_path = os.environ.get("LMCA_PLUGIN_CONFIG_PATH", "").strip()
    if config_path:
        return Path(config_path).expanduser().resolve().parent / "jobs"
    return Path(os.environ.get("TEMP", ".")).expanduser().resolve() / "rag-core-jobs"


def _jsonl_event_callback(path: Path):
    def emit(event: str, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"event": event, **payload}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    return emit


def _text_pref(preferences: Mapping[str, Any], key: str, default: str) -> str:
    value = preferences.get(key)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _bool_pref(preferences: Mapping[str, Any], key: str, default: bool) -> bool:
    value = preferences.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int_pref(preferences: Mapping[str, Any], key: str, default: int, *, minimum: int, maximum: int | None = None) -> int:
    value = _optional_int_pref(preferences, key)
    if value is None:
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _optional_int_pref(preferences: Mapping[str, Any], key: str) -> int | None:
    value = preferences.get(key)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float_pref(preferences: Mapping[str, Any], key: str) -> float | None:
    value = preferences.get(key)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_value(value: object, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _request_openai_json(provider_meta: Mapping[str, Any], messages: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    response = httpx.post(
        _chat_completions_url(str(provider_meta["base_url"])),
        headers={
            "Authorization": f"Bearer {provider_meta['api_key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": provider_meta["model"],
            "messages": list(messages),
            "temperature": 0.0,
        },
        timeout=float(provider_meta.get("timeout") or 300.0),
    )
    response.raise_for_status()
    payload = response.json()
    content = _message_content(payload)
    return _coerce_json_object(content)


def _chat_completions_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def _message_content(payload: Mapping[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("OpenAI-compatible response did not include choices")
    first = choices[0] if isinstance(choices[0], Mapping) else {}
    message = first.get("message") if isinstance(first, Mapping) else {}
    content = message.get("content") if isinstance(message, Mapping) else ""
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, Mapping):
                text = item.get("text")
                if text is not None:
                    text_parts.append(str(text))
        return "".join(text_parts)
    return str(content or "")


def _coerce_json_object(content: str) -> dict[str, Any]:
    normalized = _strip_code_fences(content).strip()
    if not normalized:
        raise ValueError("Provider returned an empty response body")
    try:
        loaded = json.loads(normalized)
    except ValueError as exc:
        raise ValueError("Provider response was not valid JSON") from exc
    if not isinstance(loaded, dict):
        raise ValueError("Provider response JSON must be an object")
    return loaded


def _strip_code_fences(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped
