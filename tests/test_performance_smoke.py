from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import pytest

from codectx.contexting import ContextResult, build_context
from codectx.indexing import IndexResult, run_index
from codectx.neighborhooding import NeighborhoodResult, build_neighborhood
from codectx.querying import SearchResult, SymbolSearchResult, search, search_symbols

T = TypeVar("T")


pytestmark = pytest.mark.skipif(
    os.environ.get("CODECTX_PERF_SMOKE") != "1",
    reason="set CODECTX_PERF_SMOKE=1 to run optional performance smoke tests",
)


def test_perf_smoke_indexes_synthetic_100_file_repo(tmp_path: Path) -> None:
    repo = _generate_synthetic_repo(tmp_path / "repo", java_files=50, cpp_files=50)
    db_path = tmp_path / "graph.sqlite"
    source_size = _directory_size(repo)

    started = time.perf_counter()
    result = run_index(repo, db_path=db_path)
    index_seconds = time.perf_counter() - started

    assert isinstance(result, IndexResult)
    assert result.stats["files"] == "100"
    assert int(result.stats["nodes"]) > 100
    assert int(result.stats["chunks"]) > 100
    assert db_path.exists()
    _print_metric("index_seconds", index_seconds)
    _print_metric("source_bytes", float(source_size))
    _print_metric("db_bytes", float(db_path.stat().st_size))
    _print_metric("db_source_size_ratio", db_path.stat().st_size / source_size)


def test_perf_smoke_runs_representative_queries(tmp_path: Path) -> None:
    repo = _generate_synthetic_repo(tmp_path / "repo", java_files=50, cpp_files=50)
    db_path = tmp_path / "graph.sqlite"
    result = run_index(repo, db_path=db_path)
    assert isinstance(result, IndexResult)

    symbol_result, symbol_seconds = _timed(
        lambda: search_symbols(repo, "JavaService025", db_path=db_path)
    )
    search_result, search_seconds = _timed(
        lambda: search(repo, "authorize25", db_path=db_path)
    )
    context_result, context_seconds = _timed(
        lambda: build_context(
            repo,
            db_path=db_path,
            symbol="JavaService025.authorize25",
            output_format="json",
        )
    )
    neighborhood_result, neighborhood_seconds = _timed(
        lambda: build_neighborhood(
            repo,
            "JavaService025.authorize25",
            db_path=db_path,
            depth=1,
            direction="out",
            edge_kinds=("calls",),
            limit=10,
        )
    )

    assert isinstance(symbol_result, SymbolSearchResult)
    assert symbol_result.symbols
    assert isinstance(search_result, SearchResult)
    assert search_result.symbols or search_result.chunks
    assert isinstance(context_result, ContextResult)
    assert "JavaService025" in context_result.rendered_text
    assert isinstance(neighborhood_result, NeighborhoodResult)
    _print_metric("symbol_query_seconds", symbol_seconds)
    _print_metric("combined_search_seconds", search_seconds)
    _print_metric("context_seconds", context_seconds)
    _print_metric("neighborhood_seconds", neighborhood_seconds)


def _timed(operation: Callable[[], T]) -> tuple[T, float]:
    started = time.perf_counter()
    result = operation()
    return result, time.perf_counter() - started


def _generate_synthetic_repo(repo: Path, *, java_files: int, cpp_files: int) -> Path:
    for index in range(java_files):
        _write_java_file(repo, index)
    for index in range(cpp_files):
        _write_cpp_file(repo, index)
    return repo


def _write_java_file(repo: Path, index: int) -> None:
    class_name = f"JavaService{index:03d}"
    dependency_name = f"JavaDependency{index:03d}"
    source = (
        "package perf;\n"
        "import java.util.Objects;\n"
        f"public class {class_name} {{\n"
        f"  private final {dependency_name} dependency = new {dependency_name}();\n"
        f"  public boolean authorize{index}(String user) {{\n"
        "    validate(user);\n"
        f"    return dependency.charge{index}(user);\n"
        "  }\n"
        "  private void validate(String user) {\n"
        '    Objects.requireNonNull(user, "user");\n'
        "  }\n"
        "}\n"
        f"class {dependency_name} {{\n"
        f"  boolean charge{index}(String user) {{ return user.length() > 0; }}\n"
        "}\n"
    )
    _write(repo / "src" / "main" / "java" / "perf" / f"{class_name}.java", source)


def _write_cpp_file(repo: Path, index: int) -> None:
    class_name = f"CppService{index:03d}"
    source = (
        "#include <string>\n"
        "namespace perf {\n"
        f"class {class_name} {{\n"
        " public:\n"
        f"  bool authorize{index}(const std::string& user) {{\n"
        "    return validate(user);\n"
        "  }\n"
        " private:\n"
        "  bool validate(const std::string& user) {\n"
        "    return !user.empty();\n"
        "  }\n"
        "};\n"
        "}\n"
    )
    _write(repo / "src" / "main" / "cpp" / "perf" / f"{class_name}.cpp", source)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _directory_size(path: Path) -> int:
    return sum(
        file_path.stat().st_size for file_path in path.rglob("*") if file_path.is_file()
    )


def _print_metric(name: str, value: float) -> None:
    print(f"perf.{name}: {value:.6f}")
