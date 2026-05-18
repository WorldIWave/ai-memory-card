# Input: raw text returned by local/API LLM chat completions.
# Output: parsed JSON payloads with LaTeX backslashes preserved in strings.
# Role: centralize tolerant LLM JSON parsing for extraction, generation, and judging.
# Note: this repairs model-output syntax only; it does not validate domain schemas.

from __future__ import annotations

import json
from typing import Any

_JSON_ESCAPES = {'"', "\\", "/", "b", "f", "n", "r", "t", "u"}
_CONTROL_TO_LATEX = {
    "\t": "\\t",
    "\f": "\\f",
    "\r": "\\r",
    "\b": "\\b",
}
_CONTROL_TO_JSON_LATEX = {key: value.replace("\\", "\\\\") for key, value in _CONTROL_TO_LATEX.items()}


def parse_llm_json_payload(text: str) -> Any:
    payload_text = _extract_json_text(text)
    repaired = _escape_latex_backslashes_in_json_strings(payload_text)
    return normalize_llm_strings(json.loads(repaired))


def normalize_llm_strings(value: Any) -> Any:
    if isinstance(value, str):
        return _normalize_text(value)
    if isinstance(value, list):
        return [normalize_llm_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_llm_strings(item) for key, item in value.items()}
    return value


def _extract_json_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _strip_fence(stripped)
    starts = [index for index in (stripped.find("{"), stripped.find("[")) if index >= 0]
    if not starts:
        raise ValueError("no JSON object or array found")
    start = min(starts)
    end = max(stripped.rfind("}"), stripped.rfind("]"))
    if end < start:
        raise ValueError("JSON end marker not found")
    return stripped[start : end + 1]


def _strip_fence(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _escape_latex_backslashes_in_json_strings(text: str) -> str:
    repaired: list[str] = []
    in_string = False
    index = 0
    while index < len(text):
        char = text[index]
        if not in_string:
            repaired.append(char)
            if char == '"':
                in_string = True
            index += 1
            continue

        if char == '"':
            repaired.append(char)
            in_string = False
            index += 1
            continue
        if char in _CONTROL_TO_JSON_LATEX:
            repaired.append(_CONTROL_TO_JSON_LATEX[char])
            index += 1
            continue
        if char != "\\":
            repaired.append(char)
            index += 1
            continue

        next_char = text[index + 1] if index + 1 < len(text) else ""
        if next_char == "\\":
            repaired.append("\\\\")
            index += 2
            continue
        if _looks_like_latex_command(text, index):
            repaired.append("\\\\")
            index += 1
            continue
        if next_char in _JSON_ESCAPES:
            repaired.append("\\" + next_char)
            index += 2
            continue
        repaired.append("\\\\")
        index += 1
    return "".join(repaired)


def _looks_like_latex_command(text: str, backslash_index: int) -> bool:
    next_index = backslash_index + 1
    if next_index >= len(text):
        return False
    next_char = text[next_index]
    if not next_char.isalpha():
        return False
    if next_char == "u" and _has_four_hex_digits(text, next_index + 1):
        return False
    following = text[next_index + 1] if next_index + 1 < len(text) else ""
    return following.isalpha() or next_char not in _JSON_ESCAPES


def _has_four_hex_digits(text: str, start: int) -> bool:
    if start + 4 > len(text):
        return False
    return all(char in "0123456789abcdefABCDEF" for char in text[start : start + 4])


def _normalize_text(text: str) -> str:
    normalized = text
    for control, replacement in _CONTROL_TO_LATEX.items():
        normalized = normalized.replace(control, replacement)
    return normalized.strip()
