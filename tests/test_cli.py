from __future__ import annotations

from pathlib import Path

import pytest

from codectx.cli import build_parser, main
from codectx.contexting import ContextResult
from codectx.frontends.base import EdgeFact, NodeFact
from codectx.graph.store import GraphStore
from codectx.graph.traversal import NeighborhoodEdge, NeighborhoodNode
from codectx.indexing import IndexResult
from codectx.neighborhooding import NeighborhoodResult
from codectx.scanner.models import FileRecord
from codectx.source.spans import SourceSpan


def test_parser_accepts_all_initial_commands() -> None:
    parser = build_parser()

    assert parser.parse_args(["index", "."]).command == "index"
    index_args = parser.parse_args(
        [
            "index",
            ".",
            "--include",
            "src/**",
            "--exclude",
            "vendor/**",
            "--force-include",
            "vendor/needed.cpp",
            "--no-ignore-files",
        ]
    )
    assert index_args.include == ["src/**"]
    assert index_args.exclude == ["vendor/**"]
    assert index_args.force_include == ["vendor/needed.cpp"]
    assert index_args.no_ignore_files is True
    assert parser.parse_args(["health"]).command == "health"
    assert parser.parse_args(["search", "PaymentService"]).command == "search"
    assert parser.parse_args(["symbols", "PaymentService"]).command == "symbols"
    assert (
        parser.parse_args(["context", "--symbol", "PaymentService.authorize"]).command
        == "context"
    )
    assert (
        parser.parse_args(
            [
                "neighborhood",
                "--symbol",
                "PaymentService",
                "--direction",
                "both",
                "--edge-kind",
                "calls",
                "--limit",
                "5",
            ]
        ).command
        == "neighborhood"
    )
    assert parser.parse_args(["inspect-node", "123"]).command == "inspect-node"
    assert parser.parse_args(["inspect-edge", "456"]).command == "inspect-edge"


def test_index_command_delegates_scan_filter_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    captured = {}
    db_path = tmp_path / "graph.sqlite"

    def fake_run_index(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return IndexResult(
            repo=tmp_path.resolve(),
            db_path=db_path,
            snapshot_id=1,
            stats={"files": "0"},
        )

    monkeypatch.setattr("codectx.cli.run_index", fake_run_index)

    assert (
        main(
            [
                "index",
                str(tmp_path),
                "--db",
                str(db_path),
                "--rebuild",
                "--include",
                "src/**",
                "--include",
                "include/**",
                "--exclude",
                "vendor/**",
                "--force-include",
                "vendor/needed.cpp",
                "--no-ignore-files",
            ]
        )
        == 0
    )

    assert "files: 0" in capsys.readouterr().out
    assert captured == {
        "args": (tmp_path,),
        "kwargs": {
            "db_path": db_path,
            "rebuild": True,
            "include_patterns": ("src/**", "include/**"),
            "exclude_patterns": ("vendor/**",),
            "force_include_patterns": ("vendor/needed.cpp",),
            "use_ignore_files": False,
        },
    }


def test_parser_version_exits_with_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])

    assert exc_info.value.code == 0
    assert "codectx 0.2.0" in capsys.readouterr().out


