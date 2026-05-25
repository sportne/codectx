from __future__ import annotations

from pathlib import Path

from codectx.frontends.base import ExtractedFacts
from codectx.graph.store import GraphStore
from codectx.indexing import (
    HealthResult,
    IndexingError,
    IndexResult,
    default_db_path,
    default_frontends,
    read_health,
    remove_db_files,
    run_index,
)


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
    assert index_result.stats["language.java"] == "1"
    assert index_result.stats["language.cpp"] == "1"

    health_result = read_health(repo, db_path=db_path, include_integrity=True)

    assert isinstance(health_result, HealthResult)
    assert health_result.snapshot_id == index_result.snapshot_id
    assert health_result.stats == index_result.stats
    assert health_result.integrity == "ok"


def test_default_frontends_register_java_and_cpp() -> None:
    frontends = default_frontends()

    assert sorted(frontends) == ["cpp", "java"]
    assert frontends["cpp"].language == "cpp"
    assert frontends["java"].language == "java"


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
