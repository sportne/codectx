"""Command-line interface for codectx."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from codectx import __version__
from codectx.graph.store import GraphStore
from codectx.scanner.models import FileRecord
from codectx.scanner.repo import scan_repository


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

    print(f"codectx command '{args.command}' is defined but not implemented yet.")
    print("See docs/04-task-decomposition.md for the ordered MVP task plan.")
    return 0


def _run_index(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    if not repo.exists() or not repo.is_dir():
        print(f"Repository path does not exist or is not a directory: {repo}")
        return 1

    db_path = _db_path(repo, args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if args.rebuild:
        _remove_db_files(db_path)

    records = scan_repository(repo)
    fingerprint = _content_fingerprint(records)
    with GraphStore(db_path) as store:
        store.apply_schema()
        repo_id = store.create_repo(repo)
        snapshot_id = store.create_snapshot(repo_id, content_fingerprint=fingerprint)
        store.insert_files(snapshot_id, records)
        stats = store.build_index_stats(snapshot_id)
        store.upsert_index_stats(snapshot_id, stats)

    print(f"Indexed {repo}")
    print(f"database: {db_path}")
    print(f"snapshot_id: {snapshot_id}")
    _print_stats(stats)
    return 0


def _run_health(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    db_path = _db_path(repo, args.db)
    if not db_path.exists():
        print(f"No codectx index found at {db_path}. Run `codectx index {repo}` first.")
        return 1

    with GraphStore(db_path) as store:
        store.apply_schema()
        snapshot_id = store.latest_snapshot_id(repo)
        if snapshot_id is None:
            print(
                f"No codectx index found for {repo}. Run `codectx index {repo}` first."
            )
            return 1
        stats = store.get_index_stats(snapshot_id)
        if not stats:
            print(
                f"No index health stats found for {repo}. "
                f"Run `codectx index {repo} --rebuild`."
            )
            return 1
        integrity = store.integrity_check() if args.integrity else None

    print(f"Index health for {repo}")
    print(f"database: {db_path}")
    print(f"snapshot_id: {snapshot_id}")
    if integrity is not None:
        print(f"integrity: {integrity}")
    _print_stats(stats)
    return 0


def _db_path(repo: Path, explicit_db: Path | None) -> Path:
    if explicit_db is not None:
        return explicit_db.resolve()
    return repo / ".codectx" / "graph.sqlite"


def _remove_db_files(db_path: Path) -> None:
    for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        if path.exists():
            path.unlink()


def _content_fingerprint(records: list[FileRecord]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(record.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(record.content_hash.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _print_stats(stats: dict[str, str]) -> None:
    for key, value in sorted(stats.items()):
        print(f"{key}: {value}")


if __name__ == "__main__":
    raise SystemExit(main())
