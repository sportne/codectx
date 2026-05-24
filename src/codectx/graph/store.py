"""SQLite graph store lifecycle helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


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
