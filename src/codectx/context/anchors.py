"""File and line anchor resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnchorResult:
    """Resolved file/line anchor."""

    file_id: int
    file_path: str
    line: int
    node_id: int | None
    node_kind: str | None
    node_name: str | None
    qualified_name: str | None
    symbol_key: str | None
    start_line: int | None
    end_line: int | None
    chunk_id: int | None
    chunk_kind: str | None
    chunk_start_line: int | None
    chunk_end_line: int | None
    chunk_text: str | None
    chunk_token_estimate: int | None


@dataclass(frozen=True)
class AnchorError:
    """Anchor resolution error."""

    message: str


@dataclass(frozen=True)
class _ChunkFields:
    chunk_id: int | None = None
    chunk_kind: str | None = None
    chunk_start_line: int | None = None
    chunk_end_line: int | None = None
    chunk_text: str | None = None
    chunk_token_estimate: int | None = None


def resolve_file_line_anchor(
    conn: Any,
    snapshot_id: int,
    file_path: str,
    line: int,
) -> AnchorResult | AnchorError:
    """Resolve a repo-relative file/line to the smallest containing node."""
    if line < 1:
        return AnchorError("Line number must be 1 or greater.")

    file_row = conn.execute(
        """
        SELECT id, path, line_count
        FROM file
        WHERE snapshot_id = ? AND path = ?
        """,
        (snapshot_id, file_path),
    ).fetchone()
    if file_row is None:
        return AnchorError(f"File is not indexed in this snapshot: {file_path}")
    if line > int(file_row["line_count"]):
        return AnchorError(
            f"Line {line} is outside indexed file {file_path} "
            f"with {file_row['line_count']} lines."
        )

    file_id = int(file_row["id"])
    chunk_row = _nearest_chunk(conn, file_id, line)
    chunk_fields = _chunk_result_fields(chunk_row)
    node_row = conn.execute(
        """
        SELECT id, kind, name, qualified_name, symbol_key, start_line, end_line
        FROM node
        WHERE file_id = ?
          AND start_line IS NOT NULL
          AND end_line IS NOT NULL
          AND start_line <= ?
          AND end_line >= ?
        ORDER BY
          (end_line - start_line) ASC,
          CASE kind
            WHEN 'callable' THEN 0
            WHEN 'field' THEN 1
            WHEN 'type' THEN 2
            WHEN 'namespace' THEN 3
            ELSE 4
          END ASC,
          start_line DESC,
          id ASC
        LIMIT 1
        """,
        (file_id, line, line),
    ).fetchone()
    if node_row is None:
        return AnchorResult(
            file_id=file_id,
            file_path=str(file_row["path"]),
            line=line,
            node_id=None,
            node_kind=None,
            node_name=None,
            qualified_name=None,
            symbol_key=None,
            start_line=None,
            end_line=None,
            chunk_id=chunk_fields.chunk_id,
            chunk_kind=chunk_fields.chunk_kind,
            chunk_start_line=chunk_fields.chunk_start_line,
            chunk_end_line=chunk_fields.chunk_end_line,
            chunk_text=chunk_fields.chunk_text,
            chunk_token_estimate=chunk_fields.chunk_token_estimate,
        )

    return AnchorResult(
        file_id=file_id,
        file_path=str(file_row["path"]),
        line=line,
        node_id=int(node_row["id"]),
        node_kind=str(node_row["kind"]),
        node_name=None if node_row["name"] is None else str(node_row["name"]),
        qualified_name=(
            None
            if node_row["qualified_name"] is None
            else str(node_row["qualified_name"])
        ),
        symbol_key=None
        if node_row["symbol_key"] is None
        else str(node_row["symbol_key"]),
        start_line=int(node_row["start_line"]),
        end_line=int(node_row["end_line"]),
        chunk_id=chunk_fields.chunk_id,
        chunk_kind=chunk_fields.chunk_kind,
        chunk_start_line=chunk_fields.chunk_start_line,
        chunk_end_line=chunk_fields.chunk_end_line,
        chunk_text=chunk_fields.chunk_text,
        chunk_token_estimate=chunk_fields.chunk_token_estimate,
    )


def _nearest_chunk(conn: Any, file_id: int, line: int) -> Any:
    """Return the containing chunk, or nearest chunk in the same file."""
    return conn.execute(
        """
        SELECT id, kind, start_line, end_line, text, token_estimate
        FROM chunk
        WHERE file_id = ?
        ORDER BY
          CASE
            WHEN start_line <= ? AND end_line >= ? THEN 0
            ELSE 1
          END ASC,
          CASE
            WHEN end_line < ? THEN ? - end_line
            WHEN start_line > ? THEN start_line - ?
            ELSE 0
          END ASC,
          (end_line - start_line) ASC,
          start_line ASC,
          id ASC
        LIMIT 1
        """,
        (file_id, line, line, line, line, line, line),
    ).fetchone()


def _chunk_result_fields(chunk_row: Any) -> _ChunkFields:
    if chunk_row is None:
        return _ChunkFields()
    return _ChunkFields(
        chunk_id=int(chunk_row["id"]),
        chunk_kind=str(chunk_row["kind"]),
        chunk_start_line=int(chunk_row["start_line"]),
        chunk_end_line=int(chunk_row["end_line"]),
        chunk_text=str(chunk_row["text"]),
        chunk_token_estimate=int(chunk_row["token_estimate"]),
    )
