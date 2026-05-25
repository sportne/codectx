"""Bounded graph neighborhood traversal helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

Direction = Literal["out", "in", "both"]

DEFAULT_EDGE_KINDS = (
    "contains",
    "references",
    "calls",
    "imports",
    "includes",
    "uses_type",
    "throws",
    "tests",
)


@dataclass(frozen=True)
class NeighborhoodNode:
    """A graph node reached by bounded traversal."""

    node_id: int
    depth: int
    kind: str
    language: str | None
    name: str | None
    qualified_name: str | None
    symbol_key: str | None
    file_path: str | None
    start_line: int | None
    end_line: int | None
    confidence: float
    extractor: str


@dataclass(frozen=True)
class NeighborhoodEdge:
    """A graph edge included in a bounded traversal result."""

    edge_id: int
    depth: int
    kind: str
    src_node_id: int | None
    dst_node_id: int | None
    unresolved_src: str | None
    unresolved_dst: str | None
    file_path: str | None
    start_line: int | None
    end_line: int | None
    confidence: float
    weight: float
    extractor: str


@dataclass(frozen=True)
class NeighborhoodResult:
    """Bounded graph neighborhood result."""

    seed_node_id: int
    nodes: list[NeighborhoodNode]
    edges: list[NeighborhoodEdge]


def bounded_neighborhood(
    conn: sqlite3.Connection,
    snapshot_id: int,
    seed_node_id: int,
    *,
    depth: int = 1,
    direction: Direction = "out",
    edge_kinds: tuple[str, ...] = DEFAULT_EDGE_KINDS,
    limit: int = 50,
) -> NeighborhoodResult:
    """Traverse graph edges from a seed node with deterministic ordering."""
    if depth < 0:
        raise ValueError("depth must be non-negative")
    if limit <= 0:
        raise ValueError("limit must be positive")
    if direction not in {"out", "in", "both"}:
        raise ValueError("direction must be out, in, or both")

    node_depths: dict[int, int] = {seed_node_id: 0}
    included_edges: dict[int, NeighborhoodEdge] = {}
    frontier = [seed_node_id]

    for next_depth in range(1, depth + 1):
        next_frontier: list[int] = []
        for node_id in frontier:
            for edge in _edge_rows(
                conn,
                snapshot_id,
                node_id,
                direction,
                edge_kinds,
            ):
                adjacent_ids = _adjacent_node_ids(edge, node_id, direction)
                include_edge = True
                for adjacent_id in adjacent_ids:
                    if adjacent_id in node_depths:
                        continue
                    if len(node_depths) >= limit:
                        include_edge = False
                        continue
                    node_depths[adjacent_id] = next_depth
                    next_frontier.append(adjacent_id)
                if include_edge and len(included_edges) < limit:
                    traversal_edge = _edge_result(edge, next_depth)
                    included_edges.setdefault(traversal_edge.edge_id, traversal_edge)
        frontier = sorted(set(next_frontier))
        if not frontier or len(node_depths) >= limit:
            break

    return NeighborhoodResult(
        seed_node_id=seed_node_id,
        nodes=_node_results(conn, snapshot_id, node_depths),
        edges=sorted(
            included_edges.values(),
            key=lambda edge: (edge.depth, edge.kind, edge.edge_id),
        ),
    )


def _edge_rows(
    conn: sqlite3.Connection,
    snapshot_id: int,
    node_id: int,
    direction: Direction,
    edge_kinds: tuple[str, ...],
) -> list[sqlite3.Row]:
    predicates = []
    if direction in {"out", "both"}:
        predicates.append("edge.src_node_id = ?")
    if direction in {"in", "both"}:
        predicates.append("edge.dst_node_id = ?")
    params: list[object] = [snapshot_id, *([node_id] * len(predicates))]
    kind_filter = ""
    if edge_kinds:
        kind_filter = f"AND edge.kind IN ({','.join('?' for _ in edge_kinds)})"
        params.extend(edge_kinds)
    sql = f"""
        SELECT edge.id, edge.kind, edge.src_node_id, edge.dst_node_id,
               edge.unresolved_src, edge.unresolved_dst, file.path AS file_path,
               edge.start_line, edge.end_line, edge.confidence, edge.weight,
               edge.extractor
        FROM edge
        LEFT JOIN file ON file.id = edge.file_id
        WHERE edge.snapshot_id = ?
          AND ({" OR ".join(predicates)})
          {kind_filter}
        ORDER BY edge.kind ASC, edge.start_line ASC, edge.id ASC
        """  # noqa: S608 - dynamic fragments are fixed predicates/placeholders.
    return conn.execute(sql, tuple(params)).fetchall()


def _adjacent_node_ids(
    row: sqlite3.Row, node_id: int, direction: Direction
) -> list[int]:
    adjacent: list[int] = []
    src_id = row["src_node_id"]
    dst_id = row["dst_node_id"]
    if direction in {"out", "both"} and src_id == node_id and dst_id is not None:
        adjacent.append(int(dst_id))
    if direction in {"in", "both"} and dst_id == node_id and src_id is not None:
        adjacent.append(int(src_id))
    return adjacent


def _node_results(
    conn: sqlite3.Connection, snapshot_id: int, node_depths: dict[int, int]
) -> list[NeighborhoodNode]:
    sql = f"""
        SELECT node.id, node.kind, node.language, node.name, node.qualified_name,
               node.symbol_key, file.path AS file_path, node.start_line,
               node.end_line, node.confidence, node.extractor
        FROM node
        LEFT JOIN file ON file.id = node.file_id
        WHERE node.snapshot_id = ?
          AND node.id IN ({",".join("?" for _ in node_depths)})
        """  # noqa: S608 - dynamic fragment is a placeholder list.
    rows = conn.execute(sql, (snapshot_id, *node_depths)).fetchall()
    results = [
        NeighborhoodNode(
            node_id=int(row["id"]),
            depth=node_depths[int(row["id"])],
            kind=str(row["kind"]),
            language=None if row["language"] is None else str(row["language"]),
            name=None if row["name"] is None else str(row["name"]),
            qualified_name=None
            if row["qualified_name"] is None
            else str(row["qualified_name"]),
            symbol_key=None if row["symbol_key"] is None else str(row["symbol_key"]),
            file_path=None if row["file_path"] is None else str(row["file_path"]),
            start_line=None if row["start_line"] is None else int(row["start_line"]),
            end_line=None if row["end_line"] is None else int(row["end_line"]),
            confidence=float(row["confidence"]),
            extractor=str(row["extractor"]),
        )
        for row in rows
    ]
    results.sort(
        key=lambda node: (
            node.depth,
            (node.qualified_name or node.name or node.symbol_key or "").lower(),
            node.node_id,
        )
    )
    return results


def _edge_result(row: sqlite3.Row, depth: int) -> NeighborhoodEdge:
    return NeighborhoodEdge(
        edge_id=int(row["id"]),
        depth=depth,
        kind=str(row["kind"]),
        src_node_id=None if row["src_node_id"] is None else int(row["src_node_id"]),
        dst_node_id=None if row["dst_node_id"] is None else int(row["dst_node_id"]),
        unresolved_src=None
        if row["unresolved_src"] is None
        else str(row["unresolved_src"]),
        unresolved_dst=None
        if row["unresolved_dst"] is None
        else str(row["unresolved_dst"]),
        file_path=None if row["file_path"] is None else str(row["file_path"]),
        start_line=None if row["start_line"] is None else int(row["start_line"]),
        end_line=None if row["end_line"] is None else int(row["end_line"]),
        confidence=float(row["confidence"]),
        weight=float(row["weight"]),
        extractor=str(row["extractor"]),
    )
