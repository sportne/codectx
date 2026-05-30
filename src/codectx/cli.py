"""Command-line interface for codectx."""

from __future__ import annotations

import argparse
from json import dumps
from pathlib import Path

from codectx import __version__
from codectx.contexting import ContextingError as ContextServiceError
from codectx.contexting import ContextResult, build_context
from codectx.graph.query import EdgeEndpoint
from codectx.indexing import (
    HealthResult,
    IndexingError,
    IndexResult,
    read_health,
    run_index,
)
from codectx.neighborhooding import (
    NeighborhoodError,
    NeighborhoodResult,
    build_neighborhood,
)
from codectx.querying import (
    EdgeInspectionResult,
    NodeInspectionResult,
    SearchResult,
    SymbolSearchResult,
    inspect_edge,
    inspect_node,
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
    p_index.add_argument(
        "--include",
        action="append",
        default=None,
        metavar="PATTERN",
        help="Only index supported source files matching this gitwildmatch pattern. Can be repeated.",
    )
    p_index.add_argument(
        "--exclude",
        action="append",
        default=None,
        metavar="PATTERN",
        help="Exclude supported source files matching this gitwildmatch pattern. Can be repeated.",
    )
    p_index.add_argument(
        "--force-include",
        action="append",
        default=None,
        metavar="PATTERN",
        help="Include supported source files matching this pattern even when excluded or ignored. Can be repeated.",
    )
    p_index.add_argument(
        "--no-ignore-files",
        action="store_true",
        help="Do not apply .gitignore or .ignore files while scanning.",
    )

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
    p_neighborhood.add_argument(
        "--direction", choices=["out", "in", "both"], default="out"
    )
    p_neighborhood.add_argument(
        "--edge-kind",
        action="append",
        default=None,
        help="Restrict traversal to an edge kind. Can be repeated.",
    )
    p_neighborhood.add_argument("--limit", type=int, default=50)

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
    if args.command == "inspect-node":
        return _run_inspect_node(args)
    if args.command == "inspect-edge":
        return _run_inspect_edge(args)
    if args.command == "context":
        return _run_context(args)
    if args.command == "neighborhood":
        return _run_neighborhood(args)

    raise AssertionError(f"unhandled command: {args.command}")


def _run_index(args: argparse.Namespace) -> int:
    result = run_index(
        args.repo,
        db_path=args.db,
        rebuild=args.rebuild,
        include_patterns=tuple(args.include or ()),
        exclude_patterns=tuple(args.exclude or ()),
        force_include_patterns=tuple(args.force_include or ()),
        use_ignore_files=not args.no_ignore_files,
    )
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
    if args.integrity and result.integrity != "ok":
        return 1
    return 0


def _run_neighborhood(args: argparse.Namespace) -> int:
    result = build_neighborhood(
        args.repo,
        args.symbol,
        db_path=args.db,
        depth=args.depth,
        direction=args.direction,
        edge_kinds=tuple(args.edge_kind) if args.edge_kind else None,
        limit=args.limit,
    )
    if isinstance(result, NeighborhoodError):
        print(result.message)
        return 1

    _print_neighborhood_result(result)
    return 0


def _run_context(args: argparse.Namespace) -> int:
    result = build_context(
        args.repo,
        db_path=args.db,
        symbol=args.symbol,
        file_path=args.file,
        line=args.line,
        goal=args.goal,
        budget=args.budget,
        output_format=args.format,
        output_path=args.output,
    )
    if isinstance(result, ContextServiceError):
        print(result.message)
        return 1

    _print_context_result(result)
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


def _run_inspect_node(args: argparse.Namespace) -> int:
    result = inspect_node(args.repo, args.node_id, db_path=args.db)
    if isinstance(result, QueryServiceError):
        print(result.message)
        return 1

    _print_node_inspection_result(result)
    return 0


def _run_inspect_edge(args: argparse.Namespace) -> int:
    result = inspect_edge(args.repo, args.edge_id, db_path=args.db)
    if isinstance(result, QueryServiceError):
        print(result.message)
        return 1

    _print_edge_inspection_result(result)
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
    if result.integrity_details is not None:
        for key, value in sorted(result.integrity_details.items()):
            print(f"integrity.{key}: {value}")
    _print_stats(result.stats)


def _print_stats(stats: dict[str, str]) -> None:
    for key, value in sorted(stats.items()):
        print(f"{key}: {value}")


def _print_neighborhood_result(result: NeighborhoodResult) -> None:
    print(f"Neighborhood for {result.symbol}:")
    print(f"seed_node_id: {result.seed_node_id}")
    print("nodes:")
    for node in result.nodes:
        label = node.qualified_name or node.name or node.symbol_key or "<unnamed>"
        location = _format_location(node.file_path, node.start_line, node.end_line)
        language = f" {node.language}" if node.language else ""
        print(
            f"- depth={node.depth} id={node.node_id} "
            f"{node.kind}{language} {label} {location} "
            f"confidence={node.confidence:g} extractor={node.extractor}"
        )
    print("edges:")
    if not result.edges:
        print("- none")
    for edge in result.edges:
        location = _format_location(edge.file_path, edge.start_line, edge.end_line)
        print(
            f"- depth={edge.depth} id={edge.edge_id} kind={edge.kind} "
            f"src={_format_optional_id(edge.src_node_id)} "
            f"dst={_format_optional_id(edge.dst_node_id)} "
            f"unresolved_src={_format_optional(edge.unresolved_src)} "
            f"unresolved_dst={_format_optional(edge.unresolved_dst)} "
            f"{location} confidence={edge.confidence:g} "
            f"weight={edge.weight:g} extractor={edge.extractor}"
        )


def _print_context_result(result: ContextResult) -> None:
    if result.output_path is None:
        print(result.rendered_text)
        return
    result.output_path.write_text(result.rendered_text, encoding="utf-8")
    print(f"Wrote context bundle to {result.output_path}")


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


def _print_node_inspection_result(result: NodeInspectionResult) -> None:
    node = result.node
    print(f"Node {node.node_id}")
    print(f"kind: {node.kind}")
    if node.language is not None:
        print(f"language: {node.language}")
    if node.name is not None:
        print(f"name: {node.name}")
    if node.qualified_name is not None:
        print(f"qualified_name: {node.qualified_name}")
    if node.symbol_key is not None:
        print(f"symbol_key: {node.symbol_key}")
    print(f"file: {_format_location(node.file_path, node.start_line, node.end_line)}")
    print(f"byte_span: {_format_byte_span(node.start_byte, node.end_byte)}")
    print(f"extractor: {node.extractor}")
    print(f"confidence: {node.confidence:g}")
    print(f"metadata: {_format_metadata(node.metadata)}")


def _print_edge_inspection_result(result: EdgeInspectionResult) -> None:
    edge = result.edge
    print(f"Edge {edge.edge_id}")
    print(f"kind: {edge.kind}")
    print(f"source: {_format_endpoint(edge.source)}")
    print(f"destination: {_format_endpoint(edge.destination)}")
    print(f"unresolved_src: {_format_optional(edge.unresolved_src)}")
    print(f"unresolved_dst: {_format_optional(edge.unresolved_dst)}")
    print(f"file: {_format_location(edge.file_path, edge.start_line, edge.end_line)}")
    print(f"byte_span: {_format_byte_span(edge.start_byte, edge.end_byte)}")
    print(f"extractor: {edge.extractor}")
    print(f"confidence: {edge.confidence:g}")
    print(f"weight: {edge.weight:g}")
    print(f"metadata: {_format_metadata(edge.metadata)}")


def _format_endpoint(endpoint: EdgeEndpoint | None) -> str:
    if endpoint is None:
        return "<none>"

    node_id = endpoint.node_id
    kind = endpoint.kind
    name = endpoint.qualified_name or endpoint.name
    symbol_key = endpoint.symbol_key
    label = name or symbol_key or "<unnamed>"
    return f"id={node_id} {kind} {label}"


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


def _format_byte_span(start_byte: int | None, end_byte: int | None) -> str:
    if start_byte is None or end_byte is None:
        return "<unknown>"
    return f"{start_byte}-{end_byte}"


def _format_optional(value: str | None) -> str:
    return "<none>" if value is None else value


def _format_optional_id(value: int | None) -> str:
    return "<none>" if value is None else str(value)


def _format_metadata(metadata: dict[str, object]) -> str:
    return dumps(metadata, sort_keys=True, separators=(",", ":"))


if __name__ == "__main__":
    raise SystemExit(main())
