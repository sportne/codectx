"""Candidate scoring, compaction, and budget selection."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codectx.context.anchors import AnchorResult
from codectx.context.bundle import OmittedItem
from codectx.context.ranking import RankingAnchor, RankingCandidate, score_candidate
from codectx.source.tokens import estimate_token_count

VENDOR_PATH_HINTS = frozenset(
    {"vendor", "vendors", "third_party", "third-party", "external"}
)


@dataclass(frozen=True)
class Candidate:
    """Internal context candidate before final bundle item rendering."""

    kind: str
    file: str | None
    line_range: tuple[int, int] | None
    text: str
    score: float
    token_estimate: int
    reason: str
    confidence: float
    extractor: str | None
    required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    score_trace: dict[str, float] = field(default_factory=dict)


def compact_large_required_enclosing_candidates(
    candidates: list[Candidate],
    budget: int,
    notes: list[str],
    trace: list[dict[str, Any]],
) -> list[Candidate]:
    """Compact required enclosing candidates that would dominate a small budget."""
    token_limit = max(250, budget // 3)
    compacted: list[Candidate] = []
    for candidate in candidates:
        if (
            not candidate.required
            or not candidate.kind.startswith("enclosing.")
            or candidate.token_estimate <= token_limit
        ):
            compacted.append(candidate)
            continue
        compacted_candidate = _compact_candidate(candidate, token_limit)
        compacted.append(compacted_candidate)
        notes.append(
            f"{candidate.kind} was compacted from "
            f"{candidate.token_estimate} to {compacted_candidate.token_estimate} "
            "estimated tokens to preserve budget for local context."
        )
        trace.append(
            {
                "stage": "compact",
                "kind": candidate.kind,
                "file": candidate.file,
                "original_tokens": candidate.token_estimate,
                "tokens": compacted_candidate.token_estimate,
            }
        )
    return compacted


def score_candidates(
    candidates: list[Candidate],
    anchor: AnchorResult,
    query: dict[str, Any],
) -> list[Candidate]:
    """Apply shared ranking scores to context candidates."""
    ranking_anchor = RankingAnchor(
        file_path=anchor.file_path,
        line=anchor.line,
        node_name=anchor.node_name,
        qualified_name=anchor.qualified_name,
        symbol_key=anchor.symbol_key,
    )
    query_text = _query_text(query)
    scored: list[Candidate] = []
    for candidate in candidates:
        result = score_candidate(
            RankingCandidate(
                kind=candidate.kind,
                file_path=candidate.file,
                line_range=candidate.line_range,
                text=candidate.text,
                token_estimate=candidate.token_estimate,
                confidence=candidate.confidence,
                metadata=candidate.metadata,
            ),
            ranking_anchor,
            query_text=query_text,
            goal=str(query.get("goal", "explain")),
        )
        scored.append(
            Candidate(
                kind=candidate.kind,
                file=candidate.file,
                line_range=candidate.line_range,
                text=candidate.text,
                score=result.score,
                token_estimate=candidate.token_estimate,
                reason=candidate.reason,
                confidence=candidate.confidence,
                extractor=candidate.extractor,
                required=candidate.required,
                metadata=candidate.metadata,
                score_trace=result.score_trace,
            )
        )
    return scored


def select_candidates(
    required: list[Candidate], optional: list[Candidate], budget: int, *, goal: str
) -> tuple[list[Candidate], list[OmittedItem]]:
    """Select candidates within a token budget and record omitted candidates."""
    selected = list(required)
    used_tokens = sum(candidate.token_estimate for candidate in selected)
    selected_ranges = [
        range_key
        for candidate in selected
        if (range_key := candidate_range_key(candidate)) is not None
    ]
    omitted: list[OmittedItem] = []
    for candidate in sorted(optional, key=lambda item: _budget_sort_key(item, goal)):
        range_key = candidate_range_key(candidate)
        if (
            range_key is not None
            and not candidate.kind.startswith("diagnostic.")
            and _is_redundant_range(range_key, selected_ranges, goal=goal)
        ):
            omitted.append(
                OmittedItem(
                    name=candidate_name(candidate),
                    reason="overlap",
                    score=candidate.score,
                )
            )
            continue
        if _should_skip_vendor_diagnostic(candidate, omitted):
            omitted.append(
                OmittedItem(
                    name=candidate_name(candidate),
                    reason="budget",
                    score=candidate.score,
                )
            )
            continue
        if used_tokens + candidate.token_estimate <= budget:
            selected.append(candidate)
            used_tokens += candidate.token_estimate
            if range_key is not None and not candidate.kind.startswith("diagnostic."):
                selected_ranges.append(range_key)
        else:
            omitted.append(
                OmittedItem(
                    name=candidate_name(candidate),
                    reason="budget",
                    score=candidate.score,
                )
            )
    return selected, omitted


def selected_chunk_ids(candidates: list[Candidate]) -> set[int]:
    """Return chunk ids already represented by candidates."""
    return {
        int(candidate.metadata["chunk_id"])
        for candidate in candidates
        if candidate.metadata.get("chunk_id") is not None
    }


def candidate_name(candidate: Candidate) -> str | None:
    """Return a stable display name for omitted candidate reporting."""
    if candidate.file is None or candidate.line_range is None:
        return candidate.kind
    start_line, end_line = candidate.line_range
    if start_line == end_line:
        return f"{candidate.file}:{start_line}"
    return f"{candidate.file}:{start_line}-{end_line}"


def is_vendor_path(file_path: str | None) -> bool:
    """Return whether a path looks like vendored or external source."""
    if file_path is None:
        return False
    return bool({part.lower() for part in Path(file_path).parts} & VENDOR_PATH_HINTS)


def candidate_range_key(candidate: Candidate) -> tuple[str, int, int] | None:
    """Return the file/line tuple used for overlap detection."""
    if candidate.file is None or candidate.line_range is None:
        return None
    start_line, end_line = candidate.line_range
    return candidate.file, start_line, end_line


def _compact_candidate(candidate: Candidate, token_limit: int) -> Candidate:
    text = _compact_text(candidate.text, token_limit)
    return Candidate(
        kind=candidate.kind,
        file=candidate.file,
        line_range=candidate.line_range,
        text=text,
        score=candidate.score,
        token_estimate=estimate_token_count(text),
        reason=candidate.reason,
        confidence=candidate.confidence,
        extractor=candidate.extractor,
        required=candidate.required,
        metadata={
            **candidate.metadata,
            "compacted": True,
            "original_token_estimate": candidate.token_estimate,
        },
        score_trace=candidate.score_trace,
    )


def _compact_text(text: str, token_limit: int) -> str:
    lines = text.splitlines(keepends=True)
    marker = "\n... omitted remainder from compacted enclosing context ...\n"
    max_chars = max(1, token_limit * 4 - len(marker))
    if len(lines) <= 2:
        return text[:max_chars].rstrip() + marker

    kept_lines: list[str] = []
    for line in lines:
        candidate_text = "".join([*kept_lines, line]).rstrip() + marker
        if estimate_token_count(candidate_text) > token_limit:
            break
        kept_lines.append(line)
    omitted_line_count = max(0, len(lines) - len(kept_lines))
    if omitted_line_count == 0:
        return text
    if not kept_lines:
        return text[:max_chars].rstrip() + marker
    return (
        "".join(kept_lines).rstrip()
        + f"\n... omitted {omitted_line_count} lines from compacted enclosing context ...\n"
    )


def _budget_sort_key(
    candidate: Candidate, goal: str
) -> tuple[float, float, str, int, int]:
    effective_score = candidate.score
    if goal == "failure-modes" and candidate.kind.startswith("diagnostic."):
        effective_score += -5.0 if candidate.metadata.get("is_vendor") is True else 5.0
    ratio = effective_score / max(candidate.token_estimate, 1)
    start_line, end_line = candidate.line_range or (0, 0)
    return (-ratio, -effective_score, candidate.file or "", start_line, end_line)


def _is_redundant_range(
    candidate: tuple[str, int, int],
    selected: list[tuple[str, int, int]],
    *,
    goal: str,
) -> bool:
    candidate_file, candidate_start, candidate_end = candidate
    for selected_file, selected_start, selected_end in selected:
        if candidate_file != selected_file:
            continue
        if (
            goal == "explain"
            and candidate_start <= selected_end
            and selected_start <= candidate_end
        ):
            return True
        if candidate_start <= selected_start and candidate_end >= selected_end:
            return True
    return False


def _should_skip_vendor_diagnostic(
    candidate: Candidate, omitted: list[OmittedItem]
) -> bool:
    return (
        candidate.kind.startswith("diagnostic.")
        and candidate.metadata.get("is_vendor") is True
        and any(
            item.reason == "budget" and not is_vendor_path(item.name)
            for item in omitted
        )
    )


def _query_text(query: dict[str, Any]) -> str | None:
    symbol = query.get("symbol")
    if symbol is not None:
        return str(symbol)
    file_path = query.get("file")
    if file_path is not None:
        return str(file_path)
    return None
