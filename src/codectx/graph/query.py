"""Read-only graph query helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from json import loads
from typing import Any


@dataclass(frozen=True)
class SymbolResult:
    """One symbol search result."""

    node_id: int
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
    score: int


@dataclass(frozen=True)
class ChunkSearchResult:
    """One chunk search result."""

    chunk_id: int
    node_id: int | None
    kind: str
    file_path: str
    start_line: int
    end_line: int
    text: str
    token_estimate: int
    score: int


@dataclass(frozen=True)
class CombinedSearchResult:
    """Combined symbol and chunk search results."""

    symbols: list[SymbolResult]
    chunks: list[ChunkSearchResult]
    used_fts: bool


@dataclass(frozen=True)
class NodeDetail:
    """Detailed graph node inspection result."""

    node_id: int
    kind: str
    language: str | None
    name: str | None
    qualified_name: str | None
    symbol_key: str | None
    file_path: str | None
    start_byte: int | None
    end_byte: int | None
    start_line: int | None
    end_line: int | None
    confidence: float
    extractor: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class EdgeEndpoint:
    """Resolved endpoint details for an inspected edge."""

    node_id: int
    kind: str
    name: str | None
    qualified_name: str | None
    symbol_key: str | None


@dataclass(frozen=True)
class EdgeDetail:
    """Detailed graph edge inspection result."""

    edge_id: int
    kind: str
    source: EdgeEndpoint | None
    destination: EdgeEndpoint | None
    unresolved_src: str | None
    unresolved_dst: str | None
    file_path: str | None
    start_byte: int | None
    end_byte: int | None
    start_line: int | None
    end_line: int | None
    confidence: float
    weight: float
    extractor: str
    metadata: dict[str, Any]


def get_node_detail(
    conn: sqlite3.Connection,
    snapshot_id: int,
    node_id: int,
) -> NodeDetail | None:
    """Read a node inspection record by id within a snapshot."""
    row = conn.execute(
        """
        SELECT node.id, node.kind, node.language, node.name, node.qualified_name,
               node.symbol_key, file.path AS file_path, node.start_byte,
               node.end_byte, node.start_line, node.end_line, node.confidence,
               node.extractor, node.metadata_json
        FROM node
        LEFT JOIN file ON file.id = node.file_id
        WHERE node.snapshot_id = ? AND node.id = ?
        """,
        (snapshot_id, node_id),
    ).fetchone()
    if row is None:
        return None
    return _node_detail(row)


def get_edge_detail(
    conn: sqlite3.Connection,
    snapshot_id: int,
    edge_id: int,
) -> EdgeDetail | None:
    """Read an edge inspection record by id within a snapshot."""
    row = conn.execute(
        """
        SELECT edge.id, edge.kind, edge.unresolved_src, edge.unresolved_dst,
               file.path AS file_path, edge.start_byte, edge.end_byte,
               edge.start_line, edge.end_line, edge.confidence, edge.weight,
               edge.extractor, edge.metadata_json,
               src.id AS src_id, src.kind AS src_kind, src.name AS src_name,
               src.qualified_name AS src_qualified_name,
               src.symbol_key AS src_symbol_key,
               dst.id AS dst_id, dst.kind AS dst_kind, dst.name AS dst_name,
               dst.qualified_name AS dst_qualified_name,
               dst.symbol_key AS dst_symbol_key
        FROM edge
        LEFT JOIN file ON file.id = edge.file_id
        LEFT JOIN node AS src ON src.id = edge.src_node_id
        LEFT JOIN node AS dst ON dst.id = edge.dst_node_id
        WHERE edge.snapshot_id = ? AND edge.id = ?
        """,
        (snapshot_id, edge_id),
    ).fetchone()
    if row is None:
        return None
    return _edge_detail(row)


def search(
    conn: sqlite3.Connection,
    snapshot_id: int,
    query: str,
    *,
    limit: int = 20,
) -> CombinedSearchResult:
    """Search symbols and chunks, using FTS when available."""
    if _fts_tables_exist(conn):
        try:
            symbols = _merge_symbols(
                _search_symbols_fts(conn, snapshot_id, query, limit=limit),
                search_symbols(conn, snapshot_id, query, limit=limit),
                limit,
            )
            chunks = _merge_chunks(
                _search_chunks_fts(conn, snapshot_id, query, limit=limit),
                search_chunks_like(conn, snapshot_id, query, limit=limit),
                limit,
            )
            return CombinedSearchResult(symbols=symbols, chunks=chunks, used_fts=True)
        except sqlite3.OperationalError:
            pass
    return CombinedSearchResult(
        symbols=search_symbols(conn, snapshot_id, query, limit=limit),
        chunks=search_chunks_like(conn, snapshot_id, query, limit=limit),
        used_fts=False,
    )


def search_symbols(
    conn: sqlite3.Connection,
    snapshot_id: int,
    query: str,
    *,
    limit: int = 20,
) -> list[SymbolResult]:
    """Search symbols in a snapshot with deterministic LIKE ranking."""
    normalized = query.strip().lower()
    if not normalized:
        return []

    rows = conn.execute(
        """
        SELECT
          node.id, node.kind, node.language, node.name, node.qualified_name,
          node.symbol_key, file.path AS file_path, node.start_line, node.end_line,
          node.confidence, node.extractor
        FROM node
        LEFT JOIN file ON file.id = node.file_id
        WHERE node.snapshot_id = ?
          AND (
            lower(COALESCE(node.name, '')) LIKE ?
              ESCAPE '\\'
            OR lower(COALESCE(node.qualified_name, '')) LIKE ?
              ESCAPE '\\'
            OR lower(COALESCE(node.symbol_key, '')) LIKE ?
              ESCAPE '\\'
            OR lower(COALESCE(file.path, '')) LIKE ?
              ESCAPE '\\'
          )
        """,
        (snapshot_id, *_like_args(normalized)),
    ).fetchall()

    results = [_symbol_result(row, _symbol_score(row, normalized)) for row in rows]
    results.sort(
        key=lambda result: (
            -result.score,
            (result.qualified_name or result.name or "").lower(),
            (result.file_path or "").lower(),
            result.start_line if result.start_line is not None else 0,
            result.node_id,
        )
    )
    return results[:limit]


def search_chunks_like(
    conn: sqlite3.Connection,
    snapshot_id: int,
    query: str,
    *,
    limit: int = 20,
) -> list[ChunkSearchResult]:
    """Search chunks with deterministic LIKE ranking."""
    normalized = query.strip().lower()
    if not normalized:
        return []
    rows = conn.execute(
        """
        SELECT chunk.id, chunk.node_id, chunk.kind, file.path AS file_path,
               chunk.start_line, chunk.end_line, chunk.text, chunk.token_estimate
        FROM chunk
        JOIN file ON file.id = chunk.file_id
        WHERE file.snapshot_id = ?
          AND lower(chunk.text) LIKE ? ESCAPE '\\'
        ORDER BY chunk.id
        """,
        (snapshot_id, f"%{_escape_like(normalized)}%"),
    ).fetchall()
    results = [_chunk_result(row, _chunk_score(row, normalized)) for row in rows]
    results.sort(
        key=lambda result: (
            -result.score,
            result.file_path.lower(),
            result.start_line,
            result.chunk_id,
        )
    )
    return results[:limit]


def _fts_tables_exist(conn: sqlite3.Connection) -> bool:
    rows = conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name IN ('symbol_fts', 'chunk_fts')
        """
    ).fetchall()
    return {str(row["name"]) for row in rows} == {"symbol_fts", "chunk_fts"}


