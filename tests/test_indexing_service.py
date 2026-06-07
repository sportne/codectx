from __future__ import annotations

from pathlib import Path

from codectx.frontends.base import (
    ChunkFact,
    DiagnosticFact,
    EdgeFact,
    ExtractedFacts,
    NodeFact,
    OccurrenceFact,
)
from codectx.graph.store import GraphStore
from codectx.indexing import (
    EXTRACTION_CACHE_VERSION,
    HealthResult,
    IndexingError,
    IndexResult,
    _facts_from_cache,
    _facts_to_cache,
    default_db_path,
    default_frontends,
    read_health,
    remove_db_files,
    resolve_unique_references,
    run_index,
)
from codectx.scanner.hashing import file_sha256
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


def test_default_frontends_register_builtin_languages() -> None:
    frontends = default_frontends()

    assert sorted(frontends) == ["cpp", "go", "java", "matlab", "python"]
    assert frontends["cpp"].language == "cpp"
    assert frontends["go"].language == "go"
    assert frontends["java"].language == "java"
    assert frontends["matlab"].language == "matlab"
    assert frontends["python"].language == "python"


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


def test_run_index_persists_python_graph_facts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "payments" / "service.py",
        "from payments.gateway import PaymentGateway\n\n"
        "class PaymentService:\n"
        "    gateway = None\n\n"
        "    def authorize(self, request):\n"
        "        validate(request)\n"
        "        return self.gateway.charge(request)\n\n"
        "def validate(request):\n"
        "    return request is not None\n",
    )
    _write(
        repo / "tests" / "test_service.py",
        "from payments.service import PaymentService\n\n"
        "def test_authorize():\n"
        "    service = PaymentService()\n"
        "    service.authorize(object())\n",
    )
    db_path = tmp_path / "graph.sqlite"

    result = run_index(repo, db_path=db_path)

    assert isinstance(result, IndexResult)
    assert result.stats["files"] == "2"
    assert result.stats["language.python"] == "2"
    assert int(result.stats["nodes"]) >= 5
    assert int(result.stats["edges"]) >= 5
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
        assert "python:src/payments/service.py#PaymentService" in symbols
        assert (
            "python:src/payments/service.py#PaymentService.authorize(self,request)"
            in symbols
        )
        assert "python:src/payments/service.py#PaymentService.gateway" in symbols
        assert "python:src/payments/service.py#validate(request)" in symbols

        edge_rows = store.conn.execute(
            "SELECT kind, unresolved_dst FROM edge ORDER BY id"
        ).fetchall()
        assert any(row["kind"] == "imports" for row in edge_rows)
        assert any(row["kind"] == "calls" for row in edge_rows)
        assert any(row["kind"] == "contains" for row in edge_rows)


def test_run_index_persists_matlab_graph_facts_and_script_chunks(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "PaymentService.m",
        "classdef PaymentService < handle\n"
        "    properties\n"
        "        Gateway\n"
        "    end\n"
        "    methods\n"
        "        function ok = authorize(obj, request)\n"
        "            validate(request);\n"
        "            ok = obj.Gateway.charge(request);\n"
        "        end\n"
        "        function validate(obj, request)\n"
        "            ok = isempty(request);\n"
        "        end\n"
        "    end\n"
        "end\n",
    )
    _write(
        repo / "scripts" / "run_payment.m",
        "gateway = PaymentGateway();\n"
        'request = PaymentRequest("u1", 42);\n'
        "ok = authorize(request, gateway);\n",
    )
    db_path = tmp_path / "graph.sqlite"

    result = run_index(repo, db_path=db_path)

    assert isinstance(result, IndexResult)
    assert result.stats["files"] == "2"
    assert result.stats["language.matlab"] == "2"
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
        assert "matlab:src/PaymentService.m#PaymentService" in symbols
        assert "matlab:src/PaymentService.m#PaymentService.Gateway" in symbols
        assert (
            "matlab:src/PaymentService.m#PaymentService.authorize(obj,request)"
            in symbols
        )
        assert (
            "matlab:src/PaymentService.m#PaymentService.validate(obj,request)"
            in symbols
        )

        script_chunk = store.conn.execute(
            """
            SELECT chunk.kind, chunk.text
            FROM chunk
            JOIN file ON file.id = chunk.file_id
            WHERE file.path = 'scripts/run_payment.m'
            """
        ).fetchone()
        assert script_chunk["kind"] == "source"
        assert "authorize(request, gateway)" in script_chunk["text"]

        edge_rows = store.conn.execute(
            "SELECT kind, unresolved_dst FROM edge ORDER BY id"
        ).fetchall()
        assert any(row["kind"] == "calls" for row in edge_rows)
        assert any(row["kind"] == "contains" for row in edge_rows)


