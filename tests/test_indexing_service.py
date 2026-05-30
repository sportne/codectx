from __future__ import annotations

from pathlib import Path

from codectx.frontends.base import EdgeFact, ExtractedFacts, NodeFact, OccurrenceFact
from codectx.graph.store import GraphStore
from codectx.indexing import (
    HealthResult,
    IndexingError,
    IndexResult,
    default_db_path,
    default_frontends,
    read_health,
    remove_db_files,
    resolve_unique_references,
    run_index,
)
from codectx.source.spans import SourceSpan


def test_run_index_and_read_health_round_trip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    _write(repo / "src" / "native.cpp", "int main() {}\n")
    db_path = tmp_path / "graph.sqlite"

    index_result = run_index(repo, db_path=db_path)

    assert isinstance(index_result, IndexResult)
    assert index_result.repo == repo.resolve()
    assert index_result.db_path == db_path.resolve()
    assert index_result.stats["files"] == "2"
    assert index_result.stats["nodes"] == "2"
    assert index_result.stats["edges"] == "0"
    assert index_result.stats["occurrences"] == "2"
    assert index_result.stats["chunks"] == "2"
    assert index_result.stats["diagnostics"] == "0"
    assert index_result.stats["feature.fts5"] in {"enabled", "disabled"}
    assert index_result.stats["language.java"] == "1"
    assert index_result.stats["language.cpp"] == "1"

    health_result = read_health(repo, db_path=db_path, include_integrity=True)

    assert isinstance(health_result, HealthResult)
    assert health_result.snapshot_id == index_result.snapshot_id
    assert health_result.stats == index_result.stats
    assert health_result.integrity == "ok"
    assert health_result.integrity_details == {
        "foreign_keys": "ok",
        "spans": "ok",
        "sqlite": "ok",
        "unresolved_edges": "ok",
    }


def test_default_frontends_register_java_and_cpp() -> None:
    frontends = default_frontends()

    assert sorted(frontends) == ["cpp", "java"]
    assert frontends["cpp"].language == "cpp"
    assert frontends["java"].language == "java"


def test_run_index_applies_scan_filters_to_persisted_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / ".gitignore", "ignored/\n")
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    _write(repo / "src" / "Bar.java", "class Bar {}\n")
    _write(repo / "ignored" / "Ignored.java", "class Ignored {}\n")
    db_path = tmp_path / "graph.sqlite"

    result = run_index(
        repo,
        db_path=db_path,
        include_patterns=("src/**",),
        exclude_patterns=("**/Bar.java",),
        force_include_patterns=("ignored/**",),
    )

    assert isinstance(result, IndexResult)
    assert result.stats["files"] == "2"
    with GraphStore(db_path) as store:
        rows = store.conn.execute("SELECT path FROM file ORDER BY path").fetchall()
        assert [row["path"] for row in rows] == [
            "ignored/Ignored.java",
            "src/Foo.java",
        ]


def test_run_index_persists_java_and_cpp_graph_facts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "PaymentService.java",
        "package acme;\n"
        "import java.util.List;\n"
        "class PaymentService { List<String> authorize(String user) { return null; } }\n",
    )
    _write(
        repo / "src" / "payment.cpp",
        '#include "payment/gateway.h"\n'
        "namespace acme { class PaymentService { bool authorize(int user); }; }\n",
    )
    db_path = tmp_path / "graph.sqlite"

    result = run_index(repo, db_path=db_path)

    assert isinstance(result, IndexResult)
    assert result.stats["files"] == "2"
    assert int(result.stats["nodes"]) >= 4
    assert int(result.stats["edges"]) >= 3
    assert int(result.stats["chunks"]) >= 4
    assert int(result.stats["occurrences"]) >= 5
    assert result.stats["feature.fts5"] in {"enabled", "disabled"}

    with GraphStore(db_path) as store:
        rows = store.conn.execute(
            """
            SELECT node.kind, node.language, node.name, node.symbol_key, file.path
            FROM node
            JOIN file ON file.id = node.file_id
            ORDER BY node.symbol_key
            """
        ).fetchall()
        symbols = {row["symbol_key"] for row in rows}
        assert "java:src/PaymentService.java#PaymentService" in symbols
        assert (
            "java:src/PaymentService.java#PaymentService.authorize(String)" in symbols
        )
        assert "cpp:src/payment.cpp#acme" in symbols
        assert "cpp:src/payment.cpp#acme::PaymentService" in symbols
        assert "cpp:src/payment.cpp#acme::PaymentService::authorize(int)" in symbols

        edge_rows = store.conn.execute(
            "SELECT kind, unresolved_dst FROM edge ORDER BY id"
        ).fetchall()
        assert any(row["kind"] == "imports" for row in edge_rows)
        assert any(row["kind"] == "includes" for row in edge_rows)
        assert any(row["kind"] == "contains" for row in edge_rows)

        chunk_count = store.conn.execute("SELECT COUNT(*) FROM chunk").fetchone()[0]
        assert chunk_count == int(result.stats["chunks"])
        if result.stats["feature.fts5"] == "enabled":
            assert (
                store.conn.execute("SELECT COUNT(*) FROM symbol_fts").fetchone()[0] > 0
            )
            assert (
                store.conn.execute("SELECT COUNT(*) FROM chunk_fts").fetchone()[0] > 0
            )