def _search_symbols_fts(
    conn: sqlite3.Connection, snapshot_id: int, query: str, *, limit: int
) -> list[SymbolResult]:
    rows = conn.execute(
        """
        SELECT node.id, node.kind, node.language, node.name, node.qualified_name,
               node.symbol_key, file.path AS file_path, node.start_line,
               node.end_line, node.confidence, node.extractor,
               bm25(symbol_fts) AS rank
        FROM symbol_fts
        JOIN node ON node.id = symbol_fts.node_id
        LEFT JOIN file ON file.id = node.file_id
        WHERE symbol_fts.snapshot_id = ? AND symbol_fts MATCH ?
        ORDER BY rank, node.id
        LIMIT ?
        """,
        (snapshot_id, _fts_query(query), limit),
    ).fetchall()
    return [_symbol_result(row, 120) for row in rows]


def _search_chunks_fts(
    conn: sqlite3.Connection, snapshot_id: int, query: str, *, limit: int
) -> list[ChunkSearchResult]:
    rows = conn.execute(
        """
        SELECT chunk.id, chunk.node_id, chunk.kind, file.path AS file_path,
               chunk.start_line, chunk.end_line, chunk.text, chunk.token_estimate,
               bm25(chunk_fts) AS rank
        FROM chunk_fts
        JOIN chunk ON chunk.id = chunk_fts.chunk_id
        JOIN file ON file.id = chunk.file_id
        WHERE chunk_fts.snapshot_id = ? AND chunk_fts MATCH ?
        ORDER BY rank, chunk.id
        LIMIT ?
        """,
        (snapshot_id, _fts_query(query), limit),
    ).fetchall()
    return [_chunk_result(row, 120) for row in rows]


