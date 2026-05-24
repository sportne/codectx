"""SQLite graph store lifecycle helpers."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 1


class FileRecordLike(Protocol):
    """Structural protocol for scanner file records persisted by the graph store."""

    path: str
    language: str | None
    content_hash: str
    size_bytes: int
    line_count: int
    is_test: bool
    is_generated: bool
    metadata: dict[str, Any]


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
        self, snapshot_id: int, files: Iterable[FileRecordLike]
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

    def integrity_check(self) -> str:
        """Run SQLite's integrity check and return the result string."""
        row = self.conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "unknown"

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


def _metadata_json(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, sort_keys=True, separators=(",", ":"))


def _lastrowid(cursor: sqlite3.Cursor) -> int:
    if cursor.lastrowid is None:
        raise RuntimeError("SQLite insert did not return a row id")
    return cursor.lastrowid
