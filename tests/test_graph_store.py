from __future__ import annotations

import json
import sqlite3

from codectx.graph.store import GraphStore
from codectx.scanner.repo import scan_repository


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


def test_graph_store_persists_repository_snapshot_and_files(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    _write(repo_root / "src" / "main" / "java" / "acme" / "PaymentService.java", "a\nb")
    _write(repo_root / "src" / "test" / "java" / "PaymentServiceTest.java", "test\n")
    _write(repo_root / "vendor" / "lib" / "Gateway.cpp", "int gateway();\n")
    records = scan_repository(repo_root)
    records_by_path = {record.path: record for record in records}
    db_path = tmp_path / "codectx.sqlite"

    with GraphStore(db_path) as store:
        store.apply_schema()
        repo_id = store.create_repo(repo_root)
        snapshot_id = store.create_snapshot(
            repo_id, content_fingerprint="fingerprint-one"
        )
        file_ids = store.insert_files(snapshot_id, records)

        assert set(file_ids) == {record.path for record in records}
        assert store.integrity_check() == "ok"

        repo_row = store.conn.execute("SELECT root_path FROM repo").fetchone()
        assert repo_row["root_path"] == str(repo_root.resolve())

        snapshot_row = store.conn.execute(
            "SELECT repo_id, schema_version, content_fingerprint FROM snapshot"
        ).fetchone()
        assert dict(snapshot_row) == {
            "repo_id": repo_id,
            "schema_version": 1,
            "content_fingerprint": "fingerprint-one",
        }

        rows = {
            row["path"]: row
            for row in store.conn.execute(
                """
                SELECT id, path, language, content_hash, size_bytes, line_count,
                       is_test, is_generated, metadata_json
                FROM file
                ORDER BY path
                """
            ).fetchall()
        }

    main_file = rows["src/main/java/acme/PaymentService.java"]
    main_record = records_by_path["src/main/java/acme/PaymentService.java"]
    assert file_ids["src/main/java/acme/PaymentService.java"] == main_file["id"]
    assert main_file["language"] == "java"
    assert main_file["content_hash"] == main_record.content_hash
    assert main_file["size_bytes"] == main_record.size_bytes
    assert main_file["line_count"] == 2
    assert main_file["is_test"] == 0
    assert main_file["is_generated"] == 0

    test_file = rows["src/test/java/PaymentServiceTest.java"]
    test_record = records_by_path["src/test/java/PaymentServiceTest.java"]
    assert file_ids["src/test/java/PaymentServiceTest.java"] == test_file["id"]
    assert test_file["content_hash"] == test_record.content_hash
    assert test_file["size_bytes"] == test_record.size_bytes
    assert test_file["is_test"] == 1

    vendor_file = rows["vendor/lib/Gateway.cpp"]
    vendor_record = records_by_path["vendor/lib/Gateway.cpp"]
    assert file_ids["vendor/lib/Gateway.cpp"] == vendor_file["id"]
    assert vendor_file["language"] == "cpp"
    assert vendor_file["content_hash"] == vendor_record.content_hash
    assert vendor_file["size_bytes"] == vendor_record.size_bytes
    assert json.loads(vendor_file["metadata_json"]) == {"is_vendor": True}


def _write(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
