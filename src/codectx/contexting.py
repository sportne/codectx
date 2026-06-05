"""CLI-facing context bundle orchestration services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codectx.context.anchors import AnchorResult, resolve_file_line_anchor
from codectx.context.formatters import format_json, format_markdown, format_text
from codectx.context.planner import build_context_bundle
from codectx.graph.query import SymbolResult
from codectx.graph.query import search_symbols as graph_search_symbols
from codectx.graph.store import GraphStore
from codectx.indexing import default_db_path

SUPPORTED_CONTEXT_FORMATS = {"json", "markdown", "text"}
SUPPORTED_CONTEXT_GOALS = {
    "call-neighborhood",
    "dependencies",
    "explain",
    "failure-modes",
}


@dataclass(frozen=True)
class ContextingError:
    """Actionable context generation error suitable for CLI display."""

    message: str


@dataclass(frozen=True)
class ContextResult:
    """Rendered context command response."""

    rendered_text: str
    output_path: Path | None = None


def build_context(
    repo: str | Path,
    *,
    db_path: str | Path | None = None,
    symbol: str | None = None,
    file_path: str | Path | None = None,
    line: int | None = None,
    goal: str = "explain",
    budget: int = 8000,
    output_format: str = "markdown",
    output_path: str | Path | None = None,
) -> ContextResult | ContextingError:
    """Build and render a context bundle."""
    error = _validate_request(
        goal=goal,
        budget=budget,
        output_format=output_format,
        symbol=symbol,
        file_path=file_path,
        line=line,
        output_path=output_path,
    )
    if error is not None:
        return error

    resolved_output_path = _resolve_output_path(output_path)
    repo_path = Path(repo).resolve()
    resolved_db_path = default_db_path(repo_path, db_path)
    if not resolved_db_path.exists():
        return ContextingError(
            f"No codectx index found at {resolved_db_path}. "
            f"Run `codectx index {repo_path}` first."
        )

    with GraphStore(resolved_db_path) as store:
        store.apply_schema()
        snapshot_id = store.latest_snapshot_id(repo_path)
        if snapshot_id is None:
            return ContextingError(
                f"No codectx index found for {repo_path}. "
                f"Run `codectx index {repo_path}` first."
            )
        stats = store.get_index_stats(snapshot_id)
        if not stats:
            return ContextingError(
                f"No index health stats found for {repo_path}. "
                f"Run `codectx index {repo_path} --rebuild`."
            )
        anchor_result = _resolve_context_anchor(
            store,
            snapshot_id,
            repo_path,
            symbol=symbol,
            file_path=file_path,
            line=line,
        )
        if isinstance(anchor_result, ContextingError):
            return anchor_result
        anchor, symbol_matches = anchor_result
        uncertainty_notes = []
        if symbol is not None and len(symbol_matches) > 1:
            uncertainty_notes.append(
                f"Symbol query matched {len(symbol_matches)} symbols; "
                "selected the top-ranked match."
            )
        bundle = build_context_bundle(
            store.conn,
            snapshot_id,
            repo_path,
            anchor,
            budget=budget,
            index_health=stats,
            query={
                "goal": goal,
                "budget": budget,
                "format": output_format,
                "symbol": symbol,
                "file": None if file_path is None else str(file_path),
                "line": line,
            },
            uncertainty_notes=uncertainty_notes,
        )

    return ContextResult(
        rendered_text=_format_bundle(bundle, output_format),
        output_path=resolved_output_path,
    )


def _resolve_context_anchor(
    store: GraphStore,
    snapshot_id: int,
    repo: Path,
    *,
    symbol: str | None,
    file_path: str | Path | None,
    line: int | None,
) -> tuple[AnchorResult, list[SymbolResult]] | ContextingError:
    if file_path is not None:
        relative_file_path = _repo_relative_path(repo, file_path)
        if line is None:
            return ContextingError("--line is required when using --file.")
        file_anchor = resolve_file_line_anchor(
            store.conn,
            snapshot_id,
            relative_file_path,
            line,
        )
        if isinstance(file_anchor, AnchorResult):
            return file_anchor, []
        return ContextingError(file_anchor.message)

    if symbol is None:
        return ContextingError("Provide either --symbol or --file for context.")
    matches = graph_search_symbols(store.conn, snapshot_id, symbol)
    if not matches:
        return ContextingError(f"No symbols found for {symbol}.")
    symbol_anchor = _anchor_from_symbol(store, snapshot_id, matches[0])
    if isinstance(symbol_anchor, ContextingError):
        return symbol_anchor
    return symbol_anchor, matches


def _anchor_from_symbol(
    store: GraphStore, snapshot_id: int, symbol: SymbolResult
) -> AnchorResult | ContextingError:
    if symbol.file_path is None or symbol.start_line is None:
        return ContextingError(
            f"Symbol {symbol.node_id} does not have a file/line anchor."
        )
    row = store.conn.execute(
        """
        SELECT file.id AS file_id, file.path AS file_path,
               chunk.id AS chunk_id, chunk.kind AS chunk_kind,
               chunk.start_line AS chunk_start_line,
               chunk.end_line AS chunk_end_line,
               chunk.text AS chunk_text,
               chunk.token_estimate AS chunk_token_estimate
        FROM node
        LEFT JOIN file ON file.id = node.file_id
        LEFT JOIN chunk ON chunk.node_id = node.id
        WHERE node.snapshot_id = ? AND node.id = ?
        ORDER BY chunk.start_line ASC, chunk.id ASC
        LIMIT 1
        """,
        (snapshot_id, symbol.node_id),
    ).fetchone()
    if row is None or row["file_id"] is None:
        return ContextingError(
            f"Symbol {symbol.node_id} does not have a file/line anchor."
        )
    return AnchorResult(
        file_id=int(row["file_id"]),
        file_path=str(row["file_path"]),
        line=symbol.start_line,
        node_id=symbol.node_id,
        node_kind=symbol.kind,
        node_name=symbol.name,
        qualified_name=symbol.qualified_name,
        symbol_key=symbol.symbol_key,
        start_line=symbol.start_line,
        end_line=symbol.end_line,
        chunk_id=None if row["chunk_id"] is None else int(row["chunk_id"]),
        chunk_kind=None if row["chunk_kind"] is None else str(row["chunk_kind"]),
        chunk_start_line=(
            None if row["chunk_start_line"] is None else int(row["chunk_start_line"])
        ),
        chunk_end_line=(
            None if row["chunk_end_line"] is None else int(row["chunk_end_line"])
        ),
        chunk_text=None if row["chunk_text"] is None else str(row["chunk_text"]),
        chunk_token_estimate=(
            None
            if row["chunk_token_estimate"] is None
            else int(row["chunk_token_estimate"])
        ),
    )


def _format_bundle(bundle: Any, output_format: str) -> str:
    if output_format == "json":
        return format_json(bundle)
    if output_format == "text":
        return format_text(bundle)
    return format_markdown(bundle)


def _validate_request(
    *,
    goal: str,
    budget: int,
    output_format: str,
    symbol: str | None,
    file_path: str | Path | None,
    line: int | None,
    output_path: str | Path | None,
) -> ContextingError | None:
    if goal not in SUPPORTED_CONTEXT_GOALS:
        return ContextingError(f"Unsupported context goal: {goal}")
    if output_format not in SUPPORTED_CONTEXT_FORMATS:
        return ContextingError(f"Unsupported context format: {output_format}")
    if budget <= 0:
        return ContextingError("Context budget must be greater than 0.")
    if symbol is None and file_path is None:
        return ContextingError("Provide either --symbol or --file for context.")
    if symbol is not None and file_path is not None:
        return ContextingError("Provide only one context anchor: --symbol or --file.")
    if symbol is not None and line is not None:
        return ContextingError("--line can only be used with --file.")
    if line is not None and line < 1:
        return ContextingError("Line number must be 1 or greater.")
    if output_path is not None:
        parent = Path(output_path).expanduser().resolve().parent
        if not parent.exists():
            return ContextingError(f"Output directory does not exist: {parent}")
    return None


def _resolve_output_path(output_path: str | Path | None) -> Path | None:
    if output_path is None:
        return None
    return Path(output_path).expanduser().resolve()


def _repo_relative_path(repo: Path, file_path: str | Path) -> str:
    path = Path(file_path)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(repo).as_posix()
        except ValueError:
            return path.as_posix()
    return path.as_posix()