def test_run_index_persists_java_call_like_facts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "PaymentService.java",
        "class PaymentService {\n"
        "  boolean authorize(User user) {\n"
        "    validate(user);\n"
        "    return gateway.charge(user);\n"
        "  }\n"
        "  void validate(User user) {}\n"
        "}\n",
    )
    db_path = tmp_path / "graph.sqlite"

    result = run_index(repo, db_path=db_path)

    assert isinstance(result, IndexResult)
    assert int(result.stats["edges"]) >= 3
    assert int(result.stats["occurrences"]) >= 5

    with GraphStore(db_path) as store:
        rows = store.conn.execute(
            """
            SELECT edge.kind, src.symbol_key AS src_key, dst.symbol_key AS dst_key,
                   edge.unresolved_dst
            FROM edge
            LEFT JOIN node AS src ON src.id = edge.src_node_id
            LEFT JOIN node AS dst ON dst.id = edge.dst_node_id
            WHERE edge.kind = 'calls'
            ORDER BY edge.start_line, edge.id
            """
        ).fetchall()
        assert [(row["dst_key"], row["unresolved_dst"]) for row in rows] == [
            (
                "java:src/PaymentService.java#PaymentService.validate(User)",
                None,
            ),
            (None, "gateway.charge"),
        ]
        assert {row["src_key"] for row in rows} == {
            "java:src/PaymentService.java#PaymentService.authorize(User)"
        }

        occurrence_rows = store.conn.execute(
            """
            SELECT role, text, resolved_node_id
            FROM occurrence
            WHERE role = 'call'
            ORDER BY start_line, id
            """
        ).fetchall()
        assert [
            (row["text"], row["resolved_node_id"] is not None)
            for row in occurrence_rows
        ] == [
            ("validate", True),
            ("gateway.charge", False),
        ]


def test_run_index_persists_cpp_call_like_facts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "payment.cpp",
        "namespace acme {\n"
        "bool authorize(User user) {\n"
        "  validate(user);\n"
        "  return gateway.charge(user);\n"
        "}\n"
        "bool validate(User user) { return true; }\n"
        "}\n",
    )
    db_path = tmp_path / "graph.sqlite"

    result = run_index(repo, db_path=db_path)

    assert isinstance(result, IndexResult)
    assert int(result.stats["edges"]) >= 3
    assert int(result.stats["occurrences"]) >= 5

    with GraphStore(db_path) as store:
        rows = store.conn.execute(
            """
            SELECT src.symbol_key AS src_key, dst.symbol_key AS dst_key,
                   edge.unresolved_dst
            FROM edge
            LEFT JOIN node AS src ON src.id = edge.src_node_id
            LEFT JOIN node AS dst ON dst.id = edge.dst_node_id
            WHERE edge.kind = 'calls'
            ORDER BY edge.start_line, edge.id
            """
        ).fetchall()
        assert [(row["dst_key"], row["unresolved_dst"]) for row in rows] == [
            ("cpp:src/payment.cpp#acme::validate(User)", None),
            (None, "gateway.charge"),
        ]
        assert {row["src_key"] for row in rows} == {
            "cpp:src/payment.cpp#acme::authorize(User)"
        }

        occurrence_rows = store.conn.execute(
            """
            SELECT role, text, resolved_node_id
            FROM occurrence
            WHERE role = 'call'
            ORDER BY start_line, id
            """
        ).fetchall()
        assert [
            (row["text"], row["resolved_node_id"] is not None)
            for row in occurrence_rows
        ] == [
            ("validate", True),
            ("gateway.charge", False),
        ]


def test_run_index_records_invalid_utf8_diagnostic_without_crashing(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    path = repo / "src" / "Bad.java"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"class Bad {\xff}\n")
    db_path = tmp_path / "graph.sqlite"

    result = run_index(repo, db_path=db_path)

    assert isinstance(result, IndexResult)
    assert result.stats["files"] == "1"
    assert result.stats["diagnostics"] == "1"
    assert result.stats["nodes"] == "0"
    with GraphStore(db_path) as store:
        row = store.conn.execute(
            "SELECT code, message, extractor, metadata_json FROM diagnostic"
        ).fetchone()
        assert row["code"] == "invalid_utf8"
        assert row["extractor"] == "source-decoder"
        assert "not valid UTF-8" in row["message"]
        assert "byte_offset" in row["metadata_json"]


