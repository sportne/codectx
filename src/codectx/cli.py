"""Command-line interface for codectx."""

from __future__ import annotations

import argparse
from pathlib import Path

from codectx import __version__


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

    # Implementation tasks in docs/04-task-decomposition.md wire these commands to services.
    print(f"codectx command '{args.command}' is defined but not implemented yet.")
    print("See docs/04-task-decomposition.md for the ordered MVP task plan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
