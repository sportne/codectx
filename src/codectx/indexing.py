"""Index orchestration services used by the CLI."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from codectx.frontends.base import (
    ChunkFact,
    DiagnosticFact,
    EdgeFact,
    LanguageFrontend,
    NodeFact,
    OccurrenceFact,
)
from codectx.frontends.cpp_treesitter import CppTreeSitterFrontend
from codectx.frontends.java_treesitter import JavaTreeSitterFrontend
from codectx.graph.store import GraphStore
from codectx.scanner.models import FileRecord
from codectx.scanner.repo import scan_repository


@dataclass(frozen=True)
class IndexResult:
    """Result of indexing a repository."""

    repo: Path
    db_path: Path
    snapshot_id: int
    stats: dict[str, str]


@dataclass(frozen=True)
class HealthResult:
    """Persisted index health for a repository."""

    repo: Path
    db_path: Path
    snapshot_id: int
    stats: dict[str, str]
    integrity: str | None = None
    integrity_details: dict[str, str] | None = None


@dataclass(frozen=True)
class IndexingError:
    """Actionable indexing error suitable for CLI display."""

    message: str


FrontendRegistry = Mapping[str, LanguageFrontend]


def run_index(
    repo: str | Path,
    *,
    db_path: str | Path | None = None,
    rebuild: bool = False,
    frontends: FrontendRegistry | None = None,
) -> IndexResult | IndexingError:
    """Scan and persist index data for a repository."""
    repo_path = Path(repo).resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        return IndexingError(
            f"Repository path does not exist or is not a directory: {repo_path}"
        )
    frontend_registry = default_frontends() if frontends is None else frontends

    resolved_db_path = default_db_path(repo_path, db_path)
    resolved_db_path.parent.mkdir(parents=True, exist_ok=True)
    if rebuild:
        remove_db_files(resolved_db_path)

    records = scan_repository(repo_path)
    fingerprint = content_fingerprint(records)
    with GraphStore(resolved_db_path) as store:
        store.apply_schema()
        repo_id = store.create_repo(repo_path)
        snapshot_id = store.create_snapshot(repo_id, content_fingerprint=fingerprint)
        file_ids = store.insert_files(snapshot_id, records)
        nodes, edges, occurrences, chunks, diagnostics = extract_graph_facts(
            repo_path, records, frontend_registry
        )
        edges, occurrences = resolve_unique_references(nodes, edges, occurrences)
        node_ids = store.insert_nodes(snapshot_id, nodes, file_ids)
        store.insert_edges(snapshot_id, edges, file_ids, node_ids)
        store.insert_occurrences(occurrences, file_ids, node_ids)
        store.insert_chunks(chunks, file_ids, node_ids)
        store.insert_diagnostics(snapshot_id, diagnostics, file_ids)
        stats = store.build_index_stats(snapshot_id)
        stats["feature.fts5"] = (
            "enabled" if store.configure_fts(snapshot_id) else "disabled"
        )
        store.upsert_index_stats(snapshot_id, stats)

    return IndexResult(
        repo=repo_path,
        db_path=resolved_db_path,
        snapshot_id=snapshot_id,
        stats=stats,
    )


def read_health(
    repo: str | Path,
    *,
    db_path: str | Path | None = None,
    include_integrity: bool = False,
) -> HealthResult | IndexingError:
    """Read persisted index health for a repository."""
    repo_path = Path(repo).resolve()
    resolved_db_path = default_db_path(repo_path, db_path)
    if not resolved_db_path.exists():
        return IndexingError(
            f"No codectx index found at {resolved_db_path}. "
            f"Run `codectx index {repo_path}` first."
        )

    with GraphStore(resolved_db_path) as store:
        store.apply_schema()
        snapshot_id = store.latest_snapshot_id(repo_path)
        if snapshot_id is None:
            return IndexingError(
                f"No codectx index found for {repo_path}. "
                f"Run `codectx index {repo_path}` first."
            )
        stats = store.get_index_stats(snapshot_id)
        if not stats:
            return IndexingError(
                f"No index health stats found for {repo_path}. "
                f"Run `codectx index {repo_path} --rebuild`."
            )
        integrity = None
        integrity_details = None
        if include_integrity:
            integrity_report = store.integrity_report(snapshot_id)
            integrity = integrity_report.summary()
            integrity_details = integrity_report.details()

    return HealthResult(
        repo=repo_path,
        db_path=resolved_db_path,
        snapshot_id=snapshot_id,
        stats=stats,
        integrity=integrity,
        integrity_details=integrity_details,
    )


def default_db_path(repo: Path, explicit_db_path: str | Path | None) -> Path:
    """Resolve an explicit DB path or return the default repo-local path."""
    if explicit_db_path is not None:
        return Path(explicit_db_path).resolve()
    return repo / ".codectx" / "graph.sqlite"


def default_frontends() -> FrontendRegistry:
    """Return built-in language frontends used by index orchestration."""
    return {
        "cpp": CppTreeSitterFrontend(),
        "java": JavaTreeSitterFrontend(),
    }


def extract_graph_facts(
    repo: Path,
    records: list[FileRecord],
    frontends: FrontendRegistry,
) -> tuple[
    list[NodeFact],
    list[EdgeFact],
    list[OccurrenceFact],
    list[ChunkFact],
    list[DiagnosticFact],
]:
    """Extract graph facts for scanned records with registered frontends."""
    nodes: list[NodeFact] = []
    edges: list[EdgeFact] = []
    occurrences: list[OccurrenceFact] = []
    chunks: list[ChunkFact] = []
    diagnostics: list[DiagnosticFact] = []
    for record in records:
        if record.language is None:
            continue
        frontend = frontends.get(record.language)
        if frontend is None:
            continue
        facts = frontend.extract(record.path, (repo / record.path).read_bytes())
        nodes.extend(facts.nodes)
        edges.extend(facts.edges)
        occurrences.extend(facts.occurrences)
        chunks.extend(facts.chunks)
        diagnostics.extend(facts.diagnostics)
    return nodes, edges, occurrences, chunks, diagnostics


def resolve_unique_references(
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
) -> tuple[list[EdgeFact], list[OccurrenceFact]]:
    """Resolve heuristic reference facts when text has one project-wide target."""
    references = _unique_type_reference_map(nodes)
    resolved_edges = [_resolve_edge_reference(edge, references) for edge in edges]
    resolved_occurrences = [
        _resolve_occurrence_reference(occurrence, references)
        for occurrence in occurrences
    ]
    return resolved_edges, resolved_occurrences


def _unique_type_reference_map(nodes: list[NodeFact]) -> dict[tuple[str, str], str]:
    candidates: dict[tuple[str, str], set[str]] = {}
    for node in nodes:
        if node.symbol_key is None or node.kind != "type" or node.language is None:
            continue
        for name in _reference_names(node):
            candidates.setdefault((node.language, name), set()).add(node.symbol_key)
    return {
        name: next(iter(keys)) for name, keys in candidates.items() if len(keys) == 1
    }


def _reference_names(node: NodeFact) -> set[str]:
    names = {value for value in (node.name, node.qualified_name) if value}
    if node.qualified_name:
        names.add(node.qualified_name.split(".")[-1].split("::")[-1])
    return names


def _resolve_edge_reference(
    edge: EdgeFact, references: dict[tuple[str, str], str]
) -> EdgeFact:
    if edge.kind != "uses_type":
        return edge
    if edge.dst_key is not None or edge.unresolved_dst is None:
        return edge
    language = _symbol_key_language(edge.src_key)
    if language is None:
        return edge
    resolved_key = references.get((language, edge.unresolved_dst))
    if resolved_key is None:
        return edge
    return replace(edge, dst_key=resolved_key, unresolved_dst=None)


def _resolve_occurrence_reference(
    occurrence: OccurrenceFact, references: dict[tuple[str, str], str]
) -> OccurrenceFact:
    if occurrence.role != "type_reference":
        return occurrence
    if occurrence.resolved_key is not None:
        return occurrence
    language = _symbol_key_language(occurrence.node_key)
    if language is None:
        return occurrence
    resolved_key = references.get((language, occurrence.text))
    if resolved_key is None:
        return occurrence
    return replace(occurrence, resolved_key=resolved_key)


def _symbol_key_language(symbol_key: str | None) -> str | None:
    if symbol_key is None or ":" not in symbol_key:
        return None
    return symbol_key.split(":", 1)[0]


def remove_db_files(db_path: Path) -> None:
    """Remove SQLite database files used by rebuild."""
    for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        if path.exists():
            path.unlink()


def content_fingerprint(records: list[FileRecord]) -> str:
    """Return a deterministic fingerprint for scanned file records."""
    digest = hashlib.sha256()
    for record in records:
        digest.update(record.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(record.content_hash.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()