def _fts_query(query: str) -> str:
    terms = [term.replace('"', '""') for term in query.strip().split() if term]
    if not terms:
        return '""'
    return " ".join(f'"{term}"' for term in terms)


def _merge_symbols(
    primary: list[SymbolResult], fallback: list[SymbolResult], limit: int
) -> list[SymbolResult]:
    seen: set[int] = set()
    merged: list[SymbolResult] = []
    for result in (*primary, *fallback):
        if result.node_id in seen:
            continue
        seen.add(result.node_id)
        merged.append(result)
    return merged[:limit]


def _merge_chunks(
    primary: list[ChunkSearchResult], fallback: list[ChunkSearchResult], limit: int
) -> list[ChunkSearchResult]:
    seen: set[int] = set()
    merged: list[ChunkSearchResult] = []
    for result in (*primary, *fallback):
        if result.chunk_id in seen:
            continue
        seen.add(result.chunk_id)
        merged.append(result)
    return merged[:limit]


def _like_args(normalized_query: str) -> tuple[str, str, str, str]:
    pattern = f"%{_escape_like(normalized_query)}%"
    return pattern, pattern, pattern, pattern


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _symbol_score(row: sqlite3.Row, normalized_query: str) -> int:
    values = {
        "name": str(row["name"] or "").lower(),
        "qualified_name": str(row["qualified_name"] or "").lower(),
        "symbol_key": str(row["symbol_key"] or "").lower(),
        "file_path": str(row["file_path"] or "").lower(),
    }
    if normalized_query in {
        values["name"],
        values["qualified_name"],
        values["symbol_key"],
    }:
        return 100
    if any(
        value.startswith(normalized_query)
        for value in (
            values["name"],
            values["qualified_name"],
            values["symbol_key"],
        )
    ):
        return 80
    if any(
        normalized_query in value
        for value in (
            values["name"],
            values["qualified_name"],
            values["symbol_key"],
        )
    ):
        return 60
    if normalized_query in values["file_path"]:
        return 40
    return 0


def _symbol_result(row: sqlite3.Row, score: int) -> SymbolResult:
    return SymbolResult(
        node_id=int(row["id"]),
        kind=str(row["kind"]),
        language=None if row["language"] is None else str(row["language"]),
        name=None if row["name"] is None else str(row["name"]),
        qualified_name=(
            None if row["qualified_name"] is None else str(row["qualified_name"])
        ),
        symbol_key=None if row["symbol_key"] is None else str(row["symbol_key"]),
        file_path=None if row["file_path"] is None else str(row["file_path"]),
        start_line=None if row["start_line"] is None else int(row["start_line"]),
        end_line=None if row["end_line"] is None else int(row["end_line"]),
        confidence=float(row["confidence"]),
        extractor=str(row["extractor"]),
        score=score,
    )