def test_run_index_persists_go_graph_facts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "service.go",
        "package payments\n\n"
        'import "context"\n\n'
        "type PaymentService struct { Gateway PaymentGateway }\n"
        "type PaymentGateway interface { Charge(context.Context, PaymentRequest) (Receipt, error) }\n"
        "type PaymentRequest struct { Amount int }\n"
        "type Receipt struct { Approved bool }\n\n"
        "func (s *PaymentService) Authorize(ctx context.Context, request PaymentRequest) (Receipt, error) {\n"
        "    s.validate(request)\n"
        "    return s.Gateway.Charge(ctx, request)\n"
        "}\n\n"
        "func (s *PaymentService) validate(request PaymentRequest) error { return nil }\n",
    )
    _write(
        repo / "service_test.go",
        "package payments\n\n"
        "func TestAuthorizeAllowsValidPayment() {\n"
        "    service := PaymentService{}\n"
        "    service.Authorize(nil, PaymentRequest{Amount: 42})\n"
        "}\n",
    )
    db_path = tmp_path / "graph.sqlite"

    result = run_index(repo, db_path=db_path)

    assert isinstance(result, IndexResult)
    assert result.stats["files"] == "2"
    assert result.stats["language.go"] == "2"
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
        assert "go:service.go#payments" in symbols
        assert "go:service.go#PaymentService" in symbols
        assert "go:service.go#PaymentService.Gateway" in symbols
        assert (
            "go:service.go#PaymentService.Authorize(context.Context,PaymentRequest)"
            in symbols
        )
        assert "go:service.go#PaymentService.validate(PaymentRequest)" in symbols

        edge_rows = store.conn.execute(
            "SELECT kind, unresolved_dst FROM edge ORDER BY id"
        ).fetchall()
        assert any(row["kind"] == "imports" for row in edge_rows)
        assert any(row["kind"] == "calls" for row in edge_rows)
        assert any(row["kind"] == "contains" for row in edge_rows)


def test_extraction_cache_round_trips_all_fact_types() -> None:
    span = SourceSpan(
        file_path="src/Foo.java",
        start_byte=0,
        end_byte=12,
        start_line=1,
        start_col=0,
        end_line=1,
        end_col=12,
    )
    facts = ExtractedFacts(
        nodes=[
            NodeFact(
                kind="type",
                language="java",
                name="Foo",
                qualified_name="acme.Foo",
                symbol_key="java:src/Foo.java#Foo",
                file_path="src/Foo.java",
                span=span,
                confidence=0.9,
                extractor="test",
                metadata={"node": True},
            )
        ],
        edges=[
            EdgeFact(
                kind="uses_type",
                src_key="java:src/Foo.java#Foo",
                dst_key=None,
                unresolved_src=None,
                unresolved_dst="Bar",
                file_path="src/Foo.java",
                span=span,
                confidence=0.8,
                extractor="test",
                weight=2.0,
                metadata={"edge": True},
            )
        ],
        occurrences=[
            OccurrenceFact(
                file_path="src/Foo.java",
                role="type_reference",
                text="Bar",
                span=span,
                node_key="java:src/Foo.java#Foo",
                resolved_key=None,
                confidence=0.7,
                extractor="test",
                metadata={"occurrence": True},
            )
        ],
        chunks=[
            ChunkFact(
                file_path="src/Foo.java",
                node_key="java:src/Foo.java#Foo",
                kind="definition",
                start_line=1,
                end_line=1,
                text="class Foo {}",
                token_estimate=3,
                metadata={"chunk": True},
            )
        ],
        diagnostics=[
            DiagnosticFact(
                file_path="src/Foo.java",
                severity="warning",
                message="synthetic",
                extractor="test",
                span=span,
                code="synthetic",
                metadata={"diagnostic": True},
            )
        ],
    )

    round_tripped = _facts_from_cache(_facts_to_cache(facts))

    assert round_tripped == facts


