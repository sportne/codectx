from __future__ import annotations

import sqlite3

from codectx.graph.store import GraphStore


def test_graph_store_applies_schema_and_integrity_check(tmp_path) -> None:
    db_path = tmp_path / "codectx.sqlite"

    with GraphStore(db_path) as store:
        store.apply_schema()

        assert store.integrity_check() == "ok"
        assert (
            store.conn.execute("SELECT version FROM schema_version").fetchone()[0] == 1
        )

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert {"repo", "snapshot", "file", "node", "edge", "occurrence"} <= tables
