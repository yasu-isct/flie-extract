from __future__ import annotations

from pathlib import Path
from typing import Any

from .chunker import TextChunk
from .evidence_selector import (
    EvidenceSelector,
    build_evidence_selector,
    score_chunk_for_evidence,
    select_chunks_by_evidence_selector,
    write_evidence_selector_outputs,
)
from .profile_input import ApplicantProfileV2


ExtractionCursor = EvidenceSelector


def build_cursor(profile: ApplicantProfileV2) -> ExtractionCursor:
    """Deprecated compatibility wrapper. Use build_evidence_selector instead."""
    return build_evidence_selector(profile)


def score_chunk(chunk: TextChunk, cursor: ExtractionCursor) -> dict[str, Any]:
    """Deprecated compatibility wrapper. Use score_chunk_for_evidence instead."""
    return score_chunk_for_evidence(chunk, cursor)


def select_chunks_by_cursor(
    chunks: list[TextChunk],
    cursor: ExtractionCursor,
) -> tuple[list[TextChunk], list[dict[str, Any]]]:
    """Deprecated compatibility wrapper. Use select_chunks_by_evidence_selector instead."""
    return select_chunks_by_evidence_selector(chunks, cursor)


def write_cursor_outputs(
    chunks: list[TextChunk],
    decisions: list[dict[str, Any]],
    chunks_output: str | Path,
    decisions_output: str | Path,
) -> None:
    """Deprecated compatibility wrapper. Use write_evidence_selector_outputs instead."""
    write_evidence_selector_outputs(chunks, decisions, chunks_output, decisions_output)