def test_run_index_reuses_existing_snapshot_when_content_is_unchanged(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    db_path = tmp_path / "graph.sqlite"
    first_frontend = CountingFrontend()

    first = run_index(repo, db_path=db_path, frontends={"java": first_frontend})
    second = run_index(repo, db_path=db_path, frontends={"java": ExplodingFrontend()})

    assert isinstance(first, IndexResult)
    assert isinstance(second, IndexResult)
    assert first.snapshot_id == second.snapshot_id
    assert first_frontend.calls == ["src/Foo.java"]
    assert second.stats["index.mode"] == "unchanged"
    assert second.stats["index.cache_hits"] == "1"
    assert second.stats["index.cache_misses"] == "0"


def test_run_index_reextracts_only_changed_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    _write(repo / "src" / "Bar.java", "class Bar {}\n")
    db_path = tmp_path / "graph.sqlite"

    first = run_index(repo, db_path=db_path, frontends={"java": CountingFrontend()})
    _write(repo / "src" / "Bar.java", "class Bar { int changed; }\n")
    frontend = CountingFrontend()
    second = run_index(repo, db_path=db_path, frontends={"java": frontend})

    assert isinstance(first, IndexResult)
    assert isinstance(second, IndexResult)
    assert second.snapshot_id != first.snapshot_id
    assert frontend.calls == ["src/Bar.java"]
    assert second.stats["index.mode"] == "incremental"
    assert second.stats["index.cache_hits"] == "1"
    assert second.stats["index.cache_misses"] == "1"


def test_run_index_recomputes_global_resolution_from_cached_facts(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "User.java", "class User {}\n")
    _write(repo / "src" / "Service.java", "class Service { User user; }\n")
    db_path = tmp_path / "graph.sqlite"

    run_index(repo, db_path=db_path, frontends={"java": ReferenceFrontend()})
    _write(repo / "src" / "Service.java", "class Service { User changed; }\n")
    second = run_index(repo, db_path=db_path, frontends={"java": ReferenceFrontend()})

    assert isinstance(second, IndexResult)
    assert second.stats["index.cache_hits"] == "1"
    assert second.stats["index.cache_misses"] == "1"
    with GraphStore(db_path) as store:
        row = store.conn.execute(
            """
            SELECT dst.symbol_key AS dst_key, edge.unresolved_dst
            FROM edge
            LEFT JOIN node AS dst ON dst.id = edge.dst_node_id
            WHERE edge.snapshot_id = ?
              AND edge.kind = 'uses_type'
            """,
            (second.snapshot_id,),
        ).fetchone()
        assert row["dst_key"] == "java:src/User.java#User"
        assert row["unresolved_dst"] is None


def test_run_index_handles_added_and_removed_files_incrementally(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    original = repo / "src" / "Foo.java"
    _write(original, "class Foo {}\n")
    db_path = tmp_path / "graph.sqlite"

    first = run_index(repo, db_path=db_path, frontends={"java": CountingFrontend()})
    original.unlink()
    _write(repo / "src" / "Bar.java", "class Bar {}\n")
    second = run_index(repo, db_path=db_path, frontends={"java": CountingFrontend()})

    assert isinstance(first, IndexResult)
    assert isinstance(second, IndexResult)
    assert second.snapshot_id != first.snapshot_id
    assert second.stats["files"] == "1"
    with GraphStore(db_path) as store:
        rows = store.conn.execute(
            "SELECT path FROM file WHERE snapshot_id = ?", (second.snapshot_id,)
        ).fetchall()
        assert [row["path"] for row in rows] == ["src/Bar.java"]


def test_run_index_cache_misses_when_only_wrong_cache_version_exists(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        store.apply_schema()
        store.upsert_extraction_cache(
            path="src/Foo.java",
            language="java",
            content_hash=file_sha256(repo / "src" / "Foo.java"),
            cache_version=EXTRACTION_CACHE_VERSION - 1,
            facts=_facts_to_cache(ExtractedFacts()),
        )
    frontend = CountingFrontend()

    result = run_index(repo, db_path=db_path, frontends={"java": frontend})

    assert isinstance(result, IndexResult)
    assert frontend.calls == ["src/Foo.java"]
    assert result.stats["index.cache_hits"] == "0"
    assert result.stats["index.cache_misses"] == "1"


def test_run_index_cache_misses_when_only_wrong_path_exists(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        store.apply_schema()
        store.upsert_extraction_cache(
            path="src/Other.java",
            language="java",
            content_hash=file_sha256(repo / "src" / "Foo.java"),
            cache_version=EXTRACTION_CACHE_VERSION,
            facts=_facts_to_cache(ExtractedFacts()),
        )
    frontend = CountingFrontend()

    result = run_index(repo, db_path=db_path, frontends={"java": frontend})

    assert isinstance(result, IndexResult)
    assert frontend.calls == ["src/Foo.java"]
    assert result.stats["index.cache_hits"] == "0"
    assert result.stats["index.cache_misses"] == "1"


def test_run_index_cache_misses_when_only_wrong_language_exists(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        store.apply_schema()
        store.upsert_extraction_cache(
            path="src/Foo.java",
            language="cpp",
            content_hash=file_sha256(repo / "src" / "Foo.java"),
            cache_version=EXTRACTION_CACHE_VERSION,
            facts=_facts_to_cache(ExtractedFacts()),
        )
    frontend = CountingFrontend()

    result = run_index(repo, db_path=db_path, frontends={"java": frontend})

    assert isinstance(result, IndexResult)
    assert frontend.calls == ["src/Foo.java"]
    assert result.stats["index.cache_hits"] == "0"
    assert result.stats["index.cache_misses"] == "1"


def test_run_index_treats_malformed_extraction_cache_as_miss(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        store.apply_schema()
        store.conn.execute(
            """
            INSERT INTO extraction_cache(
              path, language, content_hash, cache_version, facts_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "src/Foo.java",
                "java",
                file_sha256(repo / "src" / "Foo.java"),
                EXTRACTION_CACHE_VERSION,
                "{not-json",
            ),
        )
    frontend = CountingFrontend()

    result = run_index(repo, db_path=db_path, frontends={"java": frontend})

    assert isinstance(result, IndexResult)
    assert frontend.calls == ["src/Foo.java"]
    assert result.stats["index.cache_hits"] == "0"
    assert result.stats["index.cache_misses"] == "1"


def test_run_index_rebuild_clears_extraction_cache(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    db_path = tmp_path / "graph.sqlite"

    run_index(repo, db_path=db_path, frontends={"java": CountingFrontend()})
    result = run_index(
        repo,
        db_path=db_path,
        rebuild=True,
        frontends={"java": CountingFrontend()},
    )

    assert isinstance(result, IndexResult)
    assert result.stats["index.cache_hits"] == "0"
    assert result.stats["index.cache_misses"] == "1"


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


class CountingFrontend:
    language = "java"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(self, file_path: str, source: bytes) -> ExtractedFacts:
        self.calls.append(file_path)
        name = Path(file_path).stem
        span = SourceSpan(
            file_path=file_path,
            start_byte=0,
            end_byte=len(source),
            start_line=1,
            start_col=0,
            end_line=1,
            end_col=len(source.rstrip(b"\n")),
        )
        symbol_key = f"java:{file_path}#{name}"
        return ExtractedFacts(
            nodes=[
                NodeFact(
                    kind="type",
                    language="java",
                    name=name,
                    qualified_name=name,
                    symbol_key=symbol_key,
                    file_path=file_path,
                    span=span,
                    confidence=1.0,
                    extractor="counting",
                )
            ],
            occurrences=[
                OccurrenceFact(
                    file_path=file_path,
                    role="definition",
                    text=name,
                    span=span,
                    node_key=symbol_key,
                    resolved_key=symbol_key,
                    confidence=1.0,
                    extractor="counting",
                )
            ],
            chunks=[
                ChunkFact(
                    file_path=file_path,
                    node_key=symbol_key,
                    kind="definition",
                    start_line=1,
                    end_line=1,
                    text=source.decode("utf-8"),
                    token_estimate=4,
                )
            ],
        )


class ReferenceFrontend(CountingFrontend):
    def extract(self, file_path: str, source: bytes) -> ExtractedFacts:
        facts = super().extract(file_path, source)
        if file_path.endswith("Service.java"):
            span = SourceSpan(
                file_path=file_path,
                start_byte=0,
                end_byte=len(source),
                start_line=1,
                start_col=0,
                end_line=1,
                end_col=len(source.rstrip(b"\n")),
            )
            facts.edges.append(
                EdgeFact(
                    kind="uses_type",
                    src_key="java:src/Service.java#Service",
                    dst_key=None,
                    unresolved_src=None,
                    unresolved_dst="User",
                    file_path=file_path,
                    span=span,
                    confidence=1.0,
                    extractor="reference",
                )
            )
        return facts


class ExplodingFrontend:
    language = "java"

    def extract(self, file_path: str, source: bytes) -> ExtractedFacts:
        raise AssertionError(f"unexpected extraction for {file_path}")
