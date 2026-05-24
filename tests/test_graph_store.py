from __future__ import annotations

import json
import sqlite3

from codectx.frontends.base import (
    ChunkFact,
    DiagnosticFact,
    EdgeFact,
    NodeFact,
    OccurrenceFact,
)
from codectx.graph.store import GraphStore
from codectx.scanner.models import FileRecord
from codectx.scanner.repo import scan_repository
from codectx.source.spans import SourceSpan


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


def test_graph_store_persists_graph_facts(tmp_path) -> None:
    span = SourceSpan(
        file_path="src/Foo.java",
        start_byte=0,
        end_byte=12,
        start_line=1,
        start_col=0,
        end_line=1,
        end_col=12,
    )
    files = [
        FileRecord(
            path="src/Foo.java",
            language="java",
            content_hash="abc123",
            size_bytes=12,
            line_count=1,
        )
    ]
    nodes = [
        NodeFact(
            kind="type",
            language="java",
            name="Foo",
            qualified_name="acme.Foo",
            symbol_key="java:src/Foo.java#Foo",
            file_path="src/Foo.java",
            span=span,
            confidence=0.95,
            extractor="test",
            metadata={"visibility": "public"},
        ),
        NodeFact(
            kind="callable",
            language="java",
            name="bar",
            qualified_name="acme.Foo.bar",
            symbol_key="java:src/Foo.java#Foo.bar",
            file_path="src/Foo.java",
            span=span,
            confidence=0.9,
            extractor="test",
            metadata={},
        ),
    ]
    edges = [
        EdgeFact(
            kind="contains",
            src_key="java:src/Foo.java#Foo",
            dst_key="java:src/Foo.java#Foo.bar",
            unresolved_src=None,
            unresolved_dst=None,
            file_path="src/Foo.java",
            span=span,
            confidence=1.0,
            extractor="test",
            metadata={"reason": "lexical"},
        ),
        EdgeFact(
            kind="calls",
            src_key="java:src/Foo.java#Foo.bar",
            dst_key="java:src/Foo.java#Missing.call",
            unresolved_src=None,
            unresolved_dst=None,
            file_path="src/Foo.java",
            span=span,
            confidence=0.4,
            extractor="test",
            weight=0.25,
            metadata={},
        ),
        EdgeFact(
            kind="calls",
            src_key="java:src/Foo.java#Missing.caller",
            dst_key="java:src/Foo.java#Foo.bar",
            unresolved_src="external caller",
            unresolved_dst="explicit callee",
            file_path="src/Foo.java",
            span=span,
            confidence=0.2,
            extractor="test",
            metadata={},
        ),
    ]
    occurrences = [
        OccurrenceFact(
            file_path="src/Foo.java",
            role="definition",
            text="Foo",
            span=span,
            node_key="java:src/Foo.java#Foo",
            resolved_key="java:src/Foo.java#Foo",
            confidence=1.0,
            extractor="test",
            metadata={"kind": "type"},
        )
    ]
    chunks = [
        ChunkFact(
            file_path="src/Foo.java",
            node_key="java:src/Foo.java#Foo",
            kind="definition",
            start_line=1,
            end_line=1,
            text="class Foo {}",
            token_estimate=3,
            metadata={"source": "fixture"},
        )
    ]
    diagnostics = [
        DiagnosticFact(
            file_path="src/Foo.java",
            severity="warning",
            message="example warning",
            extractor="test",
            span=span,
            code="W001",
            metadata={"detail": "fixture"},
        )
    ]
    db_path = tmp_path / "codectx.sqlite"

    with GraphStore(db_path) as store:
        store.apply_schema()
        repo_id = store.create_repo(tmp_path)
        snapshot_id = store.create_snapshot(repo_id)
        file_ids = store.insert_files(snapshot_id, files)
        node_ids = store.insert_nodes(snapshot_id, nodes, file_ids)
        edge_ids = store.insert_edges(snapshot_id, edges, file_ids, node_ids)
        occurrence_ids = store.insert_occurrences(occurrences, file_ids, node_ids)
        chunk_ids = store.insert_chunks(chunks, file_ids, node_ids)
        diagnostic_ids = store.insert_diagnostics(snapshot_id, diagnostics, file_ids)

        assert set(node_ids) == {
            "java:src/Foo.java#Foo",
            "java:src/Foo.java#Foo.bar",
        }
        assert len(edge_ids) == 3
        assert len(occurrence_ids) == 1
        assert len(chunk_ids) == 1
        assert len(diagnostic_ids) == 1
        assert store.integrity_check() == "ok"

        node_row = store.conn.execute(
            "SELECT * FROM node WHERE symbol_key = ?", ("java:src/Foo.java#Foo",)
        ).fetchone()
        assert node_row["kind"] == "type"
        assert node_row["language"] == "java"
        assert node_row["name"] == "Foo"
        assert node_row["qualified_name"] == "acme.Foo"
        assert node_row["file_id"] == file_ids["src/Foo.java"]
        assert node_row["start_byte"] == 0
        assert node_row["end_byte"] == 12
        assert node_row["start_line"] == 1
        assert node_row["end_line"] == 1
        assert node_row["confidence"] == 0.95
        assert node_row["extractor"] == "test"
        assert json.loads(node_row["metadata_json"]) == {"visibility": "public"}

        resolved_edge = store.conn.execute(
            "SELECT * FROM edge WHERE kind = 'contains'"
        ).fetchone()
        assert resolved_edge["file_id"] == file_ids["src/Foo.java"]
        assert resolved_edge["start_byte"] == 0
        assert resolved_edge["end_byte"] == 12
        assert resolved_edge["start_line"] == 1
        assert resolved_edge["end_line"] == 1
        assert resolved_edge["src_node_id"] == node_ids["java:src/Foo.java#Foo"]
        assert resolved_edge["dst_node_id"] == node_ids["java:src/Foo.java#Foo.bar"]
        assert resolved_edge["unresolved_src"] is None
        assert resolved_edge["unresolved_dst"] is None
        assert resolved_edge["confidence"] == 1.0
        assert resolved_edge["extractor"] == "test"
        assert json.loads(resolved_edge["metadata_json"]) == {"reason": "lexical"}

        unresolved_edge = store.conn.execute(
            "SELECT * FROM edge WHERE kind = 'calls' AND unresolved_dst LIKE 'java:%'"
        ).fetchone()
        assert unresolved_edge["src_node_id"] == node_ids["java:src/Foo.java#Foo.bar"]
        assert unresolved_edge["dst_node_id"] is None
        assert unresolved_edge["unresolved_dst"] == "java:src/Foo.java#Missing.call"
        assert unresolved_edge["confidence"] == 0.4
        assert unresolved_edge["weight"] == 0.25

        explicit_unresolved_edge = store.conn.execute(
            "SELECT * FROM edge WHERE unresolved_src = 'external caller'"
        ).fetchone()
        assert explicit_unresolved_edge["src_node_id"] is None
        assert (
            explicit_unresolved_edge["dst_node_id"]
            == node_ids["java:src/Foo.java#Foo.bar"]
        )
        assert explicit_unresolved_edge["unresolved_src"] == "external caller"
        assert explicit_unresolved_edge["unresolved_dst"] == "explicit callee"

        occurrence_row = store.conn.execute("SELECT * FROM occurrence").fetchone()
        assert occurrence_row["node_id"] == node_ids["java:src/Foo.java#Foo"]
        assert occurrence_row["resolved_node_id"] == node_ids["java:src/Foo.java#Foo"]
        assert occurrence_row["role"] == "definition"
        assert occurrence_row["text"] == "Foo"
        assert occurrence_row["start_byte"] == 0
        assert occurrence_row["end_byte"] == 12
        assert occurrence_row["start_line"] == 1
        assert occurrence_row["end_line"] == 1
        assert occurrence_row["confidence"] == 1.0
        assert occurrence_row["extractor"] == "test"
        assert json.loads(occurrence_row["metadata_json"]) == {"kind": "type"}

        chunk_row = store.conn.execute("SELECT * FROM chunk").fetchone()
        assert chunk_row["node_id"] == node_ids["java:src/Foo.java#Foo"]
        assert chunk_row["kind"] == "definition"
        assert chunk_row["start_line"] == 1
        assert chunk_row["end_line"] == 1
        assert chunk_row["text"] == "class Foo {}"
        assert chunk_row["token_estimate"] == 3
        assert json.loads(chunk_row["metadata_json"]) == {"source": "fixture"}

        diagnostic_row = store.conn.execute("SELECT * FROM diagnostic").fetchone()
        assert diagnostic_row["file_id"] == file_ids["src/Foo.java"]
        assert diagnostic_row["start_byte"] == 0
        assert diagnostic_row["end_byte"] == 12
        assert diagnostic_row["start_line"] == 1
        assert diagnostic_row["end_line"] == 1
        assert diagnostic_row["severity"] == "warning"
        assert diagnostic_row["code"] == "W001"
        assert diagnostic_row["message"] == "example warning"
        assert diagnostic_row["extractor"] == "test"
        assert json.loads(diagnostic_row["metadata_json"]) == {"detail": "fixture"}


def _write(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
