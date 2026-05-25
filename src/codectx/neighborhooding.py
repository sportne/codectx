"""CLI-facing neighborhood orchestration services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codectx.graph.store import GraphStore
from codectx.graph.traversal import (
    DEFAULT_EDGE_KINDS,
    Direction,
    NeighborhoodEdge,
    NeighborhoodNode,
    bounded_neighborhood,
)
from codectx.querying import QueryingError, resolve_query_context, search_symbols


@dataclass(frozen=True)
class NeighborhoodResult:
    """Bounded neighborhood response for CLI rendering."""

    repo: Path
    db_path: Path
    snapshot_id: int
    symbol: str
    seed_node_id: int
    nodes: list[NeighborhoodNode]
    edges: list[NeighborhoodEdge]


@dataclass(frozen=True)
class NeighborhoodError:
    """Actionable neighborhood error suitable for CLI display."""

    message: str


def build_neighborhood(
    repo: str | Path,
    symbol: str,
    *,
    db_path: str | Path | None = None,
    depth: int = 1,
    direction: Direction = "out",
    edge_kinds: tuple[str, ...] | None = None,
    limit: int = 50,
) -> NeighborhoodResult | NeighborhoodError:
    """Build a bounded graph neighborhood from the top symbol match."""
    if depth < 0:
        return NeighborhoodError("Neighborhood depth must be zero or greater.")
    if limit <= 0:
        return NeighborhoodError("Neighborhood limit must be positive.")
    if direction not in {"out", "in", "both"}:
        return NeighborhoodError("Neighborhood direction must be out, in, or both.")

    context = resolve_query_context(repo, db_path=db_path)
    if isinstance(context, QueryingError):
        return NeighborhoodError(context.message)

    symbol_result = search_symbols(
        context.repo,
        symbol,
        db_path=context.db_path,
        limit=2,
    )
    if isinstance(symbol_result, QueryingError):
        return NeighborhoodError(symbol_result.message)
    if not symbol_result.symbols:
        return NeighborhoodError(
            f"No indexed symbol matched {symbol!r}. "
            "Run `codectx symbols` to find available anchors."
        )

    with GraphStore(context.db_path) as store:
        graph_result = bounded_neighborhood(
            store.conn,
            context.snapshot_id,
            symbol_result.symbols[0].node_id,
            depth=depth,
            direction=direction,
            edge_kinds=DEFAULT_EDGE_KINDS if edge_kinds is None else edge_kinds,
            limit=limit,
        )

    return NeighborhoodResult(
        repo=context.repo,
        db_path=context.db_path,
        snapshot_id=context.snapshot_id,
        symbol=symbol,
        seed_node_id=graph_result.seed_node_id,
        nodes=graph_result.nodes,
        edges=graph_result.edges,
    )