def test_run_index_records_binary_source_diagnostic_without_crashing(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    path = repo / "src" / "Binary.cpp"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"int main() {}\x00more")
    db_path = tmp_path / "graph.sqlite"

    result = run_index(repo, db_path=db_path)

    assert isinstance(result, IndexResult)
    assert result.stats["files"] == "1"
    assert result.stats["diagnostics"] == "1"
    assert result.stats["nodes"] == "0"
    with GraphStore(db_path) as store:
        row = store.conn.execute(
            "SELECT code, message, extractor, metadata_json FROM diagnostic"
        ).fetchone()
        assert row["code"] == "binary_source"
        assert row["extractor"] == "source-decoder"
        assert "binary content" in row["message"]
        assert "byte_offset" in row["metadata_json"]


def test_run_index_preserves_bom_and_multibyte_byte_spans(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = b'\xef\xbb\xbfclass Cafe { String name() { return "caf\xc3\xa9"; } }\n'
    path = repo / "src" / "Cafe.java"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source)
    db_path = tmp_path / "graph.sqlite"

    result = run_index(repo, db_path=db_path)

    assert isinstance(result, IndexResult)
    assert result.stats["diagnostics"] == "0"
    with GraphStore(db_path) as store:
        file_row = store.conn.execute(
            "SELECT size_bytes, line_count FROM file WHERE path = 'src/Cafe.java'"
        ).fetchone()
        assert file_row["size_bytes"] == len(source)
        assert file_row["line_count"] == 1
        node_row = store.conn.execute(
            """
            SELECT start_byte, start_line, end_byte
            FROM node
            WHERE name = 'Cafe' AND kind = 'type'
            """
        ).fetchone()
        assert node_row["start_byte"] == 3
        assert node_row["start_line"] == 1
        assert node_row["end_byte"] == len(source) - 1


def test_run_index_resolves_unique_type_references_and_preserves_ambiguous(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "PaymentService.java",
        "class PaymentService {\n"
        "  Gateway gateway;\n"
        "  Receipt authorize(User user) { return new Receipt(); }\n"
        "}\n"
        "class Gateway {}\n"
        "class Receipt {}\n"
        "class User {}\n",
    )
    _write(
        repo / "src" / "Duplicate.java",
        "class Duplicate { Missing missing; }\n",
    )
    db_path = tmp_path / "graph.sqlite"

    result = run_index(repo, db_path=db_path)

    assert isinstance(result, IndexResult)
    assert int(result.stats["unresolved_references"]) >= 1

    with GraphStore(db_path) as store:
        rows = store.conn.execute(
            """
            SELECT occurrence.text, resolved.symbol_key AS resolved_key
            FROM occurrence
            LEFT JOIN node AS resolved ON resolved.id = occurrence.resolved_node_id
            WHERE occurrence.role = 'type_reference'
            ORDER BY occurrence.text, occurrence.start_line
            """
        ).fetchall()
        resolved = {
            row["text"]: row["resolved_key"]
            for row in rows
            if row["resolved_key"] is not None
        }
        assert resolved["Gateway"] == "java:src/PaymentService.java#Gateway"
        assert resolved["Receipt"] == "java:src/PaymentService.java#Receipt"
        assert resolved["User"] == "java:src/PaymentService.java#User"
        assert any(
            row["text"] == "Missing" and row["resolved_key"] is None for row in rows
        )

        edge_rows = store.conn.execute(
            """
            SELECT edge.unresolved_dst, dst.symbol_key AS dst_key
            FROM edge
            LEFT JOIN node AS dst ON dst.id = edge.dst_node_id
            WHERE edge.kind = 'uses_type'
            ORDER BY edge.unresolved_dst, dst.symbol_key
            """
        ).fetchall()
        assert any(
            row["dst_key"] == "java:src/PaymentService.java#Gateway"
            for row in edge_rows
        )
        assert any(row["unresolved_dst"] == "Missing" for row in edge_rows)


