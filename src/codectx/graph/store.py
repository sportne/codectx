"""SQLite graph store lifecycle helpers."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 1

_UNRESOLVED_DST_OPTIONAL_EDGE_KINDS = (
    "contains",
    "defines",
    "declares",
    "diagnostic_for",
)


@dataclass(frozen=True)
class IntegrityReport:
    """Graph integrity status for a persisted snapshot."""

    sqlite: str
    foreign_keys: str
    span_ranges: str
    unresolved_edges: str
    problems: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Return whether every integrity validation passed."""
        return (
            self.sqlite == "ok"
            and self.foreign_keys == "ok"
            and self.span_ranges == "ok"
            and self.unresolved_edges == "ok"
            and not self.problems
        )

    def summary(self) -> str:
        """Return a concise top-level integrity status."""
        return "ok" if self.ok else "failed"

    def details(self) -> dict[str, str]:
        """Return stable detail fields suitable for CLI health output."""
        values = {
            "sqlite": self.sqlite,
            "foreign_keys": self.foreign_keys,
            "spans": self.span_ranges,
            "unresolved_edges": self.unresolved_edges,
        }
        for index, problem in enumerate(self.problems[:10], start=1):
            values[f"problem.{index}"] = problem
        return values


class _FileRecordLike(Protocol):
    """Structural protocol for scanner file records persisted by the graph store."""

    @property
    def path(self) -> str: ...

    @property
    def language(self) -> str | None: ...

    @property
    def content_hash(self) -> str: ...

    @property
    def size_bytes(self) -> int: ...

    @property
    def line_count(self) -> int: ...

    @property
    def is_test(self) -> bool: ...

    @property
    def is_generated(self) -> bool: ...

    @property
    def metadata(self) -> dict[str, Any]: ...


class _SpanLike(Protocol):
    """Structural protocol for source span coordinates."""

    @property
    def start_byte(self) -> int: ...

    @property
    def end_byte(self) -> int: ...

    @property
    def start_line(self) -> int: ...

    @property
    def end_line(self) -> int: ...


class _NodeFactLike(Protocol):
    """Structural protocol for graph node facts."""

    @property
    def kind(self) -> str: ...

    @property
    def language(self) -> str | None: ...

    @property
    def name(self) -> str | None: ...

    @property
    def qualified_name(self) -> str | None: ...

    @property
    def symbol_key(self) -> str | None: ...

    @property
    def file_path(self) -> str | None: ...

    @property
    def span(self) -> _SpanLike | None: ...

    @property
    def confidence(self) -> float: ...

    @property
    def extractor(self) -> str: ...

    @property
    def metadata(self) -> dict[str, Any]: ...


class _EdgeFactLike(Protocol):
    """Structural protocol for graph edge facts."""

    @property
    def kind(self) -> str: ...

    @property
    def src_key(self) -> str | None: ...

    @property
    def dst_key(self) -> str | None: ...

    @property
    def unresolved_src(self) -> str | None: ...

    @property
    def unresolved_dst(self) -> str | None: ...

    @property
    def file_path(self) -> str | None: ...

    @property
    def span(self) -> _SpanLike | None: ...

    @property
    def confidence(self) -> float: ...

    @property
    def extractor(self) -> str: ...

    @property
    def weight(self) -> float: ...

    @property
    def metadata(self) -> dict[str, Any]: ...


class _OccurrenceFactLike(Protocol):
    """Structural protocol for source occurrence facts."""

    @property
    def file_path(self) -> str: ...

    @property
    def role(self) -> str: ...

    @property
    def text(self) -> str: ...

    @property
    def span(self) -> _SpanLike: ...

    @property
    def node_key(self) -> str | None: ...

    @property
    def resolved_key(self) -> str | None: ...

    @property
    def confidence(self) -> float: ...

    @property
    def extractor(self) -> str: ...

    @property
    def metadata(self) -> dict[str, Any]: ...


class _ChunkFactLike(Protocol):
    """Structural protocol for context chunk facts."""

    @property
    def file_path(self) -> str: ...

    @property
    def node_key(self) -> str | None: ...

    @property
    def kind(self) -> str: ...

    @property
    def start_line(self) -> int: ...

    @property
    def end_line(self) -> int: ...

    @property
    def text(self) -> str: ...

    @property
    def token_estimate(self) -> int: ...

    @property
    def metadata(self) -> dict[str, Any]: ...


