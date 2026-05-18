# Input: document blocks plus local OpenAI-compatible LLM endpoint configuration.
# Output: provider-neutral extraction candidates from model-emitted atomic facts.
# Role: make P3 local LLM knowledge-unit extraction pluggable without changing pipelines.
# Note: tests subclass _call_model, so importing this file never loads model dependencies.

from __future__ import annotations

import copy
import json
import operator
from collections.abc import Sequence
from typing import Any, Callable

from textbook_qa.block_selection import adaptive_block_budget, preselect_blocks
from textbook_qa.llm_client import ChatClient, ChatClientRequestError, ChatMessage
from textbook_qa.llm_json import parse_llm_json_payload
from textbook_qa.model_extractors.base import (
    ExtractionCandidate,
    ExtractionProviderRequestError,
    ExtractionProviderResult,
    ExtractorAvailability,
)
from textbook_qa.structured_kp import BlockType, DocumentBlock

_IGNORED_BLOCK_TYPES = {BlockType.METADATA, BlockType.IMAGE_REF, BlockType.HEADING}
_DEFAULT_MAX_CHARS = 1600
_DEFAULT_MAX_BLOCKS = 40
_DEFAULT_TIMEOUT = 120.0
_DEFAULT_MAX_TOKENS = 1200
_DEFAULT_TEMPERATURE = 0.0
_DEFAULT_BATCH_MODE = "block"
_DEFAULT_BATCH_MAX_CHARS = 6000
_DEFAULT_PRESELECT_ENABLED = True
_DEFAULT_PRESELECT_MAX_BLOCKS = 180
_DEFAULT_PRESELECT_MIN_SCORE = 1.0
_DEFAULT_REQUEST_MAX_RETRIES = 2
_DEFAULT_REQUEST_RETRY_BACKOFF_SECONDS = 1.0
_DEFAULT_ADAPTIVE_MAX_BLOCKS_ENABLED = False
_DEFAULT_ADAPTIVE_MIN_BLOCKS = 12
_DEFAULT_ADAPTIVE_MAX_BLOCKS = 20
_FACT_KEYS = ("facts", "atomic_facts", "knowledge_units", "items")
_ALLOWED_LABELS = {
    "definition",
    "concept",
    "term",
    "formula",
    "notation",
    "symbol",
    "variable",
    "procedure",
    "application",
    "worked_example",
    "example",
    "misconception",
    "mistake",
    "deep_reasoning",
}
_NON_INSTRUCTIONAL_CONTENT_ROLES = {
    "course_logistics",
    "metadata",
    "navigation",
    "tooling_instruction",
    "administrative",
    "assignment_submission",
    "account_setup",
    "source_note",
    "non_instructional",
    "download_instruction",
}
_CONTENT_ROLE_GUIDANCE = (
    "Classify each source block before extracting. Use content_role core_knowledge, definition, formula, "
    "worked_example, misconception, deep_reasoning, or procedure only when the text teaches a reusable concept. "
    "If a block is non-instructional course logistics, metadata, navigation, tooling_instruction, account_setup, "
    "assignment_submission, source_note, or download_instruction, emit at most one audit fact with that "
    "non-instructional content_role and evidence_text; normalization will reject and count it."
)
_FRAGMENT_GUIDANCE = (
    "If a concept is only a modifier or prefix of a longer source term, use the longer source term as concept; "
    "do not emit fragments such as adjectives, function words, bare numerators/denominators, or orphan variables "
    "unless the source explicitly defines that exact term."
)