def _chunk_score(row: sqlite3.Row, normalized_query: str) -> int:
    text = str(row["text"]).lower()
    if text.startswith(normalized_query):
        return 80
    if normalized_query in text:
        return 60
    return 0


def _chunk_result(row: sqlite3.Row, score: int) -> ChunkSearchResult:
    return ChunkSearchResult(
        chunk_id=int(row["id"]),
        node_id=None if row["node_id"] is None else int(row["node_id"]),
        kind=str(row["kind"]),
        file_path=str(row["file_path"]),
        start_line=int(row["start_line"]),
        end_line=int(row["end_line"]),
        text=str(row["text"]),
        token_estimate=int(row["token_estimate"]),
        score=score,
    )


def _node_detail(row: sqlite3.Row) -> NodeDetail:
    return NodeDetail(
        node_id=int(row["id"]),
        kind=str(row["kind"]),
        language=None if row["language"] is None else str(row["language"]),
        name=None if row["name"] is None else str(row["name"]),
        qualified_name=(
            None if row["qualified_name"] is None else str(row["qualified_name"])
        ),
        symbol_key=None if row["symbol_key"] is None else str(row["symbol_key"]),
        file_path=None if row["file_path"] is None else str(row["file_path"]),
        start_byte=None if row["start_byte"] is None else int(row["start_byte"]),
        end_byte=None if row["end_byte"] is None else int(row["end_byte"]),
        start_line=None if row["start_line"] is None else int(row["start_line"]),
        end_line=None if row["end_line"] is None else int(row["end_line"]),
        confidence=float(row["confidence"]),
        extractor=str(row["extractor"]),
        metadata=_metadata(row["metadata_json"]),
    )


def _edge_detail(row: sqlite3.Row) -> EdgeDetail:
    return EdgeDetail(
        edge_id=int(row["id"]),
        kind=str(row["kind"]),
        source=_endpoint(row, "src"),
        destination=_endpoint(row, "dst"),
        unresolved_src=(
            None if row["unresolved_src"] is None else str(row["unresolved_src"])
        ),
        unresolved_dst=(
            None if row["unresolved_dst"] is None else str(row["unresolved_dst"])
        ),
        file_path=None if row["file_path"] is None else str(row["file_path"]),
        start_byte=None if row["start_byte"] is None else int(row["start_byte"]),
        end_byte=None if row["end_byte"] is None else int(row["end_byte"]),
        start_line=None if row["start_line"] is None else int(row["start_line"]),
        end_line=None if row["end_line"] is None else int(row["end_line"]),
        confidence=float(row["confidence"]),
        weight=float(row["weight"]),
        extractor=str(row["extractor"]),
        metadata=_metadata(row["metadata_json"]),
    )


def _endpoint(row: sqlite3.Row, prefix: str) -> EdgeEndpoint | None:
    node_id = row[f"{prefix}_id"]
    if node_id is None:
        return None
    return EdgeEndpoint(
        node_id=int(node_id),
        kind=str(row[f"{prefix}_kind"]),
        name=None if row[f"{prefix}_name"] is None else str(row[f"{prefix}_name"]),
        qualified_name=(
            None
            if row[f"{prefix}_qualified_name"] is None
            else str(row[f"{prefix}_qualified_name"])
        ),
        symbol_key=(
            None
            if row[f"{prefix}_symbol_key"] is None
            else str(row[f"{prefix}_symbol_key"])
        ),
    )


def _metadata(value: str) -> dict[str, Any]:
    metadata = loads(value)
    if isinstance(metadata, dict):
        return metadata
    return {}