def test_resolve_unique_references_leaves_ambiguous_reference_text_unresolved() -> None:
    span = SourceSpan("src/Foo.java", 0, 3, 1, 0, 1, 3)
    nodes = [
        NodeFact(
            kind="type",
            language="java",
            name="Shared",
            qualified_name="a.Shared",
            symbol_key="java:src/A.java#Shared",
            file_path="src/A.java",
            span=span,
            confidence=1.0,
            extractor="test",
        ),
        NodeFact(
            kind="type",
            language="java",
            name="Shared",
            qualified_name="b.Shared",
            symbol_key="java:src/B.java#Shared",
            file_path="src/B.java",
            span=span,
            confidence=1.0,
            extractor="test",
        ),
    ]
    edges = [
        EdgeFact(
            kind="uses_type",
            src_key=None,
            dst_key=None,
            unresolved_src=None,
            unresolved_dst="Shared",
            file_path="src/Foo.java",
            span=span,
            confidence=0.5,
            extractor="test",
        )
    ]
    occurrences = [
        OccurrenceFact(
            file_path="src/Foo.java",
            role="type_reference",
            text="Shared",
            span=span,
            node_key=None,
            resolved_key=None,
            confidence=0.5,
            extractor="test",
        )
    ]

    resolved_edges, resolved_occurrences = resolve_unique_references(
        nodes, edges, occurrences
    )

    assert resolved_edges == edges
    assert resolved_occurrences == occurrences


def test_resolve_unique_references_uses_language_and_type_kind() -> None:
    span = SourceSpan("src/Foo.java", 0, 3, 1, 0, 1, 3)
    nodes = [
        NodeFact(
            kind="type",
            language="cpp",
            name="Result",
            qualified_name="Result",
            symbol_key="cpp:src/result.cpp#Result",
            file_path="src/result.cpp",
            span=span,
            confidence=1.0,
            extractor="test",
        ),
        NodeFact(
            kind="field",
            language="java",
            name="Result",
            qualified_name="Foo.Result",
            symbol_key="java:src/Foo.java#Foo.Result",
            file_path="src/Foo.java",
            span=span,
            confidence=1.0,
            extractor="test",
        ),
    ]
    edges = [
        EdgeFact(
            kind="uses_type",
            src_key="java:src/Foo.java#Foo",
            dst_key=None,
            unresolved_src=None,
            unresolved_dst="Result",
            file_path="src/Foo.java",
            span=span,
            confidence=0.5,
            extractor="test",
        )
    ]
    occurrences = [
        OccurrenceFact(
            file_path="src/Foo.java",
            role="type_reference",
            text="Result",
            span=span,
            node_key="java:src/Foo.java#Foo",
            resolved_key=None,
            confidence=0.5,
            extractor="test",
        )
    ]

    resolved_edges, resolved_occurrences = resolve_unique_references(
        nodes, edges, occurrences
    )

    assert resolved_edges == edges
    assert resolved_occurrences == occurrences


def test_run_index_uses_supplied_frontend_registry(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    db_path = tmp_path / "graph.sqlite"

    result = run_index(repo, db_path=db_path, frontends={"java": EmptyFrontend()})

    assert isinstance(result, IndexResult)
    assert result.stats["files"] == "1"
    assert result.stats["nodes"] == "0"
    assert result.stats["chunks"] == "0"


def test_default_db_path_is_repo_local(tmp_path: Path) -> None:
    repo = tmp_path / "repo"

    assert default_db_path(repo, None) == repo / ".codectx" / "graph.sqlite"
    assert (
        default_db_path(repo, tmp_path / "explicit.sqlite")
        == (tmp_path / "explicit.sqlite").resolve()
    )


def test_run_index_rebuild_removes_sqlite_sidecars(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    db_path = repo / ".codectx" / "graph.sqlite"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("not sqlite", encoding="utf-8")
    Path(f"{db_path}-wal").write_text("wal", encoding="utf-8")
    Path(f"{db_path}-shm").write_text("shm", encoding="utf-8")

    result = run_index(repo, rebuild=True)

    assert isinstance(result, IndexResult)
    assert result.db_path == db_path
    assert not Path(f"{db_path}-wal").exists()
    assert not Path(f"{db_path}-shm").exists()


def test_run_index_reports_missing_repo(tmp_path: Path) -> None:
    result = run_index(tmp_path / "missing")

    assert isinstance(result, IndexingError)
    assert "Repository path does not exist" in result.message


def test_read_health_reports_missing_index(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = read_health(repo, db_path=tmp_path / "missing.sqlite")

    assert isinstance(result, IndexingError)
    assert "No codectx index found" in result.message


def test_read_health_reports_snapshot_without_stats(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = tmp_path / "incomplete.sqlite"
    with GraphStore(db_path) as store:
        store.apply_schema()
        repo_id = store.create_repo(repo)
        store.create_snapshot(repo_id)

    result = read_health(repo, db_path=db_path)

    assert isinstance(result, IndexingError)
    assert "No index health stats found" in result.message


def test_remove_db_files_ignores_missing_files(tmp_path: Path) -> None:
    remove_db_files(tmp_path / "missing.sqlite")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class EmptyFrontend:
    language = "java"

    def extract(self, file_path: str, source: bytes) -> ExtractedFacts:
        return ExtractedFacts()
