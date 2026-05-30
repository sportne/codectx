"""Index orchestration services used by the CLI."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from codectx.frontends.base import (
    ChunkFact,
    DiagnosticFact,
    EdgeFact,
    ExtractedFacts,
    LanguageFrontend,
    NodeFact,
    OccurrenceFact,
)
from codectx.frontends.cpp_treesitter import CppTreeSitterFrontend
from codectx.frontends.java_treesitter import JavaTreeSitterFrontend
from codectx.graph.store import GraphStore
from codectx.scanner.models import FileRecord
from codectx.scanner.repo import ScanOptions, scan_repository
from codectx.source.decoding import SourceValidation, validate_source_bytes
from codectx.source.spans import SourceSpan

EXTRACTION_CACHE_VERSION = 1


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


@dataclass(frozen=True)
class ExtractGraphResult:
    """Raw extraction facts plus cache observability."""

    nodes: list[NodeFact]
    edges: list[EdgeFact]
    occurrences: list[OccurrenceFact]
    chunks: list[ChunkFact]
    diagnostics: list[DiagnosticFact]
    cache_hits: int
    cache_misses: int


FrontendRegistry = Mapping[str, LanguageFrontend]


def run_index(
    repo: str | Path,
    *,
    db_path: str | Path | None = None,
    rebuild: bool = False,
    include_patterns: tuple[str, ...] = (),
    exclude_patterns: tuple[str, ...] = (),
    force_include_patterns: tuple[str, ...] = (),
    use_ignore_files: bool = True,
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

    records = scan_repository(
        repo_path,
        ScanOptions(
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            force_include_patterns=force_include_patterns,
            use_ignore_files=use_ignore_files,
        ),
    )
    fingerprint = content_fingerprint(records)
    with GraphStore(resolved_db_path) as store:
        store.apply_schema()
        latest_snapshot_id = None if rebuild else store.latest_snapshot_id(repo_path)
        if latest_snapshot_id is not None:
            latest_stats = store.get_index_stats(latest_snapshot_id)
            if store.snapshot_content_fingerprint(
                latest_snapshot_id
            ) == fingerprint and latest_stats.get("index.cache_version") == str(
                EXTRACTION_CACHE_VERSION
            ):
                return IndexResult(
                    repo=repo_path,
                    db_path=resolved_db_path,
                    snapshot_id=latest_snapshot_id,
                    stats={
                        **latest_stats,
                        "index.mode": "unchanged",
                        "index.cache_hits": str(len(records)),
                        "index.cache_misses": "0",
                        "index.cache_version": str(EXTRACTION_CACHE_VERSION),
                    },
                )

        repo_id = store.create_repo(repo_path)
        snapshot_id = store.create_snapshot(repo_id, content_fingerprint=fingerprint)
        file_ids = store.insert_files(snapshot_id, records)
        facts = extract_graph_facts(repo_path, records, frontend_registry, store=store)
        edges, occurrences = resolve_unique_references(
            facts.nodes, facts.edges, facts.occurrences
        )
        node_ids = store.insert_nodes(snapshot_id, facts.nodes, file_ids)
        store.insert_edges(snapshot_id, edges, file_ids, node_ids)
        store.insert_occurrences(occurrences, file_ids, node_ids)
        store.insert_chunks(facts.chunks, file_ids, node_ids)
        store.insert_diagnostics(snapshot_id, facts.diagnostics, file_ids)
        stats = store.build_index_stats(snapshot_id)
        stats["feature.fts5"] = (
            "enabled" if store.configure_fts(snapshot_id) else "disabled"
        )
        stats["index.cache_hits"] = str(facts.cache_hits)
        stats["index.cache_misses"] = str(facts.cache_misses)
        stats["index.cache_version"] = str(EXTRACTION_CACHE_VERSION)
        stats["index.mode"] = "full" if facts.cache_hits == 0 else "incremental"
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
    *,
    store: GraphStore | None = None,
) -> ExtractGraphResult:
    """Extract graph facts, optionally using the per-file extraction cache."""
    nodes: list[NodeFact] = []
    edges: list[EdgeFact] = []
    occurrences: list[OccurrenceFact] = []
    chunks: list[ChunkFact] = []
    diagnostics: list[DiagnosticFact] = []
    cache_hits = 0
    cache_misses = 0
    for record in records:
        if record.language is None:
            continue
        frontend = frontends.get(record.language)
        if frontend is None:
            continue
        cached = (
            store.get_extraction_cache(
                path=record.path,
                language=record.language,
                content_hash=record.content_hash,
                cache_version=EXTRACTION_CACHE_VERSION,
            )
            if store is not None
            else None
        )
        if cached is not None and (facts := _safe_facts_from_cache(cached)) is not None:
            cache_hits += 1
        else:
            facts = _extract_file_facts(repo, record, frontend)
            cache_misses += 1
            if store is not None:
                store.upsert_extraction_cache(
                    path=record.path,
                    language=record.language,
                    content_hash=record.content_hash,
                    cache_version=EXTRACTION_CACHE_VERSION,
                    facts=_facts_to_cache(facts),
                )
        nodes.extend(facts.nodes)
        edges.extend(facts.edges)
        occurrences.extend(facts.occurrences)
        chunks.extend(facts.chunks)
        diagnostics.extend(facts.diagnostics)
    return ExtractGraphResult(
        nodes=nodes,
        edges=edges,
        occurrences=occurrences,
        chunks=chunks,
        diagnostics=diagnostics,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
    )


def _extract_file_facts(
    repo: Path, record: FileRecord, frontend: LanguageFrontend
) -> ExtractedFacts:
    source = (repo / record.path).read_bytes()
    validation = validate_source_bytes(record.path, source)
    if not validation.ok:
        return ExtractedFacts(
            diagnostics=_source_validation_diagnostics(record.path, validation)
        )
    return frontend.extract(record.path, source)


def _source_validation_diagnostics(
    file_path: str, validation: SourceValidation
) -> list[DiagnosticFact]:
    return [
        DiagnosticFact(
            file_path=file_path,
            severity="error",
            message=issue.message,
            extractor="source-decoder",
            code=issue.code,
            metadata={
                "encoding": validation.encoding,
                **(
                    {}
                    if issue.byte_offset is None
                    else {"byte_offset": issue.byte_offset}
                ),
            },
        )
        for issue in validation.issues
    ]


def _facts_to_cache(facts: ExtractedFacts) -> dict[str, Any]:
    return {
        "nodes": [_node_to_dict(node) for node in facts.nodes],
        "edges": [_edge_to_dict(edge) for edge in facts.edges],
        "occurrences": [
            _occurrence_to_dict(occurrence) for occurrence in facts.occurrences
        ],
        "chunks": [_chunk_to_dict(chunk) for chunk in facts.chunks],
        "diagnostics": [
            _diagnostic_to_dict(diagnostic) for diagnostic in facts.diagnostics
        ],
    }


def _facts_from_cache(value: dict[str, Any]) -> ExtractedFacts:
    return ExtractedFacts(
        nodes=[_node_from_dict(item) for item in _list(value, "nodes")],
        edges=[_edge_from_dict(item) for item in _list(value, "edges")],
        occurrences=[
            _occurrence_from_dict(item) for item in _list(value, "occurrences")
        ],
        chunks=[_chunk_from_dict(item) for item in _list(value, "chunks")],
        diagnostics=[
            _diagnostic_from_dict(item) for item in _list(value, "diagnostics")
        ],
    )


def _safe_facts_from_cache(value: dict[str, Any]) -> ExtractedFacts | None:
    try:
        return _facts_from_cache(value)
    except (KeyError, TypeError, ValueError):
        return None


def _node_to_dict(node: NodeFact) -> dict[str, Any]:
    return {
        "kind": node.kind,
        "language": node.language,
        "name": node.name,
        "qualified_name": node.qualified_name,
        "symbol_key": node.symbol_key,
        "file_path": node.file_path,
        "span": _span_to_dict(node.span),
        "confidence": node.confidence,
        "extractor": node.extractor,
        "metadata": node.metadata,
    }


def _node_from_dict(value: dict[str, Any]) -> NodeFact:
    return NodeFact(
        kind=str(value["kind"]),
        language=_optional_str(value.get("language")),
        name=_optional_str(value.get("name")),
        qualified_name=_optional_str(value.get("qualified_name")),
        symbol_key=_optional_str(value.get("symbol_key")),
        file_path=_optional_str(value.get("file_path")),
        span=_span_from_dict(value.get("span")),
        confidence=float(value["confidence"]),
        extractor=str(value["extractor"]),
        metadata=_dict(value.get("metadata")),
    )


def _edge_to_dict(edge: EdgeFact) -> dict[str, Any]:
    return {
        "kind": edge.kind,
        "src_key": edge.src_key,
        "dst_key": edge.dst_key,
        "unresolved_src": edge.unresolved_src,
        "unresolved_dst": edge.unresolved_dst,
        "file_path": edge.file_path,
        "span": _span_to_dict(edge.span),
        "confidence": edge.confidence,
        "extractor": edge.extractor,
        "weight": edge.weight,
        "metadata": edge.metadata,
    }


def _edge_from_dict(value: dict[str, Any]) -> EdgeFact:
    return EdgeFact(
        kind=str(value["kind"]),
        src_key=_optional_str(value.get("src_key")),
        dst_key=_optional_str(value.get("dst_key")),
        unresolved_src=_optional_str(value.get("unresolved_src")),
        unresolved_dst=_optional_str(value.get("unresolved_dst")),
        file_path=_optional_str(value.get("file_path")),
        span=_span_from_dict(value.get("span")),
        confidence=float(value["confidence"]),
        extractor=str(value["extractor"]),
        weight=float(value.get("weight", 1.0)),
        metadata=_dict(value.get("metadata")),
    )


def _occurrence_to_dict(occurrence: OccurrenceFact) -> dict[str, Any]:
    return {
        "file_path": occurrence.file_path,
        "role": occurrence.role,
        "text": occurrence.text,
        "span": _span_to_dict(occurrence.span),
        "node_key": occurrence.node_key,
        "resolved_key": occurrence.resolved_key,
        "confidence": occurrence.confidence,
        "extractor": occurrence.extractor,
        "metadata": occurrence.metadata,
    }


def _occurrence_from_dict(value: dict[str, Any]) -> OccurrenceFact:
    span = _span_from_dict(value.get("span"))
    if span is None:
        raise ValueError("cached occurrence is missing span")
    return OccurrenceFact(
        file_path=str(value["file_path"]),
        role=str(value["role"]),
        text=str(value["text"]),
        span=span,
        node_key=_optional_str(value.get("node_key")),
        resolved_key=_optional_str(value.get("resolved_key")),
        confidence=float(value["confidence"]),
        extractor=str(value["extractor"]),
        metadata=_dict(value.get("metadata")),
    )


def _chunk_to_dict(chunk: ChunkFact) -> dict[str, Any]:
    return {
        "file_path": chunk.file_path,
        "node_key": chunk.node_key,
        "kind": chunk.kind,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "text": chunk.text,
        "token_estimate": chunk.token_estimate,
        "metadata": chunk.metadata,
    }


def _chunk_from_dict(value: dict[str, Any]) -> ChunkFact:
    return ChunkFact(
        file_path=str(value["file_path"]),
        node_key=_optional_str(value.get("node_key")),
        kind=str(value["kind"]),
        start_line=int(value["start_line"]),
        end_line=int(value["end_line"]),
        text=str(value["text"]),
        token_estimate=int(value["token_estimate"]),
        metadata=_dict(value.get("metadata")),
    )


def _diagnostic_to_dict(diagnostic: DiagnosticFact) -> dict[str, Any]:
    return {
        "file_path": diagnostic.file_path,
        "severity": diagnostic.severity,
        "message": diagnostic.message,
        "extractor": diagnostic.extractor,
        "span": _span_to_dict(diagnostic.span),
        "code": diagnostic.code,
        "metadata": diagnostic.metadata,
    }


def _diagnostic_from_dict(value: dict[str, Any]) -> DiagnosticFact:
    return DiagnosticFact(
        file_path=_optional_str(value.get("file_path")),
        severity=str(value["severity"]),
        message=str(value["message"]),
        extractor=str(value["extractor"]),
        span=_span_from_dict(value.get("span")),
        code=_optional_str(value.get("code")),
        metadata=_dict(value.get("metadata")),
    )


def _span_to_dict(span: SourceSpan | None) -> dict[str, Any] | None:
    if span is None:
        return None
    return {
        "file_path": span.file_path,
        "start_byte": span.start_byte,
        "end_byte": span.end_byte,
        "start_line": span.start_line,
        "start_col": span.start_col,
        "end_line": span.end_line,
        "end_col": span.end_col,
    }


def _span_from_dict(value: object) -> SourceSpan | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("cached span must be an object")
    return SourceSpan(
        file_path=str(value["file_path"]),
        start_byte=int(value["start_byte"]),
        end_byte=int(value["end_byte"]),
        start_line=int(value["start_line"]),
        start_col=int(value["start_col"]),
        end_line=int(value["end_line"]),
        end_col=int(value["end_col"]),
    )


def _list(value: dict[str, Any], key: str) -> list[dict[str, Any]]:
    found = value.get(key, [])
    if not isinstance(found, list) or not all(isinstance(item, dict) for item in found):
        raise ValueError(f"cached {key} must be a list of objects")
    return found


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


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
