from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class GraphStore:
    """Small SQLite wrapper for the local code graph.

    This is intentionally lightweight. Implementation tasks will add insert/query methods.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def apply_schema(self) -> None:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        with self.conn:
            self.conn.executescript(schema)

    def integrity_check(self) -> str:
        row = self.conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "unknown"

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "GraphStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()
