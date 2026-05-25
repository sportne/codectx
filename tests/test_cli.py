from __future__ import annotations

from pathlib import Path

import pytest

from codectx.cli import build_parser, main
from codectx.graph.store import GraphStore


def test_parser_accepts_all_initial_commands() -> None:
    parser = build_parser()

    assert parser.parse_args(["index", "."]).command == "index"
    assert parser.parse_args(["health"]).command == "health"
    assert parser.parse_args(["search", "PaymentService"]).command == "search"
    assert parser.parse_args(["symbols", "PaymentService"]).command == "symbols"
    assert (
        parser.parse_args(["context", "--symbol", "PaymentService.authorize"]).command
        == "context"
    )
    assert (
        parser.parse_args(["neighborhood", "--symbol", "PaymentService"]).command
        == "neighborhood"
    )
    assert parser.parse_args(["inspect-node", "123"]).command == "inspect-node"
    assert parser.parse_args(["inspect-edge", "456"]).command == "inspect-edge"


def test_parser_version_exits_with_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])

    assert exc_info.value.code == 0
    assert "codectx 0.0.1" in capsys.readouterr().out


def test_main_reports_defined_but_unimplemented_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["search", "PaymentService"]) == 0

    output = capsys.readouterr().out
    assert "codectx command 'search' is defined but not implemented yet." in output
    assert "docs/04-task-decomposition.md" in output


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
    assert "files: 2" in health_output


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


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
