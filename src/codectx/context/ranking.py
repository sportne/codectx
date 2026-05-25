"""Deterministic context candidate scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

GOAL_POLICIES: dict[str, dict[str, float]] = {
    "explain": {
        "calls": 2.0,
        "uses_type": 1.7,
        "references": 1.5,
        "import": 0.8,
        "include": 0.8,
    },
    "failure-modes": {
        "calls": 1.4,
        "uses_type": 1.2,
        "references": 1.8,
        "import": 0.5,
        "include": 0.5,
    },
    "dependencies": {
        "calls": 1.0,
        "uses_type": 2.2,
        "references": 1.4,
        "import": 1.6,
        "include": 1.6,
    },
    "call-neighborhood": {
        "calls": 2.5,
        "uses_type": 0.8,
        "references": 1.0,
        "import": 0.3,
        "include": 0.3,
    },
}

DEFAULT_GOAL = "explain"


@dataclass(frozen=True)
class RankingAnchor:
    """Anchor fields needed by local ranking."""

    file_path: str
    line: int
    node_name: str | None = None
    qualified_name: str | None = None
    symbol_key: str | None = None


@dataclass(frozen=True)
class RankingCandidate:
    """Candidate fields needed by local ranking."""

    kind: str
    file_path: str | None
    line_range: tuple[int, int] | None
    text: str
    token_estimate: int
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RankingResult:
    """Score plus explainable component trace."""

    score: float
    score_trace: dict[str, float]


def score_candidate(
    candidate: RankingCandidate,
    anchor: RankingAnchor,
    *,
    query_text: str | None = None,
    goal: str = DEFAULT_GOAL,
) -> RankingResult:
    """Score one context candidate with a stable explainable formula."""
    components = {
        "target": 5.0 if candidate.kind.startswith("target.") else 0.0,
        "exact_match": 3.0 if _has_exact_match(candidate, anchor, query_text) else 0.0,
        "edge_relevance": _edge_relevance(candidate, goal),
        "graph_proximity": _graph_proximity(candidate),
        "source_proximity": _source_proximity(candidate, anchor),
        "lexical_match": 1.0
        if _has_lexical_match(candidate, anchor, query_text)
        else 0.0,
        "enclosing_context": 0.8 if candidate.kind.startswith("enclosing.") else 0.0,
        "test_context": 0.7 if _is_test_context(candidate) else 0.0,
        "confidence": round(0.5 * _clamp(candidate.confidence, 0.0, 1.0), 4),
        "token_cost": -round(0.8 * min(candidate.token_estimate / 1000.0, 1.0), 4),
        "redundancy": 0.0,
    }
    score = round(sum(components.values()), 4)
    return RankingResult(
        score=score,
        score_trace={**components, "total": score},
    )


def _has_exact_match(
    candidate: RankingCandidate,
    anchor: RankingAnchor,
    query_text: str | None,
) -> bool:
    needle = _normalize(query_text) or _normalize(anchor.node_name)
    if needle is None:
        return False
    return needle in {
        _normalize(candidate.metadata.get("node_name")),
        _normalize(candidate.metadata.get("qualified_name")),
        _normalize(candidate.metadata.get("symbol_key")),
    }


def _has_lexical_match(
    candidate: RankingCandidate,
    anchor: RankingAnchor,
    query_text: str | None,
) -> bool:
    needle = _normalize(query_text) or _normalize(anchor.node_name)
    if needle is None:
        return False
    haystacks = (
        candidate.file_path,
        candidate.text,
        candidate.metadata.get("node_name"),
        candidate.metadata.get("qualified_name"),
        candidate.metadata.get("symbol_key"),
    )
    return any(needle in str(_normalize(value, default="")) for value in haystacks)


def _edge_relevance(candidate: RankingCandidate, goal: str) -> float:
    policy = GOAL_POLICIES.get(goal, GOAL_POLICIES[DEFAULT_GOAL])
    edge_kind = candidate.metadata.get("edge_kind")
    if edge_kind is not None:
        return policy.get(str(edge_kind), 0.0)
    return policy.get(candidate.kind, 0.0)


def _graph_proximity(candidate: RankingCandidate) -> float:
    return 1.5 if candidate.metadata.get("edge_id") is not None else 0.0


def _source_proximity(candidate: RankingCandidate, anchor: RankingAnchor) -> float:
    if candidate.file_path != anchor.file_path or candidate.line_range is None:
        return 0.0
    start_line, end_line = candidate.line_range
    if start_line <= anchor.line <= end_line:
        return 1.2
    distance = min(abs(anchor.line - start_line), abs(anchor.line - end_line))
    return round(1.2 * max(0.0, 1.0 - min(distance, 20) / 20.0), 4)


def _is_test_context(candidate: RankingCandidate) -> bool:
    file_path = (candidate.file_path or "").lower()
    return candidate.kind.startswith("test.") or "test" in file_path


def _normalize(value: object, *, default: str | None = None) -> str | None:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    return normalized or default


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)