def test_neighborhood_command_delegates_to_neighborhood_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    captured = {}

    def fake_build_neighborhood(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return NeighborhoodResult(
            repo=tmp_path,
            db_path=tmp_path / "graph.sqlite",
            snapshot_id=1,
            symbol="PaymentService",
            seed_node_id=10,
            nodes=[
                NeighborhoodNode(
                    node_id=10,
                    depth=0,
                    kind="callable",
                    language="java",
                    name="authorize",
                    qualified_name="PaymentService.authorize",
                    symbol_key="java:src/PaymentService.java#PaymentService.authorize()",
                    file_path="src/PaymentService.java",
                    start_line=3,
                    end_line=5,
                    confidence=1.0,
                    extractor="test",
                )
            ],
            edges=[
                NeighborhoodEdge(
                    edge_id=20,
                    depth=1,
                    kind="calls",
                    src_node_id=10,
                    dst_node_id=None,
                    unresolved_src=None,
                    unresolved_dst="gateway.charge",
                    file_path="src/PaymentService.java",
                    start_line=4,
                    end_line=4,
                    confidence=0.45,
                    weight=1.0,
                    extractor="test",
                )
            ],
        )

    monkeypatch.setattr("codectx.cli.build_neighborhood", fake_build_neighborhood)

    assert (
        main(
            [
                "neighborhood",
                "--symbol",
                "PaymentService",
                "--repo",
                str(tmp_path),
                "--depth",
                "2",
                "--direction",
                "both",
                "--edge-kind",
                "calls",
                "--limit",
                "5",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "Neighborhood for PaymentService:" in output
    assert "seed_node_id: 10" in output
    assert "PaymentService.authorize src/PaymentService.java:3-5" in output
    assert "unresolved_dst=gateway.charge" in output
    assert captured == {
        "args": (tmp_path, "PaymentService"),
        "kwargs": {
            "db_path": None,
            "depth": 2,
            "direction": "both",
            "edge_kinds": ("calls",),
            "limit": 5,
        },
    }


def test_context_command_delegates_to_context_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_build_context(*_args, **_kwargs):
        return ContextResult(rendered_text="context service result")

    monkeypatch.setattr("codectx.cli.build_context", fake_build_context)

    assert main(["context", "--symbol", "PaymentService", "--repo", str(tmp_path)]) == 0

    assert capsys.readouterr().out == "context service result\n"


def test_context_command_writes_service_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_path = tmp_path / "context.md"

    def fake_build_context(*_args, **_kwargs):
        return ContextResult(
            rendered_text="context service result",
            output_path=output_path,
        )

    monkeypatch.setattr("codectx.cli.build_context", fake_build_context)

    assert (
        main(
            [
                "context",
                "--symbol",
                "PaymentService",
                "--repo",
                str(tmp_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    assert output_path.read_text(encoding="utf-8") == "context service result"
    assert f"Wrote context bundle to {output_path}" in capsys.readouterr().out


def test_context_command_reports_invalid_anchor_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["context", "--file", "src/Foo.java", "--repo", str(tmp_path)]) == 1
    assert "--line is required" in capsys.readouterr().out

    assert (
        main(
            [
                "context",
                "--file",
                "src/Foo.java",
                "--line",
                "0",
                "--repo",
                str(tmp_path),
            ]
        )
        == 1
    )
    assert "Line number must be 1 or greater" in capsys.readouterr().out

    assert (
        main(
            [
                "context",
                "--symbol",
                "PaymentService",
                "--line",
                "10",
                "--repo",
                str(tmp_path),
            ]
        )
        == 1
    )
    assert "--line can only be used with --file" in capsys.readouterr().out


def test_context_command_generates_markdown_for_file_line_anchor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "Foo.java",
        "class Foo {\n  void run() { helper(); }\n  void helper() {}\n}\n",
    )
    db_path = tmp_path / "graph.sqlite"
    assert main(["index", str(repo), "--db", str(db_path)]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "context",
                "--file",
                "src/Foo.java",
                "--line",
                "2",
                "--repo",
                str(repo),
                "--db",
                str(db_path),
                "--format",
                "markdown",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "# codectx context bundle" in output
    assert "target.definition" in output
    assert "overlap" in output
    assert "src/Foo.java:2" in output


def test_context_command_generates_json_text_and_output_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "Foo.java", "class Foo { void run() {} }\n")
    db_path = tmp_path / "graph.sqlite"
    assert main(["index", str(repo), "--db", str(db_path)]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "context",
                "--symbol",
                "Foo",
                "--repo",
                str(repo),
                "--db",
                str(db_path),
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert '"goal": "explain"' in capsys.readouterr().out

    output_path = tmp_path / "context.txt"
    assert (
        main(
            [
                "context",
                "--symbol",
                "Foo",
                "--repo",
                str(repo),
                "--db",
                str(db_path),
                "--format",
                "text",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    assert output_path.read_text(encoding="utf-8").startswith(
        "codectx context bundle\n"
    )
    assert f"Wrote context bundle to {output_path.resolve()}" in capsys.readouterr().out


def test_context_command_reports_missing_index_no_symbol_and_routes_extra_goals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert (
        main(
            [
                "context",
                "--symbol",
                "Foo",
                "--repo",
                str(repo),
                "--db",
                str(tmp_path / "missing.sqlite"),
            ]
        )
        == 1
    )
    assert "No codectx index found" in capsys.readouterr().out

    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    db_path = tmp_path / "graph.sqlite"
    assert main(["index", str(repo), "--db", str(db_path)]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "context",
                "--symbol",
                "Missing",
                "--repo",
                str(repo),
                "--db",
                str(db_path),
            ]
        )
        == 1
    )
    assert "No symbols found for Missing" in capsys.readouterr().out

    assert (
        main(
            [
                "context",
                "--symbol",
                "Foo",
                "--repo",
                str(repo),
                "--db",
                str(db_path),
                "--goal",
                "dependencies",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "# codectx context bundle" in output
    assert "- goal: dependencies" in output


def test_context_command_generates_failure_modes_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "PaymentService.java",
        (
            "class PaymentService {\n"
            "  boolean authorize() {\n"
            "    return validatePayment() && helper();\n"
            "  }\n"
            "  boolean validatePayment() { throw new IllegalStateException(); }\n"
            "  boolean helper() { return true; }\n"
            "}\n"
        ),
    )
    _write(
        repo / "test" / "PaymentServiceFailureTest.java",
        (
            "class PaymentServiceFailureTest {\n"
            "  void authorize_failsInvalidPayment() {\n"
            "    new PaymentService().authorize();\n"
            "  }\n"
            "}\n"
        ),
    )
    db_path = tmp_path / "graph.sqlite"
    assert main(["index", str(repo), "--db", str(db_path)]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "context",
                "--symbol",
                "authorize",
                "--repo",
                str(repo),
                "--db",
                str(db_path),
                "--goal",
                "failure-modes",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "- goal: failure-modes" in output
    assert "validatePayment" in output
    assert "PaymentServiceFailureTest" in output


def test_context_command_generates_dependencies_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "PaymentService.java",
        (
            "import java.util.List;\n"
            "class PaymentService {\n"
            "  private Gateway gateway;\n"
            "  boolean authorize() {\n"
            "    return gateway.ready() && validate();\n"
            "  }\n"
            "  boolean validate() { return true; }\n"
            "}\n"
        ),
    )
    _write(repo / "src" / "Gateway.java", "class Gateway {}\n")
    db_path = tmp_path / "graph.sqlite"
    assert main(["index", str(repo), "--db", str(db_path)]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "context",
                "--symbol",
                "authorize",
                "--repo",
                str(repo),
                "--db",
                str(db_path),
                "--goal",
                "dependencies",
                "--format",
                "text",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "- goal: dependencies" in output
    assert "import java.util.List;" in output
    assert "Gateway" in output


def test_context_command_generates_call_neighborhood_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "Foo.java",
        (
            "class Foo {\n"
            "  void controller() { target(); }\n"
            "  void target() {\n"
            "    validate();\n"
            "    externalGateway.charge();\n"
            "  }\n"
            "  void validate() {}\n"
            "}\n"
        ),
    )
    db_path = tmp_path / "graph.sqlite"
    assert main(["index", str(repo), "--db", str(db_path)]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "context",
                "--symbol",
                "target",
                "--repo",
                str(repo),
                "--db",
                str(db_path),
                "--goal",
                "call-neighborhood",
                "--format",
                "json",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert '"goal": "call-neighborhood"' in output
    assert "neighborhood.callee" in output
    assert "neighborhood.caller" in output
    assert "externalGateway.charge" in output


def test_index_and_health_commands_persist_and_display_stats(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    _write(repo / "src" / "native.cpp", "int main() {}\n")
    db_path = tmp_path / "graph.sqlite"

    assert main(["index", str(repo), "--db", str(db_path)]) == 0
    index_output = capsys.readouterr().out
    assert db_path.exists()
    assert f"Indexed {repo.resolve()}" in index_output
    assert "files: 2" in index_output
    assert "language.cpp: 1" in index_output
    assert "language.java: 1" in index_output

    assert (
        main(["health", "--repo", str(repo), "--db", str(db_path), "--integrity"]) == 0
    )
    health_output = capsys.readouterr().out
    assert f"Index health for {repo.resolve()}" in health_output
    assert "integrity: ok" in health_output
    assert "integrity.sqlite: ok" in health_output
    assert "integrity.foreign_keys: ok" in health_output
    assert "files: 2" in health_output


def test_health_integrity_failure_returns_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = tmp_path / "graph.sqlite"
    file_record = FileRecord(
        path="src/Foo.java",
        language="java",
        content_hash="abc123",
        size_bytes=12,
        line_count=1,
    )
    with GraphStore(db_path) as store:
        store.apply_schema()
        repo_id = store.create_repo(repo)
        snapshot_id = store.create_snapshot(repo_id)
        store.insert_files(snapshot_id, [file_record])
        store.upsert_index_stats(snapshot_id, {"files": "1"})
        store.conn.execute("PRAGMA ignore_check_constraints = ON")
        store.conn.execute(
            """
            INSERT INTO edge(snapshot_id, kind, confidence, weight, extractor)
            VALUES (?, 'calls', 1.0, 1.0, 'test')
            """,
            (snapshot_id,),
        )
        store.conn.commit()

    assert (
        main(["health", "--repo", str(repo), "--db", str(db_path), "--integrity"]) == 1
    )

    output = capsys.readouterr().out
    assert "integrity: failed" in output
    assert "integrity.unresolved_edges: failed (1)" in output
    assert "integrity.problem." in output
    assert "edge" in output


def test_index_uses_default_db_path_and_rebuild_removes_existing_sidecars(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    default_db = repo / ".codectx" / "graph.sqlite"
    default_db.parent.mkdir(parents=True)
    default_db.write_text("not sqlite", encoding="utf-8")
    Path(f"{default_db}-wal").write_text("wal", encoding="utf-8")
    Path(f"{default_db}-shm").write_text("shm", encoding="utf-8")

    assert main(["index", str(repo), "--rebuild"]) == 0

    output = capsys.readouterr().out
    assert f"database: {default_db}" in output
    assert "files: 1" in output
    assert not Path(f"{default_db}-wal").exists()
    assert not Path(f"{default_db}-shm").exists()

    assert main(["health", "--repo", str(repo)]) == 0
    health_output = capsys.readouterr().out
    assert "Index health" in health_output
    assert "integrity:" not in health_output


def test_index_reports_invalid_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing_repo = tmp_path / "missing"

    assert main(["index", str(missing_repo)]) == 1

    output = capsys.readouterr().out
    assert "Repository path does not exist" in output


def test_health_reports_missing_index(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = tmp_path / "missing.sqlite"

    assert main(["health", "--repo", str(repo), "--db", str(db_path)]) == 1

    output = capsys.readouterr().out
    assert "No codectx index found" in output
    assert "codectx index" in output


def test_health_reports_db_without_repo_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = tmp_path / "empty.sqlite"
    with GraphStore(db_path) as store:
        store.apply_schema()

    assert main(["health", "--repo", str(repo), "--db", str(db_path)]) == 1

    output = capsys.readouterr().out
    assert "No codectx index found for" in output


def test_health_reports_snapshot_without_stats(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = tmp_path / "incomplete.sqlite"
    with GraphStore(db_path) as store:
        store.apply_schema()
        repo_id = store.create_repo(repo)
        store.create_snapshot(repo_id)

    assert main(["health", "--repo", str(repo), "--db", str(db_path)]) == 1

    output = capsys.readouterr().out
    assert "No index health stats found" in output
    assert "--rebuild" in output


def test_symbols_command_displays_symbol_matches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "PaymentService.java",
        "package acme;\nclass PaymentService { void authorize() {} }\n",
    )
    db_path = tmp_path / "graph.sqlite"
    assert main(["index", str(repo), "--db", str(db_path)]) == 0
    capsys.readouterr()

    assert (
        main(["symbols", "PaymentService", "--repo", str(repo), "--db", str(db_path)])
        == 0
    )

    output = capsys.readouterr().out
    assert "Symbols for PaymentService:" in output
    assert "type java acme.PaymentService src/PaymentService.java:2" in output
    assert "score=100" in output


def test_symbols_command_reports_no_matches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    db_path = tmp_path / "graph.sqlite"
    assert main(["index", str(repo), "--db", str(db_path)]) == 0
    capsys.readouterr()

    assert main(["symbols", "Missing", "--repo", str(repo), "--db", str(db_path)]) == 0

    output = capsys.readouterr().out
    assert "No symbols found for Missing." in output


def test_symbols_command_reports_missing_index(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    assert (
        main(
            [
                "symbols",
                "Foo",
                "--repo",
                str(repo),
                "--db",
                str(tmp_path / "missing.sqlite"),
            ]
        )
        == 1
    )

    output = capsys.readouterr().out
    assert "No codectx index found" in output
    assert "codectx index" in output


def test_search_command_displays_symbol_and_chunk_matches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "PaymentService.java",
        "package acme;\nclass PaymentService { void authorize() {} }\n",
    )
    db_path = tmp_path / "graph.sqlite"
    assert main(["index", str(repo), "--db", str(db_path)]) == 0
    capsys.readouterr()

    assert main(["search", "authorize", "--repo", str(repo), "--db", str(db_path)]) == 0

    output = capsys.readouterr().out
    assert "Search results for authorize" in output
    assert "symbols:" in output
    assert "chunks:" in output
    assert "acme.PaymentService.authorize()" in output
    assert "src/PaymentService.java" in output


def test_search_command_reports_no_matches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    db_path = tmp_path / "graph.sqlite"
    assert main(["index", str(repo), "--db", str(db_path)]) == 0
    capsys.readouterr()

    assert main(["search", "Missing", "--repo", str(repo), "--db", str(db_path)]) == 0

    output = capsys.readouterr().out
    assert "No results found for Missing." in output


def test_search_command_reports_missing_index(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    assert (
        main(
            [
                "search",
                "Foo",
                "--repo",
                str(repo),
                "--db",
                str(tmp_path / "missing.sqlite"),
            ]
        )
        == 1
    )

    output = capsys.readouterr().out
    assert "No codectx index found" in output
    assert "codectx index" in output


def test_inspect_node_command_displays_node_details(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        ids = _seed_inspection_graph(store, repo)

    assert (
        main(
            [
                "inspect-node",
                str(ids["node_id"]),
                "--repo",
                str(repo),
                "--db",
                str(db_path),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert f"Node {ids['node_id']}" in output
    assert "kind: type" in output
    assert "language: java" in output
    assert "qualified_name: acme.Foo" in output
    assert "file: src/Foo.java:1-3" in output
    assert 'metadata: {"visibility":"public"}' in output


def test_inspect_edge_command_displays_edge_details(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        ids = _seed_inspection_graph(store, repo)

    assert (
        main(
            [
                "inspect-edge",
                str(ids["edge_id"]),
                "--repo",
                str(repo),
                "--db",
                str(db_path),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert f"Edge {ids['edge_id']}" in output
    assert "kind: calls" in output
    assert "source: id=" in output
    assert "type acme.Foo" in output
    assert "destination: <none>" in output
    assert "unresolved_src: legacy source label" in output
    assert "unresolved_dst: acme.Missing" in output
    assert "file: src/Foo.java:1-3" in output
    assert "confidence: 0.8" in output
    assert "weight: 0.25" in output
    assert 'metadata: {"reason":"fixture"}' in output


def test_inspect_commands_report_missing_records(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        _seed_inspection_graph(store, repo)

    assert main(["inspect-node", "999", "--repo", str(repo), "--db", str(db_path)]) == 1
    assert "Node 999 was not found" in capsys.readouterr().out

    assert main(["inspect-edge", "999", "--repo", str(repo), "--db", str(db_path)]) == 1
    assert "Edge 999 was not found" in capsys.readouterr().out


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_inspection_graph(store: GraphStore, repo: Path) -> dict[str, int]:
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    file_ids = store.insert_files(
        snapshot_id,
        [
            FileRecord(
                path="src/Foo.java",
                language="java",
                content_hash="abc123",
                size_bytes=40,
                line_count=3,
            )
        ],
    )
    span = SourceSpan(
        file_path="src/Foo.java",
        start_byte=0,
        end_byte=20,
        start_line=1,
        start_col=0,
        end_line=3,
        end_col=1,
    )
    node_ids = store.insert_nodes(
        snapshot_id,
        [
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
            )
        ],
        file_ids,
    )
    edge_ids = store.insert_edges(
        snapshot_id,
        [
            EdgeFact(
                kind="calls",
                src_key="java:src/Foo.java#Foo",
                dst_key=None,
                unresolved_src="legacy source label",
                unresolved_dst="acme.Missing",
                file_path="src/Foo.java",
                span=span,
                confidence=0.8,
                extractor="test",
                weight=0.25,
                metadata={"reason": "fixture"},
            )
        ],
        file_ids,
        node_ids,
    )
    return {
        "node_id": node_ids["java:src/Foo.java#Foo"],
        "edge_id": edge_ids[0],
    }
