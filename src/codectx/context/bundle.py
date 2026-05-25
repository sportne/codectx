"""Serializable context bundle models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContextItem:
    """One ranked item selected for a context bundle."""

    rank: int
    kind: str
    file: str | None
    line_range: tuple[int, int] | None
    text: str
    score: float
    token_estimate: int
    reason: str
    confidence: float
    extractor: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    score_trace: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class OmittedItem:
    """One relevant item omitted from a context bundle."""

    name: str | None
    reason: str
    score: float | None = None


@dataclass(frozen=True)
class ContextBundle:
    """A source-grounded context bundle ready for formatting."""

    query: dict[str, Any]
    anchor: dict[str, Any]
    index_health: dict[str, Any]
    items: list[ContextItem]
    omitted: list[OmittedItem] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary representation."""
        return asdict(self)
