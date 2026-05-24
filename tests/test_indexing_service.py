from __future__ import annotations

from pathlib import Path

from codectx.graph.store import GraphStore
from codectx.indexing import (
    HealthResult,
    IndexingError,
    IndexResult,
    default_db_path,
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
    assert index_result.stats["language.java"] == "1"
    assert index_result.stats["language.cpp"] == "1"

    health_result = read_health(repo, db_path=db_path, include_integrity=True)

    assert isinstance(health_result, HealthResult)
    assert health_result.snapshot_id == index_result.snapshot_id
    assert health_result.stats == index_result.stats
    assert health_result.integrity == "ok"


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
