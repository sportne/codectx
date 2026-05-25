"""CLI-facing query orchestration services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codectx.context.anchors import AnchorError, AnchorResult, resolve_file_line_anchor
from codectx.graph.query import (
    ChunkSearchResult,
    CombinedSearchResult,
    EdgeDetail,
    NodeDetail,
    SymbolResult,
)
from codectx.graph.query import get_edge_detail as graph_get_edge_detail
from codectx.graph.query import get_node_detail as graph_get_node_detail
from codectx.graph.query import search as graph_search
from codectx.graph.query import search_symbols as graph_search_symbols
from codectx.graph.store import GraphStore
from codectx.indexing import default_db_path


@dataclass(frozen=True)
class QueryContext:
    """Resolved query context for the latest indexed repository snapshot."""

    repo: Path
    db_path: Path
    snapshot_id: int


@dataclass(frozen=True)
class QueryingError:
    """Actionable query error suitable for CLI display."""

    message: str


@dataclass(frozen=True)
class PlaceholderResult:
    """Placeholder response for query commands not implemented in this milestone step."""

    message: str


@dataclass(frozen=True)
class SymbolSearchResult:
    """Symbol search response for CLI rendering."""

    repo: Path
    db_path: Path
    snapshot_id: int
    query: str
    symbols: list[SymbolResult]


@dataclass(frozen=True)
class SearchResult:
    """Combined search response for CLI rendering."""

    repo: Path
    db_path: Path
    snapshot_id: int
    query: str
    symbols: list[SymbolResult]
    chunks: list[ChunkSearchResult]
    used_fts: bool


@dataclass(frozen=True)
class FileLineAnchorResult:
    """File/line anchor resolution response for callers."""

    repo: Path
    db_path: Path
    snapshot_id: int
    anchor: AnchorResult


@dataclass(frozen=True)
class NodeInspectionResult:
    """Node inspection response for CLI rendering."""

    repo: Path
    db_path: Path
    snapshot_id: int
    node: NodeDetail


@dataclass(frozen=True)
class EdgeInspectionResult:
    """Edge inspection response for CLI rendering."""

    repo: Path
    db_path: Path
    snapshot_id: int
    edge: EdgeDetail


def resolve_query_context(
    repo: str | Path,
    *,
    db_path: str | Path | None = None,
) -> QueryContext | QueryingError:
    """Resolve the latest indexed snapshot for a repository."""
    repo_path = Path(repo).resolve()
    resolved_db_path = default_db_path(repo_path, db_path)
    if not resolved_db_path.exists():
        return QueryingError(
            f"No codectx index found at {resolved_db_path}. "
            f"Run `codectx index {repo_path}` first."
        )

    with GraphStore(resolved_db_path) as store:
        store.apply_schema()
        snapshot_id = store.latest_snapshot_id(repo_path)
        if snapshot_id is None:
            return QueryingError(
                f"No codectx index found for {repo_path}. "
                f"Run `codectx index {repo_path}` first."
            )

    return QueryContext(
        repo=repo_path,
        db_path=resolved_db_path,
        snapshot_id=snapshot_id,
    )


def resolve_anchor(
    repo: str | Path,
    file_path: str | Path,
    line: int,
    *,
    db_path: str | Path | None = None,
) -> FileLineAnchorResult | QueryingError:
    """Resolve a file/line anchor against the latest repository snapshot."""
    context = resolve_query_context(repo, db_path=db_path)
    if isinstance(context, QueryingError):
        return context
    relative_file_path = _repo_relative_path(context.repo, file_path)

    with GraphStore(context.db_path) as store:
        anchor = resolve_file_line_anchor(
            store.conn,
            context.snapshot_id,
            relative_file_path,
            line,
        )
    if isinstance(anchor, AnchorError):
        return QueryingError(anchor.message)

    return FileLineAnchorResult(
        repo=context.repo,
        db_path=context.db_path,
        snapshot_id=context.snapshot_id,
        anchor=anchor,
    )


def search(
    repo: str | Path,
    query: str,
    *,
    db_path: str | Path | None = None,
    limit: int = 20,
) -> SearchResult | QueryingError:
    """Search indexed symbols and chunks for a repository."""
    context = resolve_query_context(repo, db_path=db_path)
    if isinstance(context, QueryingError):
        return context

    with GraphStore(context.db_path) as store:
        result: CombinedSearchResult = graph_search(
            store.conn,
            context.snapshot_id,
            query,
            limit=limit,
        )

    return SearchResult(
        repo=context.repo,
        db_path=context.db_path,
        snapshot_id=context.snapshot_id,
        query=query,
        symbols=result.symbols,
        chunks=result.chunks,
        used_fts=result.used_fts,
    )


def inspect_node(
    repo: str | Path,
    node_id: int,
    *,
    db_path: str | Path | None = None,
) -> NodeInspectionResult | QueryingError:
    """Inspect an indexed graph node by id."""
    context = resolve_query_context(repo, db_path=db_path)
    if isinstance(context, QueryingError):
        return context

    with GraphStore(context.db_path) as store:
        node = graph_get_node_detail(store.conn, context.snapshot_id, node_id)
    if node is None:
        return QueryingError(
            f"Node {node_id} was not found in the latest codectx snapshot."
        )

    return NodeInspectionResult(
        repo=context.repo,
        db_path=context.db_path,
        snapshot_id=context.snapshot_id,
        node=node,
    )


def inspect_edge(
    repo: str | Path,
    edge_id: int,
    *,
    db_path: str | Path | None = None,
) -> EdgeInspectionResult | QueryingError:
    """Inspect an indexed graph edge by id."""
    context = resolve_query_context(repo, db_path=db_path)
    if isinstance(context, QueryingError):
        return context

    with GraphStore(context.db_path) as store:
        edge = graph_get_edge_detail(store.conn, context.snapshot_id, edge_id)
    if edge is None:
        return QueryingError(
            f"Edge {edge_id} was not found in the latest codectx snapshot."
        )

    return EdgeInspectionResult(
        repo=context.repo,
        db_path=context.db_path,
        snapshot_id=context.snapshot_id,
        edge=edge,
    )


def search_symbols(
    repo: str | Path,
    query: str,
    *,
    db_path: str | Path | None = None,
    limit: int = 20,
) -> SymbolSearchResult | QueryingError:
    """Search indexed symbols for a repository."""
    context = resolve_query_context(repo, db_path=db_path)
    if isinstance(context, QueryingError):
        return context

    with GraphStore(context.db_path) as store:
        symbols = graph_search_symbols(
            store.conn,
            context.snapshot_id,
            query,
            limit=limit,
        )

    return SymbolSearchResult(
        repo=context.repo,
        db_path=context.db_path,
        snapshot_id=context.snapshot_id,
        query=query,
        symbols=symbols,
    )


def _repo_relative_path(repo: Path, file_path: str | Path) -> str:
    path = Path(file_path)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(repo).as_posix()
        except ValueError:
            return path.as_posix()
    return path.as_posix()


def placeholder_result(command: str) -> PlaceholderResult:
    """Return the current placeholder response for an unimplemented query command."""
    return PlaceholderResult(
        message=(
            f"codectx command '{command}' is defined but not implemented yet.\n"
            "See docs/04-task-decomposition.md for the ordered MVP task plan."
        )
    )