class _DiagnosticFactLike(Protocol):
    """Structural protocol for extraction diagnostic facts."""

    @property
    def file_path(self) -> str | None: ...

    @property
    def severity(self) -> str: ...

    @property
    def message(self) -> str: ...

    @property
    def extractor(self) -> str: ...

    @property
    def span(self) -> _SpanLike | None: ...

    @property
    def code(self) -> str | None: ...

    @property
    def metadata(self) -> dict[str, Any]: ...


class GraphStore:
    """Small SQLite wrapper for the local code graph.

    This is intentionally lightweight. Implementation tasks will add insert/query methods.
    """

    def __init__(self, db_path: Path) -> None:
        """Open a graph store at the given SQLite database path."""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def apply_schema(self) -> None:
        """Apply the packaged SQLite schema to the database."""
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        with self.conn:
            self.conn.executescript(schema)

    def create_repo(self, root_path: str | Path) -> int:
        """Insert a repository row and return its database id."""
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO repo(root_path) VALUES (?)",
                (str(Path(root_path).resolve()),),
            )
        return _lastrowid(cursor)

    def create_snapshot(
        self, repo_id: int, *, content_fingerprint: str | None = None
    ) -> int:
        """Insert a snapshot row for a repository and return its database id."""
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO snapshot(repo_id, schema_version, content_fingerprint)
                VALUES (?, ?, ?)
                """,
                (repo_id, SCHEMA_VERSION, content_fingerprint),
            )
        return _lastrowid(cursor)

    def insert_files(
        self, snapshot_id: int, files: Iterable[_FileRecordLike]
    ) -> dict[str, int]:
        """Batch insert source file rows and return database ids by file path."""
        file_ids: dict[str, int] = {}
        with self.conn:
            for file_record in files:
                cursor = self.conn.execute(
                    """
                    INSERT INTO file(
                      snapshot_id,
                      path,
                      language,
                      content_hash,
                      size_bytes,
                      line_count,
                      is_test,
                      is_generated,
                      metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        file_record.path,
                        file_record.language,
                        file_record.content_hash,
                        file_record.size_bytes,
                        file_record.line_count,
                        int(file_record.is_test),
                        int(file_record.is_generated),
                        _metadata_json(file_record.metadata),
                    ),
                )
                file_ids[file_record.path] = _lastrowid(cursor)
        return file_ids

    def insert_nodes(
        self,
        snapshot_id: int,
        nodes: Iterable[_NodeFactLike],
        file_ids: dict[str, int],
    ) -> dict[str, int]:
        """Batch insert node facts and return node ids by symbol key."""
        node_ids: dict[str, int] = {}
        with self.conn:
            for node in nodes:
                span = node.span
                cursor = self.conn.execute(
                    """
                    INSERT INTO node(
                      snapshot_id, kind, language, name, qualified_name, symbol_key,
                      file_id, start_byte, end_byte, start_line, end_line,
                      confidence, extractor, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        node.kind,
                        node.language,
                        node.name,
                        node.qualified_name,
                        node.symbol_key,
                        _optional_file_id(file_ids, node.file_path),
                        _span_start_byte(span),
                        _span_end_byte(span),
                        _span_start_line(span),
                        _span_end_line(span),
                        node.confidence,
                        node.extractor,
                        _metadata_json(node.metadata),
                    ),
                )
                if node.symbol_key is not None:
                    node_ids[node.symbol_key] = _lastrowid(cursor)
        return node_ids

    def insert_edges(
        self,
        snapshot_id: int,
        edges: Iterable[_EdgeFactLike],
        file_ids: dict[str, int],
        node_ids: dict[str, int],
    ) -> list[int]:
        """Batch insert edge facts and return inserted row ids."""
        edge_ids: list[int] = []
        with self.conn:
            for edge in edges:
                span = edge.span
                src_node_id = _optional_node_id(node_ids, edge.src_key)
                dst_node_id = _optional_node_id(node_ids, edge.dst_key)
                cursor = self.conn.execute(
                    """
                    INSERT INTO edge(
                      snapshot_id, kind, src_node_id, dst_node_id,
                      unresolved_src, unresolved_dst, file_id, start_byte, end_byte,
                      start_line, end_line, confidence, weight, extractor, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        edge.kind,
                        src_node_id,
                        dst_node_id,
                        _unresolved_text(
                            edge.unresolved_src, edge.src_key, src_node_id
                        ),
                        _unresolved_text(
                            edge.unresolved_dst, edge.dst_key, dst_node_id
                        ),
                        _optional_file_id(file_ids, edge.file_path),
                        _span_start_byte(span),
                        _span_end_byte(span),
                        _span_start_line(span),
                        _span_end_line(span),
                        edge.confidence,
                        edge.weight,
                        edge.extractor,
                        _metadata_json(edge.metadata),
                    ),
                )
                edge_ids.append(_lastrowid(cursor))
        return edge_ids

    def insert_occurrences(
        self,
        occurrences: Iterable[_OccurrenceFactLike],
        file_ids: dict[str, int],
        node_ids: dict[str, int],
    ) -> list[int]:
        """Batch insert occurrence facts and return inserted row ids."""
        occurrence_ids: list[int] = []
        with self.conn:
            for occurrence in occurrences:
                cursor = self.conn.execute(
                    """
                    INSERT INTO occurrence(
                      file_id, node_id, role, text, start_byte, end_byte,
                      start_line, end_line, resolved_node_id, confidence, extractor,
                      metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _required_file_id(file_ids, occurrence.file_path),
                        _optional_node_id(node_ids, occurrence.node_key),
                        occurrence.role,
                        occurrence.text,
                        occurrence.span.start_byte,
                        occurrence.span.end_byte,
                        occurrence.span.start_line,
                        occurrence.span.end_line,
                        _optional_node_id(node_ids, occurrence.resolved_key),
                        occurrence.confidence,
                        occurrence.extractor,
                        _metadata_json(occurrence.metadata),
                    ),
                )
                occurrence_ids.append(_lastrowid(cursor))
        return occurrence_ids

    def insert_chunks(
        self,
        chunks: Iterable[_ChunkFactLike],
        file_ids: dict[str, int],
        node_ids: dict[str, int],
    ) -> list[int]:
        """Batch insert context chunk facts and return inserted row ids."""
        chunk_ids: list[int] = []
        with self.conn:
            for chunk in chunks:
                cursor = self.conn.execute(
                    """
                    INSERT INTO chunk(
                      file_id, node_id, kind, start_line, end_line, text,
                      token_estimate, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _required_file_id(file_ids, chunk.file_path),
                        _optional_node_id(node_ids, chunk.node_key),
                        chunk.kind,
                        chunk.start_line,
                        chunk.end_line,
                        chunk.text,
                        chunk.token_estimate,
                        _metadata_json(chunk.metadata),
                    ),
                )
                chunk_ids.append(_lastrowid(cursor))
        return chunk_ids

    def insert_diagnostics(
        self,
        snapshot_id: int,
        diagnostics: Iterable[_DiagnosticFactLike],
        file_ids: dict[str, int],
    ) -> list[int]:
        """Batch insert diagnostic facts and return inserted row ids."""
        diagnostic_ids: list[int] = []
        with self.conn:
            for diagnostic in diagnostics:
                span = diagnostic.span
                cursor = self.conn.execute(
                    """
                    INSERT INTO diagnostic(
                      snapshot_id, file_id, start_byte, end_byte, start_line,
                      end_line, severity, code, message, extractor, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        _optional_file_id(file_ids, diagnostic.file_path),
                        _span_start_byte(span),
                        _span_end_byte(span),
                        _span_start_line(span),
                        _span_end_line(span),
                        diagnostic.severity,
                        diagnostic.code,
                        diagnostic.message,
                        diagnostic.extractor,
                        _metadata_json(diagnostic.metadata),
                    ),
                )
                diagnostic_ids.append(_lastrowid(cursor))
        return diagnostic_ids

    def build_index_stats(self, snapshot_id: int) -> dict[str, str]:
        """Build persisted health statistics for a snapshot."""
        stats = {
            "files": str(_count_rows(self.conn, "file", snapshot_id)),
            "nodes": str(_count_rows(self.conn, "node", snapshot_id)),
            "edges": str(_count_rows(self.conn, "edge", snapshot_id)),
            "occurrences": str(_count_occurrences(self.conn, snapshot_id)),
            "chunks": str(_count_chunks(self.conn, snapshot_id)),
            "diagnostics": str(_count_rows(self.conn, "diagnostic", snapshot_id)),
            "unresolved_references": str(
                _count_unresolved_edges(self.conn, snapshot_id)
            ),
        }
        for language, count in self.conn.execute(
            """
            SELECT COALESCE(language, 'unknown') AS language, COUNT(*) AS count
            FROM file
            WHERE snapshot_id = ?
            GROUP BY COALESCE(language, 'unknown')
            ORDER BY language
            """,
            (snapshot_id,),
        ):
            stats[f"language.{language}"] = str(count)
        return stats

    def upsert_index_stats(self, snapshot_id: int, stats: dict[str, str]) -> None:
        """Persist index health statistics for a snapshot."""
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO index_stat(snapshot_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(snapshot_id, key) DO UPDATE SET value = excluded.value
                """,
                ((snapshot_id, key, value) for key, value in sorted(stats.items())),
            )

    def get_index_stats(self, snapshot_id: int) -> dict[str, str]:
        """Read persisted index health statistics for a snapshot."""
        return {
            str(row["key"]): str(row["value"])
            for row in self.conn.execute(
                "SELECT key, value FROM index_stat WHERE snapshot_id = ? ORDER BY key",
                (snapshot_id,),
            ).fetchall()
        }

    def has_fts5(self) -> bool:
        """Return whether the active SQLite connection supports FTS5."""
        try:
            self.conn.execute(
                "CREATE VIRTUAL TABLE temp.codectx_fts_probe USING fts5(value)"
            )
            self.conn.execute("DROP TABLE temp.codectx_fts_probe")
        except sqlite3.OperationalError:
            return False
        return True

    def configure_fts(self, snapshot_id: int) -> bool:
        """Create and populate optional FTS tables for a snapshot."""
        if not self.has_fts5():
            return False
        try:
            self.conn.execute("DROP TABLE IF EXISTS symbol_fts")
            self.conn.execute("DROP TABLE IF EXISTS chunk_fts")
            self.conn.execute(
                """
                CREATE VIRTUAL TABLE symbol_fts USING fts5(
                  snapshot_id UNINDEXED,
                  node_id UNINDEXED,
                  text
                )
                """
            )
            self.conn.execute(
                """
                CREATE VIRTUAL TABLE chunk_fts USING fts5(
                  snapshot_id UNINDEXED,
                  chunk_id UNINDEXED,
                  text
                )
                """
            )
            self.conn.execute(
                """
                INSERT INTO symbol_fts(snapshot_id, node_id, text)
                SELECT node.snapshot_id, node.id,
                       COALESCE(node.name, '') || ' ' ||
                       COALESCE(node.qualified_name, '') || ' ' ||
                       COALESCE(node.symbol_key, '') || ' ' ||
                       COALESCE(file.path, '')
                FROM node
                LEFT JOIN file ON file.id = node.file_id
                WHERE node.snapshot_id = ?
                """,
                (snapshot_id,),
            )
            self.conn.execute(
                """
                INSERT INTO chunk_fts(snapshot_id, chunk_id, text)
                SELECT file.snapshot_id, chunk.id, chunk.text
                FROM chunk
                JOIN file ON file.id = chunk.file_id
                WHERE file.snapshot_id = ?
                """,
                (snapshot_id,),
            )
        except sqlite3.OperationalError:
            return False
        return True

    def latest_snapshot_id(self, root_path: str | Path | None = None) -> int | None:
        """Return the most recent snapshot id, optionally scoped to a repo root."""
        if root_path is None:
            row = self.conn.execute(
                "SELECT id FROM snapshot ORDER BY indexed_at DESC, id DESC LIMIT 1"
            ).fetchone()
        else:
            row = self.conn.execute(
                """
                SELECT snapshot.id
                FROM snapshot
                JOIN repo ON repo.id = snapshot.repo_id
                WHERE repo.root_path = ?
                ORDER BY snapshot.indexed_at DESC, snapshot.id DESC
                LIMIT 1
                """,
                (str(Path(root_path).resolve()),),
            ).fetchone()
        return None if row is None else int(row["id"])

    def integrity_check(self) -> str:
        """Run SQLite's integrity check and return the result string."""
        row = self.conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "unknown"

    def integrity_report(self, snapshot_id: int) -> IntegrityReport:
        """Validate SQLite and graph-level invariants for a snapshot."""
        sqlite_status = self.integrity_check()
        foreign_key_problems = _foreign_key_problems(self.conn)
        span_problems = _span_range_problems(self.conn, snapshot_id)
        unresolved_edge_problems = _unresolved_edge_problems(self.conn, snapshot_id)
        problems = tuple() if sqlite_status == "ok" else (f"sqlite: {sqlite_status}",)
        problems += foreign_key_problems + span_problems + unresolved_edge_problems
        return IntegrityReport(
            sqlite=sqlite_status,
            foreign_keys=_status_for_problems(foreign_key_problems),
            span_ranges=_status_for_problems(span_problems),
            unresolved_edges=_status_for_problems(unresolved_edge_problems),
            problems=problems,
        )

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.conn.close()

    def __enter__(self) -> GraphStore:
        """Return this store for context manager use."""
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        self.close()


