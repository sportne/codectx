from __future__ import annotations

from pathlib import Path

from codectx.graph.store import GraphStore
from codectx.querying import (
    FileLineAnchorResult,
    PlaceholderResult,
    QueryContext,
    QueryingError,
    placeholder_result,
    resolve_anchor,
    resolve_query_context,
)


def test_resolve_query_context_returns_latest_snapshot(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        store.apply_schema()
        repo_id = store.create_repo(repo)
        first_snapshot_id = store.create_snapshot(repo_id)
        second_snapshot_id = store.create_snapshot(repo_id)

    result = resolve_query_context(repo, db_path=db_path)

    assert isinstance(result, QueryContext)
    assert result.repo == repo.resolve()
    assert result.db_path == db_path.resolve()
    assert first_snapshot_id < second_snapshot_id
    assert result.snapshot_id == second_snapshot_id


def test_resolve_query_context_reports_missing_index(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = resolve_query_context(repo, db_path=tmp_path / "missing.sqlite")

    assert isinstance(result, QueryingError)
    assert "No codectx index found" in result.message
    assert "codectx index" in result.message


def test_resolve_query_context_reports_db_without_repo_snapshot(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = tmp_path / "empty.sqlite"
    with GraphStore(db_path) as store:
        store.apply_schema()

    result = resolve_query_context(repo, db_path=db_path)

    assert isinstance(result, QueryingError)
    assert f"No codectx index found for {repo.resolve()}" in result.message


def test_placeholder_result_is_query_service_response() -> None:
    result = placeholder_result("symbols")

    assert isinstance(result, PlaceholderResult)
    assert "codectx command 'symbols' is defined but not implemented yet." in (
        result.message
    )
    assert "docs/04-task-decomposition.md" in result.message


def test_resolve_anchor_returns_file_line_anchor(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        store.apply_schema()
        repo_id = store.create_repo(repo)
        snapshot_id = store.create_snapshot(repo_id)
        store.insert_files(
            snapshot_id,
            [
                _file_record(
                    path="src/Foo.java",
                    line_count=3,
                )
            ],
        )

    result = resolve_anchor(repo, repo / "src" / "Foo.java", 1, db_path=db_path)

    assert isinstance(result, FileLineAnchorResult)
    assert result.anchor.file_path == "src/Foo.java"
    assert result.anchor.line == 1
    assert result.anchor.node_id is None


def test_resolve_anchor_reports_missing_index(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = resolve_anchor(
        repo, "src/Foo.java", 1, db_path=tmp_path / "missing.sqlite"
    )

    assert isinstance(result, QueryingError)
    assert "No codectx index found" in result.message


def test_resolve_anchor_reports_missing_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        store.apply_schema()
        repo_id = store.create_repo(repo)
        store.create_snapshot(repo_id)

    result = resolve_anchor(repo, "src/Missing.java", 1, db_path=db_path)

    assert isinstance(result, QueryingError)
    assert "File is not indexed" in result.message


def _file_record(path: str, line_count: int):
    from codectx.scanner.models import FileRecord

    return FileRecord(
        path=path,
        language="java",
        content_hash="abc123",
        size_bytes=10,
        line_count=line_count,
    )
