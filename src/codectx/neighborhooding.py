"""CLI-facing neighborhood orchestration services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NeighborhoodPlaceholderResult:
    """Placeholder response until bounded neighborhoods are implemented."""

    message: str


def build_neighborhood(
    repo: str | Path,
    symbol: str,
    *,
    db_path: str | Path | None = None,
    depth: int = 1,
) -> NeighborhoodPlaceholderResult:
    """Return the current placeholder response for the neighborhood command."""
    _ = (repo, symbol, db_path, depth)
    return NeighborhoodPlaceholderResult(
        message=(
            "codectx command 'neighborhood' is defined but not implemented yet.\n"
            "See docs/04-task-decomposition.md for the ordered MVP task plan."
        )
    )