class LocalLlmProvider:
    name = "local_llm"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = dict(config or {})
        self._base_url = str(self._config.get("base_url") or "").rstrip("/")
        self._model = str(self._config.get("model") or "").strip()
        self._selection_metadata: dict[str, Any] = {}
        self._event_callback: Callable[[str, dict[str, Any]], None] | None = None
        self._progress_callback: Callable[[str], None] | None = None

    def availability(self) -> ExtractorAvailability:
        missing = [key for key, value in (("base_url", self._base_url), ("model", self._model)) if not value]
        if missing:
            return ExtractorAvailability(
                provider=self.name,
                available=False,
                reason="missing required local_llm config: " + ", ".join(missing),
            )
        return ExtractorAvailability(
            provider=self.name,
            available=True,
            reason="configured OpenAI-compatible endpoint",
            metadata={"base_url": self._base_url, "model": self._model},
        )

    def set_runtime_callbacks(
        self,
        *,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._event_callback = event_callback
        self._progress_callback = progress_callback

    def _emit_runtime_event(self, event: str, **payload: Any) -> None:
        if self._event_callback is not None:
            self._event_callback(event, payload)

    def _emit_runtime_progress(self, label: str) -> None:
        if self._progress_callback is not None:
            self._progress_callback(label)

    def extract(self, blocks: Sequence[DocumentBlock]) -> ExtractionProviderResult:
        availability = self.availability()
        if not availability.available:
            return ExtractionProviderResult(
                provider=self.name,
                warnings=[availability.reason],
                metadata={"processed_blocks": 0, "processed_batches": 0},
            )

        candidates: list[ExtractionCandidate] = []
        warnings: list[str] = []
        eligible_blocks = self._eligible_blocks(blocks)
        batches = _batches_for_mode(eligible_blocks, mode=self._batch_mode(), batch_max_chars=self._batch_max_chars())
        total_batches = len(batches)
        model_calls = 0
        salvaged_batches = 0

        self._emit_runtime_event(
            "extract_batches_planned",
            eligible_block_count=len(eligible_blocks),
            batch_count=total_batches,
            batch_mode=self._batch_mode(),
            batch_max_chars=self._batch_max_chars(),
            selection_metadata=dict(self._selection_metadata),
        )

        def extract_batch(
            batch: Sequence[DocumentBlock],
            *,
            batch_index: int,
            total_batches: int,
            salvage_depth: int = 0,
        ) -> list[ExtractionCandidate]:
            nonlocal model_calls, salvaged_batches
            model_calls += 1
            batch_id = "+".join(block.id for block in batch[:3])
            batch_label = f"extract batch {batch_index}/{total_batches}"
            if salvage_depth:
                batch_label += f" retry {salvage_depth}"
            self._emit_runtime_progress(batch_label)
            self._emit_runtime_event(
                "extract_batch_start",
                batch_index=batch_index,
                total_batches=total_batches,
                salvage_depth=salvage_depth,
                block_ids=[block.id for block in batch],
                block_count=len(batch),
                model_call_index=model_calls,
                batch_id=batch_id,
            )
            prompt = _prompt_for_batch(batch, max_chars=self._max_chars(), batch_max_chars=self._batch_max_chars())
            try:
                payload = parse_llm_json_payload(self._call_model(prompt))
            except ExtractionProviderRequestError as exc:
                warning = f"request_failed:{batch_id}:{exc.__class__.__name__}:{exc}"
                warnings.append(warning)
                self._emit_runtime_event(
                    "extract_batch_request_failed",
                    batch_index=batch_index,
                    total_batches=total_batches,
                    salvage_depth=salvage_depth,
                    block_ids=[block.id for block in batch],
                    block_count=len(batch),
                    model_call_index=model_calls,
                    batch_id=batch_id,
                    warning=warning,
                    retryable=exc.retryable,
                )
                raise
            except Exception as exc:
                warning = f"parse_failed:{batch_id}:{exc.__class__.__name__}:{exc}"
                warnings.append(warning)
                self._emit_runtime_event(
                    "extract_batch_parse_failed",
                    batch_index=batch_index,
                    total_batches=total_batches,
                    salvage_depth=salvage_depth,
                    block_ids=[block.id for block in batch],
                    block_count=len(batch),
                    model_call_index=model_calls,
                    batch_id=batch_id,
                    warning=warning,
                )
                if len(batch) <= 1:
                    return []
                salvaged_batches += 1
                midpoint = max(1, len(batch) // 2)
                self._emit_runtime_event(
                    "extract_batch_salvage_split",
                    batch_index=batch_index,
                    total_batches=total_batches,
                    salvage_depth=salvage_depth,
                    block_ids=[block.id for block in batch],
                    left_block_ids=[block.id for block in batch[:midpoint]],
                    right_block_ids=[block.id for block in batch[midpoint:]],
                    batch_id=batch_id,
                )
                return extract_batch(
                    batch[:midpoint],
                    batch_index=batch_index,
                    total_batches=total_batches,
                    salvage_depth=salvage_depth + 1,
                ) + extract_batch(
                    batch[midpoint:],
                    batch_index=batch_index,
                    total_batches=total_batches,
                    salvage_depth=salvage_depth + 1,
                )
            candidates = _candidates_from_batch_payload(self.name, batch, payload)
            self._emit_runtime_event(
                "extract_batch_end",
                batch_index=batch_index,
                total_batches=total_batches,
                salvage_depth=salvage_depth,
                block_ids=[block.id for block in batch],
                block_count=len(batch),
                model_call_index=model_calls,
                batch_id=batch_id,
                candidate_count=len(candidates),
            )
            return candidates

        for batch_index, batch in enumerate(batches, start=1):
            candidates.extend(extract_batch(batch, batch_index=batch_index, total_batches=total_batches))

        self._emit_runtime_event(
            "extract_batches_completed",
            eligible_block_count=len(eligible_blocks),
            batch_count=total_batches,
            model_calls=model_calls,
            salvaged_batches=salvaged_batches,
            candidate_count=len(candidates),
        )

        return ExtractionProviderResult(
            provider=self.name,
            candidates=candidates,
            warnings=warnings,
            metadata={
                "processed_blocks": len(eligible_blocks),
                "processed_batches": len(batches),
                "model_calls": model_calls,
                "salvaged_batches": salvaged_batches,
                **self._selection_metadata,
            },
        )

    def _call_model(self, prompt: str) -> str:
        client = ChatClient(
            base_url=self._base_url,
            model=self._model,
            api_key=str(self._config.get("api_key") or "").strip(),
            timeout=self._timeout(),
            max_retries=self._request_max_retries(),
            retry_backoff_seconds=self._request_retry_backoff_seconds(),
        )
        try:
            return client.complete(
                [
                    ChatMessage(role="system", content="Extract textbook atomic facts. Return JSON only."),
                    ChatMessage(role="user", content=prompt),
                ],
                temperature=self._temperature(),
                max_tokens=self._max_tokens(),
            )
        except ChatClientRequestError as exc:
            raise ExtractionProviderRequestError(self.name, str(exc), retryable=exc.retryable) from exc

    def _completion_url(self) -> str:
        if self._base_url.endswith("/chat/completions"):
            return self._base_url
        return self._base_url + "/chat/completions"

    def _timeout(self) -> float:
        return _coerce_float(self._config.get("timeout"), _DEFAULT_TIMEOUT)

    def _temperature(self) -> float:
        return _coerce_float(self._config.get("temperature"), _DEFAULT_TEMPERATURE)

    def _max_tokens(self) -> int:
        return _coerce_int(self._config.get("max_tokens"), _DEFAULT_MAX_TOKENS)

    def _request_max_retries(self) -> int:
        return _coerce_int(self._config.get("request_max_retries"), _DEFAULT_REQUEST_MAX_RETRIES)

    def _request_retry_backoff_seconds(self) -> float:
        return _coerce_float(
            self._config.get("request_retry_backoff_seconds"),
            _DEFAULT_REQUEST_RETRY_BACKOFF_SECONDS,
        )

    def _max_blocks(self) -> int:
        return _coerce_int(self._config.get("max_blocks"), _DEFAULT_MAX_BLOCKS)

    def _max_chars(self) -> int:
        return _coerce_int(self._config.get("max_chars"), _DEFAULT_MAX_CHARS)

    def _adaptive_max_blocks_enabled(self) -> bool:
        value = self._config.get("adaptive_max_blocks_enabled", _DEFAULT_ADAPTIVE_MAX_BLOCKS_ENABLED)
        if isinstance(value, str):
            return value.strip().casefold() in {"1", "true", "yes", "on"}
        return bool(value)

    def _adaptive_min_blocks(self) -> int:
        return _coerce_int(self._config.get("adaptive_min_blocks"), _DEFAULT_ADAPTIVE_MIN_BLOCKS)

    def _adaptive_max_blocks(self) -> int:
        return _coerce_int(self._config.get("adaptive_max_blocks"), _DEFAULT_ADAPTIVE_MAX_BLOCKS)

    def _effective_max_blocks(self, blocks: Sequence[DocumentBlock]) -> int:
        configured = self._max_blocks()
        if not self._adaptive_max_blocks_enabled():
            return configured
        return adaptive_block_budget(
            blocks,
            min_blocks=self._adaptive_min_blocks(),
            max_blocks=min(configured, self._adaptive_max_blocks()),
        )

    def _batch_mode(self) -> str:
        mode = str(self._config.get("batch_mode") or _DEFAULT_BATCH_MODE).strip().casefold()
        return mode if mode in {"block", "section", "token-window"} else _DEFAULT_BATCH_MODE

    def _batch_max_chars(self) -> int:
        return _coerce_int(self._config.get("batch_max_chars"), _DEFAULT_BATCH_MAX_CHARS)

    def _preselect_enabled(self) -> bool:
        value = self._config.get("preselect_enabled", _DEFAULT_PRESELECT_ENABLED)
        if isinstance(value, str):
            return value.strip().casefold() not in {"0", "false", "no", "off"}
        return bool(value)

    def _preselect_max_blocks(self) -> int:
        return _coerce_int(self._config.get("preselect_max_blocks"), _DEFAULT_PRESELECT_MAX_BLOCKS)

    def _preselect_min_score(self) -> float:
        return _coerce_float(self._config.get("preselect_min_score"), _DEFAULT_PRESELECT_MIN_SCORE)

    def _eligible_blocks(self, blocks: Sequence[DocumentBlock]) -> list[DocumentBlock]:
        raw_blocks = [
            block
            for block in blocks
            if block.type not in _IGNORED_BLOCK_TYPES and block.text.strip()
        ]
        configured_max_blocks = self._max_blocks()
        effective_max_blocks = self._effective_max_blocks(raw_blocks)
        budget_metadata = {
            "configured_max_blocks": configured_max_blocks,
            "effective_max_blocks": effective_max_blocks,
            "adaptive_max_blocks_enabled": self._adaptive_max_blocks_enabled(),
        }
        if self._adaptive_max_blocks_enabled():
            budget_metadata.update(
                {
                    "adaptive_min_blocks": self._adaptive_min_blocks(),
                    "adaptive_max_blocks": min(configured_max_blocks, self._adaptive_max_blocks()),
                }
            )

        if not self._preselect_enabled():
            selected = raw_blocks[:effective_max_blocks]
            self._selection_metadata = {
                "raw_eligible_blocks": len(raw_blocks),
                "preselected_blocks": len(selected),
                "skipped_by_preselect": max(0, len(raw_blocks) - len(selected)),
                "preselect_enabled": False,
                **budget_metadata,
            }
            return selected

        selected, metadata = preselect_blocks(
            raw_blocks,
            max_blocks=effective_max_blocks,
            preselect_max_blocks=self._preselect_max_blocks(),
            min_score=self._preselect_min_score(),
        )
        metadata["preselect_enabled"] = True
        metadata.update(budget_metadata)
        self._selection_metadata = metadata
        return selected


def _batches_for_mode(blocks: Sequence[DocumentBlock], *, mode: str, batch_max_chars: int) -> list[list[DocumentBlock]]:
    if mode == "block":
        return [[block] for block in blocks]
    if mode == "section":
        return _section_batches(blocks, batch_max_chars=batch_max_chars)
    return _window_batches(blocks, batch_max_chars=batch_max_chars)


def _section_batches(blocks: Sequence[DocumentBlock], *, batch_max_chars: int) -> list[list[DocumentBlock]]:
    batches: list[list[DocumentBlock]] = []
    current: list[DocumentBlock] = []
    current_key: tuple[str, ...] | None = None
    current_chars = 0
    for block in blocks:
        key = tuple(block.heading_path)
        size = len(block.text)
        if current and (key != current_key or current_chars + size > batch_max_chars):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(block)
        current_key = key
        current_chars += size
    if current:
        batches.append(current)
    return batches


def _window_batches(blocks: Sequence[DocumentBlock], *, batch_max_chars: int) -> list[list[DocumentBlock]]:
    batches: list[list[DocumentBlock]] = []
    current: list[DocumentBlock] = []
    current_chars = 0
    for block in blocks:
        size = len(block.text)
        if current and current_chars + size > batch_max_chars:
            batches.append(current)
            current = []
            current_chars = 0
        current.append(block)
        current_chars += size
    if current:
        batches.append(current)
    return batches


def _prompt_for_batch(blocks: Sequence[DocumentBlock], *, max_chars: int, batch_max_chars: int) -> str:
    if len(blocks) == 1:
        return _prompt_for_block(blocks[0], max_chars=max_chars)
    schema = json.dumps(
        {
            "facts": [
                {
                    "block_id": "source block id",
                    "type": "definition|formula|notation|application|worked_example|example|misconception|procedure|deep_reasoning",
                    "fact_type": "definition|formula|notation|procedure|application|worked_example|example|misconception|deep_reasoning",
                    "content_role": "core_knowledge|definition|formula|worked_example|misconception|deep_reasoning|procedure",
                    "concept": "...",
                    "target_concept": "complete concept this support item belongs to, for examples or misconceptions",
                    "concept_aliases": ["..."],
                    "statement": "...",
                    "formula": "...",
                    "conditions": ["..."],
                    "common_mistakes": ["..."],
                    "evidence_text": "quote from source",
                    "pedagogical_value": 0.0,
                    "standalone": True,
                    "variables": [{"symbol": "...", "meaning": "...", "condition": "..."}],
                    "relations": [{"type": "defines|used_for|condition_of|part_of|contrasts_with|prerequisite_of", "source_concept": "...", "target_concept": "...", "evidence_text": "...", "confidence": 0.0}],
                    "confidence": 0.0,
                }
            ]
        },
        separators=(",", ":"),
    )
    parts = [
        "Return JSON only with this schema: " + schema,
        "Rules: extract only facts supported by the source; preserve source language; every fact must include the exact block_id it came from; "
        "distinguish instructional roles from non-instructional source text; every instructional fact must include fact_type, "
        "concept, statement, evidence_text, pedagogical_value, and standalone; set standalone false if the concept or statement "
        "cannot be understood without the surrounding passage; for worked_example or misconception facts, set target_concept "
        "to the complete concept being illustrated or corrected; " + _CONTENT_ROLE_GUIDANCE + " " + _FRAGMENT_GUIDANCE + " In JSON strings, escape LaTeX backslashes as double backslashes.",
        "",
        "Source blocks:",
    ]
    used_chars = 0
    for block in blocks:
        remaining = max(0, batch_max_chars - used_chars)
        if remaining <= 0:
            break
        block_text = block.text.strip()[: min(max_chars, remaining)]
        used_chars += len(block_text)
        heading = " > ".join(part for part in block.heading_path if part.strip()) or "Untitled"
        parts.extend(["", f"Block ID: {block.id}", f"Heading: {heading}", f"Lines: {block.line_start}-{block.line_end}", "Text:", block_text])
    return "\n".join(parts)


def _prompt_for_block(block: DocumentBlock, *, max_chars: int) -> str:
    heading = " > ".join(part for part in block.heading_path if part.strip()) or "Untitled"
    text = block.text.strip()[:max_chars]
    schema = json.dumps(
        {
            "facts": [
                {
                    "type": "definition|formula|notation|application|worked_example|example|misconception|procedure|deep_reasoning",
                    "fact_type": "definition|formula|notation|procedure|application|worked_example|example|misconception|deep_reasoning",
                    "content_role": "core_knowledge|definition|formula|worked_example|misconception|deep_reasoning|procedure",
                    "concept": "...",
                    "target_concept": "complete concept this support item belongs to, for examples or misconceptions",
                    "concept_aliases": ["..."],
                    "statement": "...",
                    "formula": "...",
                    "conditions": ["..."],
                    "common_mistakes": ["..."],
                    "evidence_text": "quote from source",
                    "pedagogical_value": 0.0,
                    "standalone": True,
                    "variables": [{"symbol": "...", "meaning": "...", "condition": "..."}],
                    "relations": [{"type": "defines|used_for|condition_of|part_of|contrasts_with|prerequisite_of", "source_concept": "...", "target_concept": "...", "evidence_text": "...", "confidence": 0.0}],
                    "confidence": 0.0,
                }
            ]
        },
        separators=(",", ":"),
    )
    return "\n".join(
        [
            "Return JSON only with this schema: " + schema,
            "Rules: extract only facts supported by the source; preserve the source language; prefer complete concepts over isolated words; "
            "distinguish instructional roles from non-instructional source text; every instructional fact must include fact_type, "
            "concept, statement, evidence_text, pedagogical_value, and standalone; set standalone false if the concept or statement "
            "cannot be understood without the surrounding passage; for worked_example or misconception facts, set target_concept "
            "to the complete concept being illustrated or corrected; " + _CONTENT_ROLE_GUIDANCE + " " + _FRAGMENT_GUIDANCE + " In JSON strings, escape LaTeX backslashes as double backslashes.",
            "",
            f"Heading: {heading}",
            f"Lines: {block.line_start}-{block.line_end}",
            "Text:",
            text,
        ]
    )



def _candidates_from_batch_payload(provider: str, blocks: Sequence[DocumentBlock], payload: Any) -> list[ExtractionCandidate]:
    block_by_id = {block.id: block for block in blocks}
    fallback = blocks[0]
    candidates: list[ExtractionCandidate] = []
    for fact in _iter_fact_dicts(payload):
        block_id = _string_value(fact.get("block_id") or fact.get("source_block_id"))
        block = block_by_id.get(block_id, fallback)
        candidate = _candidate_from_fact(provider, block, fact)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _candidates_from_payload(provider: str, block: DocumentBlock, payload: Any) -> list[ExtractionCandidate]:
    candidates: list[ExtractionCandidate] = []
    for fact in _iter_fact_dicts(payload):
        candidate = _candidate_from_fact(provider, block, fact)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _iter_fact_dicts(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        facts: list[dict[str, Any]] = []
        for item in payload:
            facts.extend(_iter_fact_dicts(item))
        return facts
    if not isinstance(payload, dict):
        return []
    for key in _FACT_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            facts = []
            for item in value:
                facts.extend(_iter_fact_dicts(item))
            return facts
    return [payload]


def _candidate_from_fact(provider: str, block: DocumentBlock, fact: dict[str, Any]) -> ExtractionCandidate | None:
    label = _normalize_label(fact.get("type") or fact.get("fact_type") or fact.get("label") or fact.get("kind"))
    if label not in _ALLOWED_LABELS:
        return None
    content_role = _normalize_content_role(fact.get("content_role") or fact.get("role") or fact.get("content_type"))
    concept = _string_value(fact.get("concept") or fact.get("title") or fact.get("term"))
    formula = _string_value(fact.get("formula"))
    statement = _string_value(fact.get("statement") or fact.get("definition") or fact.get("result"))
    evidence_text = _string_value(fact.get("evidence_text") or fact.get("evidence") or fact.get("quote"))
    text = concept or formula or statement or evidence_text
    if not text:
        return None
    start_char, end_char = _evidence_offsets(block.text, evidence_text or text)
    return ExtractionCandidate(
        provider=provider,
        block_id=block.id,
        label=label,
        text=text,
        start_char=start_char,
        end_char=end_char,
        confidence=_optional_float(fact.get("confidence")),
        attributes={
            "concept": concept,
            "statement": statement,
            "formula": formula,
            "content_role": content_role,
            "fact_type": _normalize_label(fact.get("fact_type") or fact.get("type") or fact.get("label")),
            "target_concept": _string_value(
                fact.get("target_concept")
                or fact.get("support_for")
                or fact.get("example_of")
                or fact.get("misconception_of")
            ),
            "concept_aliases": _string_list(fact.get("concept_aliases") or fact.get("aliases")),
            "conditions": _string_list(fact.get("conditions")),
            "common_mistakes": _string_list(fact.get("common_mistakes") or fact.get("misconceptions")),
            "evidence_text": evidence_text,
            "pedagogical_value": _optional_float(fact.get("pedagogical_value")),
            "standalone": _optional_bool(fact.get("standalone")),
            "variables": _dict_list(fact.get("variables")),
            "relations": _dict_list(fact.get("relations")),
            "raw_fact": copy.deepcopy(fact),
        },
    )


def _message_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise ValueError("completion response must be a JSON object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("completion response has no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("completion choice is not an object")
    message = first.get("message")
    if isinstance(message, dict) and message.get("content") is not None:
        return str(message["content"])
    if first.get("text") is not None:
        return str(first["text"])
    raise ValueError("completion choice has no message content")


def _normalize_label(value: Any) -> str:
    return str(value or "").strip().casefold().replace("-", "_")


def _normalize_content_role(value: Any) -> str:
    return str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _evidence_offsets(block_text: str, evidence_text: str) -> tuple[int | None, int | None]:
    if not evidence_text:
        return None, None
    start = block_text.find(evidence_text)
    if start < 0:
        return None, None
    return start, start + len(evidence_text)


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, (str, bytes)) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any, default: float) -> float:
    converted = _optional_float(value)
    return default if converted is None else converted


def _coerce_int(value: Any, default: int) -> int:
    if isinstance(value, (str, bytes)):
        try:
            return max(1, int(value))
        except ValueError:
            return default
    try:
        return max(1, operator.index(value))
    except TypeError:
        return default
