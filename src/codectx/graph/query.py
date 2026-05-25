"""Read-only graph query helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


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