def _status_for_problems(problems: tuple[str, ...]) -> str:
    return "ok" if not problems else f"failed ({len(problems)})"


def _foreign_key_problems(conn: sqlite3.Connection) -> tuple[str, ...]:
    rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    return tuple(
        f"foreign key violation: table={row[0]} rowid={row[1]} parent={row[2]} fkid={row[3]}"
        for row in rows
    )


def _span_range_problems(conn: sqlite3.Connection, snapshot_id: int) -> tuple[str, ...]:
    problems: list[str] = []
    checks = (
        (
            "node",
            """
            SELECT id, file_id, start_byte, end_byte, start_line, end_line
            FROM node
            WHERE snapshot_id = ?
            """,
        ),
        (
            "edge",
            """
            SELECT id, file_id, start_byte, end_byte, start_line, end_line
            FROM edge
            WHERE snapshot_id = ?
            """,
        ),
        (
            "diagnostic",
            """
            SELECT id, file_id, start_byte, end_byte, start_line, end_line
            FROM diagnostic
            WHERE snapshot_id = ?
            """,
        ),
        (
            "occurrence",
            """
            SELECT occurrence.id, occurrence.file_id, occurrence.start_byte,
                   occurrence.end_byte, occurrence.start_line, occurrence.end_line
            FROM occurrence
            JOIN file ON file.id = occurrence.file_id
            WHERE file.snapshot_id = ?
            """,
        ),
        (
            "chunk",
            """
            SELECT chunk.id, chunk.file_id, NULL AS start_byte, NULL AS end_byte,
                   chunk.start_line, chunk.end_line
            FROM chunk
            JOIN file ON file.id = chunk.file_id
            WHERE file.snapshot_id = ?
            """,
        ),
    )
    file_bounds = _file_bounds_by_file_id(conn, snapshot_id)
    for table, query in checks:
        for row in conn.execute(query, (snapshot_id,)).fetchall():
            problems.extend(_span_row_problems(table, row, file_bounds))
    return tuple(problems)


