# Input: Markdown-ish textbook text with source identifiers.
# Output: ordered DocumentBlock objects with 1-based line spans.
# Role: split documents into generic structural blocks for downstream extraction.
# Note: keep parsing deterministic and independent of any one textbook.

from __future__ import annotations

import re

from textbook_qa.structured_kp import BlockType, DocumentBlock

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_SETEXT_HEADING_UNDERLINE_RE = re.compile(r"^(=+|-+)\s*$")
_LIST_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
_METADATA_RE = re.compile(r"^\s*(?:author|authors|download|downloads|source|sources|copyright|license|isbn|doi|url)\s*:", re.IGNORECASE)
_IMAGE_RE = re.compile(r"^\s*(?:!\[[^\]]*\]\([^)]*\)|<img\b)", re.IGNORECASE)
_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]*\)|https?://\S+", re.IGNORECASE)
_LATEX_COMMAND_RE = re.compile(
    r"\\(?:frac|sum|int|prod|theta|alpha|beta|gamma|lambda|mu|sigma|infty|begin|end|leq|geq|neq|approx)"
)
_MATH_OPERATOR_RE = re.compile(r"(?:=|<|>|\\leq|\\geq|\\neq|\\approx)")


def parse_markdown_blocks(text: str, source_id: str = "document") -> list[DocumentBlock]:
    blocks: list[DocumentBlock] = []
    heading_path: list[str] = []
    paragraph_lines: list[str] = []
    paragraph_start = 0
    formula_lines: list[str] = []
    formula_start = 0
    formula_end_marker = ""

    def append_block(block_type: BlockType, block_text: str, line_start: int, line_end: int) -> None:
        blocks.append(
            DocumentBlock(
                id=_block_id(source_id, len(blocks) + 1),
                type=block_type,
                text=block_text,
                line_start=line_start,
                line_end=line_end,
                heading_path=list(heading_path),
                metadata={"source_id": source_id},
            )
        )

    def flush_paragraph() -> None:
        nonlocal paragraph_lines, paragraph_start
        if paragraph_lines:
            append_block(BlockType.PARAGRAPH, "\n".join(paragraph_lines), paragraph_start, paragraph_start + len(paragraph_lines) - 1)
            paragraph_lines = []
            paragraph_start = 0

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()

        if formula_lines:
            formula_lines.append(line)
            if _formula_closes(line, formula_end_marker):
                append_block(BlockType.FORMULA, "\n".join(formula_lines), formula_start, line_number)
                formula_lines = []
                formula_start = 0
                formula_end_marker = ""
            continue

        if not stripped:
            flush_paragraph()
            continue

        setext_level = _setext_heading_level(stripped)
        if setext_level and len(paragraph_lines) == 1:
            title = paragraph_lines[0].strip()
            heading_path[:] = heading_path[: setext_level - 1]
            heading_path.append(title)
            append_block(BlockType.HEADING, title, paragraph_start, line_number)
            paragraph_lines = []
            paragraph_start = 0
            continue

        marker = _opening_formula_marker(stripped)
        if marker and not _formula_is_balanced(stripped, marker):
            flush_paragraph()
            formula_lines = [line]
            formula_start = line_number
            formula_end_marker = "$$" if marker == "$$" else r"\]"
            continue

        line_type = _classify_line(line)
        if line_type is BlockType.PARAGRAPH:
            if not paragraph_lines:
                paragraph_start = line_number
            paragraph_lines.append(line)
            continue

        flush_paragraph()
        if line_type is BlockType.HEADING:
            match = _HEADING_RE.match(stripped)
            assert match is not None
            level = len(match.group(1))
            title = match.group(2).strip()
            heading_path[:] = heading_path[: level - 1]
            heading_path.append(title)
            append_block(BlockType.HEADING, title, line_number, line_number)
        else:
            append_block(line_type, line, line_number, line_number)

    flush_paragraph()
    if formula_lines:
        append_block(BlockType.FORMULA, "\n".join(formula_lines), formula_start, formula_start + len(formula_lines) - 1)

    return blocks


def _block_id(source_id: str, index: int) -> str:
    safe_source = re.sub(r"[^A-Za-z0-9_.-]+", "-", source_id.strip()).strip("-") or "document"
    return f"{safe_source}:block-{index:04d}"


def _classify_line(line: str) -> BlockType:
    stripped = line.strip()
    if _HEADING_RE.match(stripped):
        return BlockType.HEADING
    if _is_metadata_line(stripped):
        return BlockType.METADATA
    if _LIST_RE.match(line):
        return BlockType.LIST_ITEM
    if _is_image_or_link_heavy(stripped):
        return BlockType.IMAGE_REF
    if _is_formula_line(stripped):
        return BlockType.FORMULA
    return BlockType.PARAGRAPH


def _is_metadata_line(line: str) -> bool:
    return bool(_METADATA_RE.match(line))


def _setext_heading_level(line: str) -> int:
    match = _SETEXT_HEADING_UNDERLINE_RE.match(line)
    if not match or len(line.strip()) < 3:
        return 0
    return 1 if match.group(1).startswith("=") else 2


def _is_image_or_link_heavy(line: str) -> bool:
    if _IMAGE_RE.match(line):
        return True
    links = _LINK_RE.findall(line)
    if not links:
        return False
    return len(links) > 1 or len("".join(links)) >= max(12, len(line) // 2)


def _is_formula_line(line: str) -> bool:
    if _setext_heading_level(line):
        return False
    if line.startswith(r"\[") and line.endswith(r"\]"):
        return True
    if line.startswith("$$") or line.endswith("$$"):
        return True
    if line.startswith("$") and line.endswith("$") and line.count("$") >= 2:
        return True
    if line.count("$") >= 2:
        return bool(_LATEX_COMMAND_RE.search(line) or _MATH_OPERATOR_RE.search(line))

    density = _math_token_density(line)
    has_latex_command = bool(_LATEX_COMMAND_RE.search(line))
    has_operator = bool(_MATH_OPERATOR_RE.search(line))
    starts_with_latex = line.startswith("\\")

    if has_latex_command:
        return has_operator or density >= 0.20 or starts_with_latex
    if has_operator:
        return density >= 0.18 and bool(re.search(r"[0-9_^{}()+\-*/\\]", line))
    return density >= 0.45 and len(re.findall(r"[A-Za-z]{3,}", line)) <= 3


def _math_token_density(line: str) -> float:
    compact = re.sub(r"\s+", "", line)
    if not compact:
        return 0.0
    math_chars = sum(1 for char in compact if char.isdigit() or char in r"\_^{}=<>+-*/()[]$")
    return math_chars / len(compact)


def _opening_formula_marker(line: str) -> str:
    if "$$" in line:
        return "$$"
    if r"\[" in line:
        return r"\["
    return ""


def _formula_is_balanced(line: str, marker: str) -> bool:
    if marker == "$$":
        return line.count("$$") >= 2
    return r"\[" in line and r"\]" in line


def _formula_closes(line: str, end_marker: str) -> bool:
    return end_marker in line
