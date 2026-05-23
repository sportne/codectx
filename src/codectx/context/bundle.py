from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class ContextItem:
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


@dataclass(frozen=True)
class OmittedItem:
    name: str | None
    reason: str
    score: float | None = None


@dataclass(frozen=True)
class ContextBundle:
    query: dict[str, Any]
    anchor: dict[str, Any]
    index_health: dict[str, Any]
    items: list[ContextItem]
    omitted: list[OmittedItem] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