def _file_bounds_by_file_id(
    conn: sqlite3.Connection, snapshot_id: int
) -> dict[int, tuple[int, int]]:
    return {
        int(row["id"]): (int(row["line_count"]), int(row["size_bytes"]))
        for row in conn.execute(
            "SELECT id, line_count, size_bytes FROM file WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchall()
    }


def _span_row_problems(
    table: str, row: sqlite3.Row, file_bounds: dict[int, tuple[int, int]]
) -> list[str]:
    problems: list[str] = []
    row_id = int(row["id"])
    start_byte = _optional_int(row["start_byte"])
    end_byte = _optional_int(row["end_byte"])
    start_line = _optional_int(row["start_line"])
    end_line = _optional_int(row["end_line"])
    if start_byte is not None and end_byte is not None and start_byte > end_byte:
        problems.append(f"{table} {row_id} has start_byte after end_byte")
    if start_byte is not None and start_byte < 0:
        problems.append(f"{table} {row_id} has negative start_byte")
    if end_byte is not None and end_byte < 0:
        problems.append(f"{table} {row_id} has negative end_byte")
    if start_line is not None and end_line is not None and start_line > end_line:
        problems.append(f"{table} {row_id} has start_line after end_line")
    if start_line is not None and start_line < 1:
        problems.append(f"{table} {row_id} has non-positive start_line")
    if end_line is not None and end_line < 1:
        problems.append(f"{table} {row_id} has non-positive end_line")
    file_id = _optional_int(row["file_id"])
    if file_id is None:
        return problems
    if file_id not in file_bounds:
        problems.append(f"{table} {row_id} references a file outside the snapshot")
        return problems
    line_count, size_bytes = file_bounds[file_id]
    if start_byte is not None and start_byte > size_bytes:
        problems.append(f"{table} {row_id} start_byte exceeds file size")
    if end_byte is not None and end_byte > size_bytes:
        problems.append(f"{table} {row_id} end_byte exceeds file size")
    if start_line is not None and start_line > line_count:
        problems.append(f"{table} {row_id} start_line exceeds file line count")
    if end_line is not None and end_line > line_count:
        problems.append(f"{table} {row_id} end_line exceeds file line count")
    return problems


def _unresolved_edge_problems(
    conn: sqlite3.Connection, snapshot_id: int
) -> tuple[str, ...]:
    allowed_kinds = ",".join("?" for _ in _UNRESOLVED_DST_OPTIONAL_EDGE_KINDS)
    rows = conn.execute(
        f"""
        SELECT id, kind
        FROM edge
        WHERE snapshot_id = ?
          AND (
            (src_node_id IS NULL AND unresolved_src IS NULL)
            OR (
              dst_node_id IS NULL
              AND unresolved_dst IS NULL
              AND kind NOT IN ({allowed_kinds})
            )
          )
        ORDER BY id
        """,  # noqa: S608
        (snapshot_id, *_UNRESOLVED_DST_OPTIONAL_EDGE_KINDS),
    ).fetchall()
    return tuple(
        f"edge {int(row['id'])} has unresolved {str(row['kind'])} endpoint"
        for row in rows
    )


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _metadata_json(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, sort_keys=True, separators=(",", ":"))


def _lastrowid(cursor: sqlite3.Cursor) -> int:
    if cursor.lastrowid is None:
        raise RuntimeError("SQLite insert did not return a row id")
    return cursor.lastrowid


def _optional_file_id(file_ids: dict[str, int], file_path: str | None) -> int | None:
    if file_path is None:
        return None
    return _required_file_id(file_ids, file_path)


def _required_file_id(file_ids: dict[str, int], file_path: str) -> int:
    try:
        return file_ids[file_path]
    except KeyError as exc:
        raise KeyError(f"Unknown file path for graph persistence: {file_path}") from exc


def _optional_node_id(node_ids: dict[str, int], node_key: str | None) -> int | None:
    if node_key is None:
        return None
    return node_ids.get(node_key)


def _unresolved_text(
    explicit_unresolved: str | None, node_key: str | None, node_id: int | None
) -> str | None:
    if explicit_unresolved is not None:
        return explicit_unresolved
    if node_key is not None and node_id is None:
        return node_key
    return None


def _span_start_byte(span: _SpanLike | None) -> int | None:
    return None if span is None else span.start_byte


def _span_end_byte(span: _SpanLike | None) -> int | None:
    return None if span is None else span.end_byte


def _span_start_line(span: _SpanLike | None) -> int | None:
    return None if span is None else span.start_line


def _span_end_line(span: _SpanLike | None) -> int | None:
    return None if span is None else span.end_line


def _count_rows(conn: sqlite3.Connection, table: str, snapshot_id: int) -> int:
    if table not in {"file", "node", "edge", "diagnostic"}:
        raise ValueError(f"unsupported snapshot table: {table}")
    row = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE snapshot_id = ?",  # noqa: S608
        (snapshot_id,),
    ).fetchone()
    return int(row[0])


def _count_occurrences(conn: sqlite3.Connection, snapshot_id: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM occurrence
        JOIN file ON file.id = occurrence.file_id
        WHERE file.snapshot_id = ?
        """,
        (snapshot_id,),
    ).fetchone()
    return int(row[0])


def _count_chunks(conn: sqlite3.Connection, snapshot_id: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM chunk
        JOIN file ON file.id = chunk.file_id
        WHERE file.snapshot_id = ?
        """,
        (snapshot_id,),
    ).fetchone()
    return int(row[0])


def _count_unresolved_edges(conn: sqlite3.Connection, snapshot_id: int) -> int:
    row = conn.execute(
        """
        SELECT
          SUM(
            CASE WHEN unresolved_src IS NULL THEN 0 ELSE 1 END
            + CASE WHEN unresolved_dst IS NULL THEN 0 ELSE 1 END
          )
        FROM edge
        WHERE snapshot_id = ?
          AND (unresolved_src IS NOT NULL OR unresolved_dst IS NOT NULL)
        """,
        (snapshot_id,),
    ).fetchone()
    return int(row[0] or 0)
