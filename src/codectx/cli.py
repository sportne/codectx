"""Command-line interface for codectx."""

from __future__ import annotations

import argparse
from pathlib import Path

from codectx import __version__
from codectx.indexing import (
    HealthResult,
    IndexingError,
    IndexResult,
    read_health,
    run_index,
)
from codectx.querying import (
    PlaceholderResult,
    SearchResult,
    SymbolSearchResult,
    placeholder_result,
    search,
    search_symbols,
)
from codectx.querying import QueryingError as QueryServiceError


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command parser."""
    parser = argparse.ArgumentParser(
        prog="codectx",
        description="Local code graph and context bundle generator for manual LLM use.",
    )
    parser.add_argument("--version", action="version", version=f"codectx {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Index a local repository.")
    p_index.add_argument("repo", type=Path)
    p_index.add_argument("--db", type=Path, default=None)
    p_index.add_argument("--rebuild", action="store_true")

    p_health = sub.add_parser("health", help="Show index health information.")
    p_health.add_argument("--repo", type=Path, default=Path.cwd())
    p_health.add_argument("--db", type=Path, default=None)
    p_health.add_argument("--integrity", action="store_true")

    p_search = sub.add_parser("search", help="Search indexed symbols and chunks.")
    p_search.add_argument("query")
    p_search.add_argument("--repo", type=Path, default=Path.cwd())
    p_search.add_argument("--db", type=Path, default=None)

    p_symbols = sub.add_parser("symbols", help="Search indexed symbols.")
    p_symbols.add_argument("query")
    p_symbols.add_argument("--repo", type=Path, default=Path.cwd())
    p_symbols.add_argument("--db", type=Path, default=None)

    p_context = sub.add_parser("context", help="Generate a ranked context bundle.")
    p_context.add_argument("--repo", type=Path, default=Path.cwd())
    p_context.add_argument("--db", type=Path, default=None)
    anchor = p_context.add_mutually_exclusive_group(required=True)
    anchor.add_argument("--symbol")
    anchor.add_argument("--file", type=Path)
    p_context.add_argument("--line", type=int, default=None)
    p_context.add_argument(
        "--goal",
        choices=["explain", "failure-modes", "dependencies", "call-neighborhood"],
        default="explain",
    )
    p_context.add_argument("--budget", type=int, default=8000)
    p_context.add_argument(
        "--format", choices=["markdown", "json", "text"], default="markdown"
    )
    p_context.add_argument("--output", type=Path, default=None)

    p_neighborhood = sub.add_parser(
        "neighborhood", help="Show a bounded graph neighborhood."
    )
    p_neighborhood.add_argument("--repo", type=Path, default=Path.cwd())
    p_neighborhood.add_argument("--db", type=Path, default=None)
    p_neighborhood.add_argument("--symbol", required=True)
    p_neighborhood.add_argument("--depth", type=int, default=1)

    p_node = sub.add_parser("inspect-node", help="Inspect a graph node by id.")
    p_node.add_argument("node_id", type=int)
    p_node.add_argument("--repo", type=Path, default=Path.cwd())
    p_node.add_argument("--db", type=Path, default=None)

    p_edge = sub.add_parser("inspect-edge", help="Inspect a graph edge by id.")
    p_edge.add_argument("edge_id", type=int)
    p_edge.add_argument("--repo", type=Path, default=Path.cwd())
    p_edge.add_argument("--db", type=Path, default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the codectx command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "index":
        return _run_index(args)
    if args.command == "health":
        return _run_health(args)
    if args.command == "symbols":
        return _run_symbols(args)
    if args.command == "search":
        return _run_search(args)
    if args.command in {
        "context",
        "inspect-edge",
        "inspect-node",
        "neighborhood",
    }:
        return _run_query_placeholder(args)

    raise AssertionError(f"unhandled command: {args.command}")


def _run_index(args: argparse.Namespace) -> int:
    result = run_index(args.repo, db_path=args.db, rebuild=args.rebuild)
    if isinstance(result, IndexingError):
        print(result.message)
        return 1

    _print_index_result(result)
    return 0


def _run_health(args: argparse.Namespace) -> int:
    result = read_health(args.repo, db_path=args.db, include_integrity=args.integrity)
    if isinstance(result, IndexingError):
        print(result.message)
        return 1

    _print_health_result(result)
    return 0


def _run_query_placeholder(args: argparse.Namespace) -> int:
    result = placeholder_result(args.command)
    _print_placeholder_result(result)
    return 0


def _run_symbols(args: argparse.Namespace) -> int:
    result = search_symbols(args.repo, args.query, db_path=args.db)
    if isinstance(result, QueryServiceError):
        print(result.message)
        return 1

    _print_symbol_search_result(result)
    return 0


def _run_search(args: argparse.Namespace) -> int:
    result = search(args.repo, args.query, db_path=args.db)
    if isinstance(result, QueryServiceError):
        print(result.message)
        return 1

    _print_search_result(result)
    return 0


def _print_index_result(result: IndexResult) -> None:
    print(f"Indexed {result.repo}")
    print(f"database: {result.db_path}")
    print(f"snapshot_id: {result.snapshot_id}")
    _print_stats(result.stats)


def _print_health_result(result: HealthResult) -> None:
    print(f"Index health for {result.repo}")
    print(f"database: {result.db_path}")
    print(f"snapshot_id: {result.snapshot_id}")
    if result.integrity is not None:
        print(f"integrity: {result.integrity}")
    _print_stats(result.stats)


def _print_stats(stats: dict[str, str]) -> None:
    for key, value in sorted(stats.items()):
        print(f"{key}: {value}")


def _print_placeholder_result(result: PlaceholderResult) -> None:
    print(result.message)


def _print_symbol_search_result(result: SymbolSearchResult) -> None:
    if not result.symbols:
        print(f"No symbols found for {result.query}.")
        return

    print(f"Symbols for {result.query}:")
    for symbol in result.symbols:
        location = _format_location(
            symbol.file_path, symbol.start_line, symbol.end_line
        )
        label = symbol.qualified_name or symbol.name or symbol.symbol_key or "<unnamed>"
        language = f" {symbol.language}" if symbol.language else ""
        print(
            f"- id={symbol.node_id} score={symbol.score} "
            f"{symbol.kind}{language} {label} {location}"
        )


def _print_search_result(result: SearchResult) -> None:
    if not result.symbols and not result.chunks:
        print(f"No results found for {result.query}.")
        return

    mode = "fts" if result.used_fts else "like"
    print(f"Search results for {result.query} ({mode}):")
    if result.symbols:
        print("symbols:")
        for symbol in result.symbols:
            location = _format_location(
                symbol.file_path, symbol.start_line, symbol.end_line
            )
            label = (
                symbol.qualified_name or symbol.name or symbol.symbol_key or "<unnamed>"
            )
            language = f" {symbol.language}" if symbol.language else ""
            print(
                f"- id={symbol.node_id} score={symbol.score} "
                f"{symbol.kind}{language} {label} {location}"
            )
    if result.chunks:
        print("chunks:")
        for chunk in result.chunks:
            location = _format_location(
                chunk.file_path, chunk.start_line, chunk.end_line
            )
            print(
                f"- id={chunk.chunk_id} score={chunk.score} "
                f"{chunk.kind} {location} tokens={chunk.token_estimate}"
            )


def _format_location(
    file_path: str | None, start_line: int | None, end_line: int | None
) -> str:
    if file_path is None:
        return "<unknown>"
    if start_line is None:
        return file_path
    if end_line is None or end_line == start_line:
        return f"{file_path}:{start_line}"
    return f"{file_path}:{start_line}-{end_line}"


if __name__ == "__main__":
    raise SystemExit(main())
