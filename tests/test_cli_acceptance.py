from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from codectx.cli import main
from codectx.graph.store import GraphStore

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    (
        "fixture_name",
        "symbol_query",
        "search_query",
        "neighborhood_query",
        "expected_files",
        "file_path",
    ),
    [
        (
            "java_basic",
            "authorize",
            "PaymentService",
            "authorize",
            4,
            "src/main/java/acme/PaymentService.java",
        ),
        (
            "cpp_basic",
            "authorize",
            "PaymentService",
            "PaymentService::authorize",
            4,
            "src/payment_service.cpp",
        ),
        (
            "python_basic",
            "authorize",
            "PaymentService",
            "PaymentService.authorize",
            4,
            "src/payments/service.py",
        ),
    ],
)
def test_cli_acceptance_commands_on_golden_fixtures(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    fixture_name: str,
    symbol_query: str,
    search_query: str,
    neighborhood_query: str,
    expected_files: int,
    file_path: str,
) -> None:
    repo = _copy_fixture(fixture_name, tmp_path)
    db_path = tmp_path / f"{fixture_name}.sqlite"

    assert main(["index", str(repo), "--db", str(db_path)]) == 0
    index_output = capsys.readouterr().out
    assert f"Indexed {repo.resolve()}" in index_output
    assert f"files: {expected_files}" in index_output

    assert (
        main(["health", "--repo", str(repo), "--db", str(db_path), "--integrity"]) == 0
    )
    health_output = capsys.readouterr().out
    assert "integrity: ok" in health_output
    assert "unresolved_references:" in health_output

    assert (
        main(["symbols", symbol_query, "--repo", str(repo), "--db", str(db_path)]) == 0
    )
    symbols_output = capsys.readouterr().out
    assert f"Symbols for {symbol_query}:" in symbols_output
    assert "authorize" in symbols_output

    assert (
        main(["search", search_query, "--repo", str(repo), "--db", str(db_path)]) == 0
    )
    search_output = capsys.readouterr().out
    assert f"Search results for {search_query}" in search_output
    assert "symbols:" in search_output

    assert (
        main(
            [
                "context",
                "--symbol",
                symbol_query,
                "--repo",
                str(repo),
                "--db",
                str(db_path),
                "--goal",
                "explain",
                "--format",
                "markdown",
            ]
        )
        == 0
    )
    context_output = capsys.readouterr().out
    assert "# codectx context bundle" in context_output
    assert "- goal: explain" in context_output

    assert (
        main(
            [
                "context",
                "--file",
                file_path,
                "--repo",
                str(repo),
                "--db",
                str(db_path),
                "--goal",
                "explain",
                "--format",
                "markdown",
            ]
        )
        == 0
    )
    file_context_output = capsys.readouterr().out
    assert "# codectx context bundle" in file_context_output
    assert "- anchor_kind: file" in file_context_output
    assert "- file: " + file_path in file_context_output

    assert (
        main(
            [
                "neighborhood",
                "--symbol",
                neighborhood_query,
                "--repo",
                str(repo),
                "--db",
                str(db_path),
                "--direction",
                "both",
                "--edge-kind",
                "calls",
            ]
        )
        == 0
    )
    neighborhood_output = capsys.readouterr().out
    assert f"Neighborhood for {neighborhood_query}:" in neighborhood_output
    assert "kind=calls" in neighborhood_output

    node_id, edge_id = _inspection_ids(db_path)
    assert (
        main(["inspect-node", str(node_id), "--repo", str(repo), "--db", str(db_path)])
        == 0
    )
    node_output = capsys.readouterr().out
    assert f"Node {node_id}" in node_output
    assert "metadata:" in node_output

    assert (
        main(["inspect-edge", str(edge_id), "--repo", str(repo), "--db", str(db_path)])
        == 0
    )
    edge_output = capsys.readouterr().out
    assert f"Edge {edge_id}" in edge_output
    assert "kind: calls" in edge_output


def _copy_fixture(name: str, tmp_path: Path) -> Path:
    source = FIXTURE_DIR / name
    destination = tmp_path / name
    shutil.copytree(source, destination)
    return destination


def _inspection_ids(db_path: Path) -> tuple[int, int]:
    with GraphStore(db_path) as store:
        node = store.conn.execute(
            """
            SELECT id
            FROM node
            WHERE kind = 'callable'
              AND name LIKE '%authorize%'
            ORDER BY file_id, start_line, id
            LIMIT 1
            """
        ).fetchone()
        edge = store.conn.execute(
            """
            SELECT id
            FROM edge
            WHERE kind = 'calls'
            ORDER BY start_line, id
            LIMIT 1
            """
        ).fetchone()
    assert node is not None
    assert edge is not None
    return int(node["id"]), int(edge["id"])
