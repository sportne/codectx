"""Initial context bundle planning for explain requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from json import loads
from pathlib import Path
from typing import Any

from codectx.context.anchors import AnchorResult
from codectx.context.bundle import ContextBundle, ContextItem, OmittedItem
from codectx.context.ranking import RankingAnchor, RankingCandidate, score_candidate
from codectx.source.decoding import validate_source_bytes
from codectx.source.snippets import snippet_by_line_range
from codectx.source.tokens import estimate_token_count

VENDOR_PATH_HINTS = frozenset(
    {"vendor", "vendors", "third_party", "third-party", "external"}
)


@dataclass(frozen=True)
class _Candidate:
    kind: str
    file: str | None
    line_range: tuple[int, int] | None
    text: str
    score: float
    token_estimate: int
    reason: str
    confidence: float
    extractor: str | None
    required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    score_trace: dict[str, float] = field(default_factory=dict)


def build_context_bundle(
    conn: Any,
    snapshot_id: int,
    repo: str | Path,
    anchor: AnchorResult,
    *,
    budget: int,
    index_health: dict[str, str],
    query: dict[str, Any] | None = None,
    uncertainty_notes: list[str] | None = None,
) -> ContextBundle:
    """Build a deterministic context bundle for a supported goal."""
    repo_path = Path(repo)
    notes = list(uncertainty_notes or [])
    trace: list[dict[str, Any]] = [
        {"stage": "anchor", "file": anchor.file_path, "line": anchor.line}
    ]
    resolved_query = query or {"goal": "explain", "budget": budget}
    goal = str(resolved_query.get("goal", "explain"))

    candidates: list[_Candidate] = []
    target = _target_candidate(conn, repo_path, anchor, notes)
    if target is not None:
        candidates.append(target)
        trace.append({"stage": "candidate", "kind": target.kind, "required": True})
    enclosing = _enclosing_candidates(conn, repo_path, anchor, notes)
    candidates.extend(enclosing)
    for candidate in enclosing:
        trace.append({"stage": "candidate", "kind": candidate.kind, "required": True})
    candidates = _compact_large_required_enclosing_candidates(
        candidates, budget, notes, trace
    )

    relationship_candidates = _relationship_candidates(conn, repo_path, anchor, notes)
    if goal == "call-neighborhood":
        relationship_candidates.extend(
            _incoming_call_candidates(conn, repo_path, anchor, notes)
        )
    test_candidates = _test_candidates(conn, anchor, _selected_chunk_ids(candidates))
    diagnostic_candidates = (
        _diagnostic_candidates(conn, repo_path, snapshot_id, anchor, notes)
        if goal == "failure-modes"
        else []
    )
    base_optional_candidates = [
        *diagnostic_candidates,
        *_import_include_candidates(conn, repo_path, anchor),
        *relationship_candidates,
        *test_candidates,
    ]
    optional_candidates = [
        *base_optional_candidates,
        *_sibling_candidates(
            conn,
            anchor,
            _selected_chunk_ids([*candidates, *base_optional_candidates]),
        ),
    ]
    trace.append(
        {
            "stage": "candidates",
            "optional_count": len(optional_candidates),
            "diagnostic_count": len(diagnostic_candidates),
            "relationship_count": len(relationship_candidates),
            "test_count": len(test_candidates),
        }
    )

    candidates = _score_candidates(candidates, anchor, resolved_query)
    optional_candidates = _score_candidates(optional_candidates, anchor, resolved_query)
    trace.append(
        {
            "stage": "rank",
            "required_count": len(candidates),
            "optional_count": len(optional_candidates),
        }
    )

    selected, omitted = _select_candidates(
        candidates,
        optional_candidates,
        budget,
        goal=goal,
    )
    items = [
        ContextItem(
            rank=rank,
            kind=candidate.kind,
            file=candidate.file,
            line_range=candidate.line_range,
            text=candidate.text,
            score=candidate.score,
            token_estimate=candidate.token_estimate,
            reason=candidate.reason,
            confidence=candidate.confidence,
            extractor=candidate.extractor,
            metadata=candidate.metadata,
            score_trace=candidate.score_trace,
        )
        for rank, candidate in enumerate(selected, start=1)
    ]

    return ContextBundle(
        query=resolved_query,
        anchor=_anchor_dict(anchor),
        index_health=dict(sorted(index_health.items())),
        items=items,
        omitted=omitted,
        uncertainty_notes=notes,
        trace=trace,
    )


def build_explain_bundle(
    conn: Any,
    snapshot_id: int,
    repo: str | Path,
    anchor: AnchorResult,
    *,
    budget: int,
    index_health: dict[str, str],
    query: dict[str, Any] | None = None,
    uncertainty_notes: list[str] | None = None,
) -> ContextBundle:
    """Build an explain bundle through the shared goal planner."""
    resolved_query = query or {"goal": "explain", "budget": budget}
    return build_context_bundle(
        conn,
        snapshot_id,
        repo,
        anchor,
        budget=budget,
        index_health=index_health,
        query={**resolved_query, "goal": "explain"},
        uncertainty_notes=uncertainty_notes,
    )


def _target_candidate(
    conn: Any,
    repo: Path,
    anchor: AnchorResult,
    notes: list[str],
) -> _Candidate | None:
    if anchor.node_id is not None:
        row = _chunk_for_node(conn, anchor.file_id, anchor.node_id)
        if row is not None:
            return _chunk_candidate(row, "target.definition", "target definition", 5.0)
        if anchor.start_line is not None and anchor.end_line is not None:
            snippet = _source_snippet(
                repo, anchor.file_path, anchor.start_line, anchor.end_line, notes
            )
            if snippet is not None:
                notes.append(
                    "Target context used source-range fallback because no node chunk "
                    "was indexed."
                )
                return _Candidate(
                    kind="target.source",
                    file=snippet.file_path,
                    line_range=(snippet.start_line, snippet.end_line),
                    text=snippet.text,
                    score=4.0,
                    token_estimate=snippet.token_estimate,
                    reason="target source range fallback",
                    confidence=0.5,
                    extractor=None,
                    required=True,
                    metadata={"node_id": anchor.node_id},
                )

    if (
        anchor.node_id is None
        and anchor.chunk_id is not None
        and anchor.chunk_text is not None
    ):
        return _Candidate(
            kind=f"target.{anchor.chunk_kind or 'chunk'}",
            file=anchor.file_path,
            line_range=_line_range(anchor.chunk_start_line, anchor.chunk_end_line),
            text=anchor.chunk_text,
            score=5.0,
            token_estimate=anchor.chunk_token_estimate
            or estimate_token_count(anchor.chunk_text),
            reason="anchor chunk",
            confidence=0.7,
            extractor=None,
            required=True,
            metadata={"chunk_id": anchor.chunk_id, "node_id": anchor.node_id},
        )

    snippet = _source_snippet(repo, anchor.file_path, anchor.line, anchor.line, notes)
    if snippet is None:
        notes.append("Target source line could not be read from the working tree.")
        return None
    notes.append(
        "Target context used source-line fallback because no chunk was indexed."
    )
    return _Candidate(
        kind="target.source",
        file=snippet.file_path,
        line_range=(snippet.start_line, snippet.end_line),
        text=snippet.text,
        score=4.0,
        token_estimate=snippet.token_estimate,
        reason="target source line fallback",
        confidence=0.5,
        extractor=None,
        required=True,
        metadata={"node_id": anchor.node_id},
    )


def _enclosing_candidates(
    conn: Any,
    repo: Path,
    anchor: AnchorResult,
    notes: list[str],
) -> list[_Candidate]:
    if anchor.node_id is None:
        return []
    rows = conn.execute(
        """
        SELECT id, kind, language, name, qualified_name, symbol_key, file_id,
               start_line, end_line, confidence, extractor
        FROM node
        WHERE snapshot_id = ?
          AND file_id = ?
          AND id IS NOT ?
          AND kind IN ('namespace', 'type')
          AND start_line IS NOT NULL
          AND end_line IS NOT NULL
          AND start_line <= ?
          AND end_line >= ?
        ORDER BY (end_line - start_line) ASC, start_line DESC, id ASC
        """,
        (
            _snapshot_id_for_file(conn, anchor.file_id),
            anchor.file_id,
            anchor.node_id,
            anchor.line,
            anchor.line,
        ),
    ).fetchall()
    candidates: list[_Candidate] = []
    for row in rows[:1]:
        chunk = _chunk_for_node(conn, anchor.file_id, int(row["id"]))
        if chunk is not None:
            candidates.append(
                _chunk_candidate(
                    chunk,
                    f"enclosing.{row['kind']}",
                    f"enclosing {row['kind']}",
                    4.0,
                )
            )
            continue
        snippet = _source_snippet(
            repo,
            anchor.file_path,
            int(row["start_line"]),
            int(row["end_line"]),
            notes,
        )
        if snippet is None:
            notes.append(f"Enclosing {row['kind']} source could not be read.")
            continue
        notes.append(f"Enclosing {row['kind']} used source fallback.")
        candidates.append(
            _Candidate(
                kind=f"enclosing.{row['kind']}",
                file=snippet.file_path,
                line_range=(snippet.start_line, snippet.end_line),
                text=snippet.text,
                score=4.0,
                token_estimate=snippet.token_estimate,
                reason=f"enclosing {row['kind']}",
                confidence=float(row["confidence"]),
                extractor=str(row["extractor"]),
                required=True,
                metadata=_node_metadata(row),
            )
        )
    if candidates:
        return candidates
    file_candidate = _file_enclosing_candidate(conn, repo, anchor, notes)
    if file_candidate is None:
        return []
    return [file_candidate]


def _file_enclosing_candidate(
    conn: Any,
    repo: Path,
    anchor: AnchorResult,
    notes: list[str],
) -> _Candidate | None:
    chunk = conn.execute(
        """
        SELECT chunk.id, chunk.node_id, chunk.kind, chunk.start_line, chunk.end_line,
               chunk.text, chunk.token_estimate, NULL AS node_kind,
               NULL AS node_name, NULL AS qualified_name, NULL AS symbol_key,
               NULL AS confidence, NULL AS extractor, file.path AS file_path
        FROM chunk
        JOIN file ON file.id = chunk.file_id
        WHERE chunk.file_id = ? AND chunk.node_id IS NULL
        ORDER BY
          CASE
            WHEN chunk.kind = 'file' THEN 0
            ELSE 1
          END ASC,
          chunk.start_line ASC,
          chunk.id ASC
        LIMIT 1
        """,
        (anchor.file_id,),
    ).fetchone()
    if chunk is not None:
        return _chunk_candidate(chunk, "enclosing.file", "enclosing file", 3.5)

    snippet = _source_snippet(repo, anchor.file_path, anchor.line, anchor.line, notes)
    if snippet is None:
        notes.append("Enclosing file source could not be read.")
        return None
    notes.append("Enclosing file used source fallback.")
    return _Candidate(
        kind="enclosing.file",
        file=snippet.file_path,
        line_range=(snippet.start_line, snippet.end_line),
        text=snippet.text,
        score=3.5,
        token_estimate=snippet.token_estimate,
        reason="enclosing file",
        confidence=0.5,
        extractor=None,
        required=True,
    )


def _import_include_candidates(
    conn: Any, repo: Path, anchor: AnchorResult
) -> list[_Candidate]:
    source = _read_source(repo, anchor.file_path)
    rows = conn.execute(
        """
        SELECT id, role, text, start_line, end_line, confidence, extractor, metadata_json
        FROM occurrence
        WHERE file_id = ? AND role IN ('import', 'include')
        ORDER BY start_line ASC, id ASC
        """,
        (anchor.file_id,),
    ).fetchall()
    candidates: list[_Candidate] = []
    for row in rows:
        text = str(row["text"])
        start_line = int(row["start_line"])
        end_line = int(row["end_line"])
        if source is not None:
            try:
                snippet = snippet_by_line_range(
                    anchor.file_path, source, start_line, end_line
                )
                text = snippet.text
                start_line = snippet.start_line
                end_line = snippet.end_line
            except ValueError:
                pass
        candidates.append(
            _Candidate(
                kind=str(row["role"]),
                file=anchor.file_path,
                line_range=(start_line, end_line),
                text=text,
                score=3.0,
                token_estimate=estimate_token_count(text),
                reason=f"same-file {row['role']}",
                confidence=float(row["confidence"]),
                extractor=str(row["extractor"]),
                metadata={
                    "occurrence_id": int(row["id"]),
                    **_metadata(str(row["metadata_json"])),
                },
            )
        )
    return candidates


def _diagnostic_candidates(
    conn: Any,
    repo: Path,
    snapshot_id: int,
    anchor: AnchorResult,
    notes: list[str],
) -> list[_Candidate]:
    rows = conn.execute(
        """
        SELECT diagnostic.id, diagnostic.severity, diagnostic.code,
               diagnostic.message, diagnostic.extractor,
               diagnostic.metadata_json, diagnostic.start_line,
               diagnostic.end_line, file.id AS file_id, file.path AS file_path
        FROM diagnostic
        LEFT JOIN file ON file.id = diagnostic.file_id
        WHERE diagnostic.snapshot_id = ?
        ORDER BY
          CASE
            WHEN file.id = ? THEN 0
            ELSE 1
          END ASC,
          file.path ASC,
          diagnostic.start_line ASC,
          diagnostic.id ASC
        """,
        (snapshot_id, anchor.file_id),
    ).fetchall()
    candidates: list[_Candidate] = []
    for row in rows:
        file_path = None if row["file_path"] is None else str(row["file_path"])
        is_vendor = _is_vendor_path(file_path)
        start_line = None if row["start_line"] is None else int(row["start_line"])
        end_line = None if row["end_line"] is None else int(row["end_line"])
        line_range = _line_range(start_line, end_line)
        message = str(row["message"])
        text = message
        if file_path is not None and line_range is not None:
            snippet = _source_snippet(
                repo, file_path, line_range[0], line_range[1], notes
            )
            if snippet is not None:
                text = snippet.text
                line_range = (snippet.start_line, snippet.end_line)
        severity = str(row["severity"])
        code = None if row["code"] is None else str(row["code"])
        code_label = "" if code is None else f" {code}"
        candidates.append(
            _Candidate(
                kind="diagnostic.parser",
                file=file_path,
                line_range=line_range,
                text=text,
                score=_diagnostic_base_score(
                    row["file_id"] == anchor.file_id, is_vendor
                ),
                token_estimate=estimate_token_count(text),
                reason=f"parser diagnostic: {severity}{code_label}: {message}",
                confidence=_diagnostic_confidence(severity, is_vendor),
                extractor=str(row["extractor"]),
                metadata={
                    **_metadata(str(row["metadata_json"])),
                    "diagnostic_id": int(row["id"]),
                    "is_vendor": is_vendor,
                    "severity": severity,
                    "code": code,
                    "message": message,
                },
            )
        )
    return candidates


def _diagnostic_base_score(is_anchor_file: bool, is_vendor: bool) -> float:
    if is_vendor:
        return 0.8
    return 3.8 if is_anchor_file else 3.0


def _diagnostic_confidence(severity: str, is_vendor: bool) -> float:
    if is_vendor:
        return 0.3
    return 0.8 if severity == "error" else 0.6


def _relationship_candidates(
    conn: Any,
    repo: Path,
    anchor: AnchorResult,
    notes: list[str],
) -> list[_Candidate]:
    if anchor.node_id is None:
        return []
    rows = conn.execute(
        """
        SELECT edge.id AS edge_id, edge.kind AS edge_kind, edge.unresolved_dst,
               edge.confidence AS edge_confidence, edge.extractor AS edge_extractor,
               edge.metadata_json AS edge_metadata_json, dst.id AS dst_id,
               dst.kind AS dst_kind, dst.name AS dst_name,
               dst.qualified_name AS dst_qualified_name,
               dst.symbol_key AS dst_symbol_key, dst.file_id AS dst_file_id,
               dst.start_line AS dst_start_line, dst.end_line AS dst_end_line,
               dst.confidence AS dst_confidence, dst.extractor AS dst_extractor,
               file.path AS dst_file_path
        FROM edge
        LEFT JOIN node AS dst ON dst.id = edge.dst_node_id
        LEFT JOIN file ON file.id = dst.file_id
        WHERE edge.snapshot_id = ?
          AND edge.src_node_id = ?
          AND edge.kind IN ('calls', 'uses_type', 'references')
        ORDER BY
          CASE edge.kind
            WHEN 'calls' THEN 0
            WHEN 'uses_type' THEN 1
            WHEN 'references' THEN 2
            ELSE 3
          END ASC,
          edge.start_line ASC,
          edge.id ASC
        """,
        (_snapshot_id_for_file(conn, anchor.file_id), anchor.node_id),
    ).fetchall()
    candidates: list[_Candidate] = []
    for row in rows:
        if row["dst_id"] is None:
            unresolved = row["unresolved_dst"]
            if unresolved is not None:
                notes.append(
                    f"Unresolved {row['edge_kind']} relationship from target: "
                    f"{unresolved}."
                )
            continue
        candidate = _relationship_candidate(conn, repo, row, notes)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _relationship_candidate(
    conn: Any,
    repo: Path,
    row: Any,
    notes: list[str],
) -> _Candidate | None:
    reason = _relationship_reason(str(row["edge_kind"]))
    kind = _relationship_kind(str(row["edge_kind"]))
    score = _relationship_score(str(row["edge_kind"]))
    if row["dst_file_id"] is not None:
        chunk = _chunk_for_node(conn, int(row["dst_file_id"]), int(row["dst_id"]))
        if chunk is not None:
            return _relationship_from_chunk(chunk, row, kind, reason, score)
    if (
        row["dst_file_path"] is None
        or row["dst_start_line"] is None
        or row["dst_end_line"] is None
    ):
        return None
    snippet = _source_snippet(
        repo,
        str(row["dst_file_path"]),
        int(row["dst_start_line"]),
        int(row["dst_end_line"]),
        notes,
    )
    if snippet is None:
        return None
    notes.append(f"{reason.title()} used source fallback.")
    return _Candidate(
        kind=kind,
        file=snippet.file_path,
        line_range=(snippet.start_line, snippet.end_line),
        text=snippet.text,
        score=score,
        token_estimate=snippet.token_estimate,
        reason=reason,
        confidence=float(row["edge_confidence"]),
        extractor=str(row["edge_extractor"]),
        metadata={
            **_metadata(str(row["edge_metadata_json"])),
            "edge_id": int(row["edge_id"]),
            "edge_kind": str(row["edge_kind"]),
            "node_id": int(row["dst_id"]),
            "node_kind": str(row["dst_kind"]),
            "node_name": None if row["dst_name"] is None else str(row["dst_name"]),
            "qualified_name": None
            if row["dst_qualified_name"] is None
            else str(row["dst_qualified_name"]),
            "symbol_key": None
            if row["dst_symbol_key"] is None
            else str(row["dst_symbol_key"]),
        },
    )


def _incoming_call_candidates(
    conn: Any,
    repo: Path,
    anchor: AnchorResult,
    notes: list[str],
) -> list[_Candidate]:
    if anchor.node_id is None:
        return []
    rows = conn.execute(
        """
        SELECT edge.id AS edge_id, edge.kind AS edge_kind,
               edge.confidence AS edge_confidence, edge.extractor AS edge_extractor,
               edge.metadata_json AS edge_metadata_json, src.id AS src_id,
               src.kind AS src_kind, src.name AS src_name,
               src.qualified_name AS src_qualified_name,
               src.symbol_key AS src_symbol_key, src.file_id AS src_file_id,
               src.start_line AS src_start_line, src.end_line AS src_end_line,
               src.confidence AS src_confidence, src.extractor AS src_extractor,
               file.path AS src_file_path
        FROM edge
        JOIN node AS src ON src.id = edge.src_node_id
        LEFT JOIN file ON file.id = src.file_id
        WHERE edge.snapshot_id = ?
          AND edge.dst_node_id = ?
          AND edge.kind = 'calls'
        ORDER BY edge.start_line ASC, edge.id ASC
        """,
        (_snapshot_id_for_file(conn, anchor.file_id), anchor.node_id),
    ).fetchall()
    candidates: list[_Candidate] = []
    for row in rows:
        candidate = _incoming_call_candidate(conn, repo, row, notes)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _incoming_call_candidate(
    conn: Any,
    repo: Path,
    row: Any,
    notes: list[str],
) -> _Candidate | None:
    if row["src_file_id"] is not None:
        chunk = _chunk_for_node(conn, int(row["src_file_id"]), int(row["src_id"]))
        if chunk is not None:
            candidate = _relationship_from_chunk(
                chunk,
                row,
                "neighborhood.caller",
                "direct caller",
                3.6,
            )
            return _with_direction_metadata(candidate, "in")
    if (
        row["src_file_path"] is None
        or row["src_start_line"] is None
        or row["src_end_line"] is None
    ):
        return None
    snippet = _source_snippet(
        repo,
        str(row["src_file_path"]),
        int(row["src_start_line"]),
        int(row["src_end_line"]),
        notes,
    )
    if snippet is None:
        return None
    notes.append("Direct caller used source fallback.")
    return _Candidate(
        kind="neighborhood.caller",
        file=snippet.file_path,
        line_range=(snippet.start_line, snippet.end_line),
        text=snippet.text,
        score=3.6,
        token_estimate=snippet.token_estimate,
        reason="direct caller",
        confidence=float(row["edge_confidence"]),
        extractor=str(row["edge_extractor"]),
        metadata={
            **_metadata(str(row["edge_metadata_json"])),
            "direction": "in",
            "edge_id": int(row["edge_id"]),
            "edge_kind": str(row["edge_kind"]),
            "node_id": int(row["src_id"]),
            "node_kind": str(row["src_kind"]),
            "node_name": None if row["src_name"] is None else str(row["src_name"]),
            "qualified_name": None
            if row["src_qualified_name"] is None
            else str(row["src_qualified_name"]),
            "symbol_key": None
            if row["src_symbol_key"] is None
            else str(row["src_symbol_key"]),
        },
    )


def _with_direction_metadata(candidate: _Candidate, direction: str) -> _Candidate:
    return _Candidate(
        kind=candidate.kind,
        file=candidate.file,
        line_range=candidate.line_range,
        text=candidate.text,
        score=candidate.score,
        token_estimate=candidate.token_estimate,
        reason=candidate.reason,
        confidence=candidate.confidence,
        extractor=candidate.extractor,
        required=candidate.required,
        metadata={**candidate.metadata, "direction": direction},
        score_trace=candidate.score_trace,
    )


def _relationship_from_chunk(
    chunk: Any,
    edge: Any,
    kind: str,
    reason: str,
    score: float,
) -> _Candidate:
    candidate = _chunk_candidate(chunk, kind, reason, score)
    return _Candidate(
        kind=candidate.kind,
        file=candidate.file,
        line_range=candidate.line_range,
        text=candidate.text,
        score=candidate.score,
        token_estimate=candidate.token_estimate,
        reason=candidate.reason,
        confidence=min(candidate.confidence, float(edge["edge_confidence"])),
        extractor=str(edge["edge_extractor"]),
        metadata={
            **candidate.metadata,
            **_metadata(str(edge["edge_metadata_json"])),
            "edge_id": int(edge["edge_id"]),
            "edge_kind": str(edge["edge_kind"]),
        },
    )


def _relationship_kind(edge_kind: str) -> str:
    if edge_kind == "calls":
        return "neighborhood.callee"
    if edge_kind == "uses_type":
        return "neighborhood.type"
    return "neighborhood.reference"


def _relationship_reason(edge_kind: str) -> str:
    if edge_kind == "calls":
        return "direct callee"
    if edge_kind == "uses_type":
        return "referenced type"
    return "referenced field"


def _relationship_score(edge_kind: str) -> float:
    if edge_kind == "calls":
        return 3.4
    if edge_kind == "uses_type":
        return 3.2
    return 3.1


def _test_candidates(
    conn: Any,
    anchor: AnchorResult,
    selected_chunk_ids: set[int],
) -> list[_Candidate]:
    if anchor.node_name is None:
        return []
    needle = anchor.node_name.lower()
    rows = conn.execute(
        """
        SELECT chunk.id, chunk.node_id, chunk.kind, chunk.start_line, chunk.end_line,
               chunk.text, chunk.token_estimate, node.kind AS node_kind,
               node.name AS node_name, node.qualified_name, node.symbol_key,
               node.confidence, node.extractor, file.path AS file_path
        FROM chunk
        JOIN file ON file.id = chunk.file_id
        LEFT JOIN node ON node.id = chunk.node_id
        WHERE file.snapshot_id = ?
          AND (file.is_test = 1 OR lower(file.path) LIKE '%%test%%')
          AND (
            lower(file.path) LIKE ?
            OR lower(COALESCE(node.name, '')) LIKE ?
            OR lower(COALESCE(node.qualified_name, '')) LIKE ?
          )
        ORDER BY file.path ASC, chunk.start_line ASC, chunk.id ASC
        """,
        (
            _snapshot_id_for_file(conn, anchor.file_id),
            f"%{needle}%",
            f"%{needle}%",
            f"%{needle}%",
        ),
    ).fetchall()
    return [
        _chunk_candidate(row, "test.related", "related test", 2.8)
        for row in rows
        if int(row["id"]) not in selected_chunk_ids
    ]


def _sibling_candidates(
    conn: Any,
    anchor: AnchorResult,
    selected_chunk_ids: set[int],
) -> list[_Candidate]:
    rows = conn.execute(
        """
        SELECT chunk.id, chunk.node_id, chunk.kind, chunk.start_line, chunk.end_line,
               chunk.text, chunk.token_estimate, node.kind AS node_kind,
               node.name AS node_name, node.qualified_name, node.symbol_key,
               node.confidence, node.extractor, file.path AS file_path
        FROM chunk
        JOIN file ON file.id = chunk.file_id
        LEFT JOIN node ON node.id = chunk.node_id
        WHERE chunk.file_id = ?
        ORDER BY
          CASE
            WHEN chunk.end_line < ? THEN ? - chunk.end_line
            WHEN chunk.start_line > ? THEN chunk.start_line - ?
            ELSE 0
          END ASC,
          chunk.start_line ASC,
          chunk.id ASC
        """,
        (
            anchor.file_id,
            anchor.line,
            anchor.line,
            anchor.line,
            anchor.line,
        ),
    ).fetchall()
    return [
        _chunk_candidate(row, "sibling.definition", "same-file sibling", 1.5)
        for row in rows
        if int(row["id"]) not in selected_chunk_ids
    ]


def _select_candidates(
    required: list[_Candidate], optional: list[_Candidate], budget: int, *, goal: str
) -> tuple[list[_Candidate], list[OmittedItem]]:
    selected = list(required)
    used_tokens = sum(candidate.token_estimate for candidate in selected)
    selected_ranges = [
        range_key
        for candidate in selected
        if (range_key := _candidate_range_key(candidate)) is not None
    ]
    omitted: list[OmittedItem] = []
    for candidate in sorted(
        optional, key=lambda candidate: _budget_sort_key(candidate, goal)
    ):
        range_key = _candidate_range_key(candidate)
        if (
            range_key is not None
            and not candidate.kind.startswith("diagnostic.")
            and _is_redundant_range(range_key, selected_ranges, goal=goal)
        ):
            omitted.append(
                OmittedItem(
                    name=_candidate_name(candidate),
                    reason="overlap",
                    score=candidate.score,
                )
            )
            continue
        if _should_skip_vendor_diagnostic(candidate, omitted):
            omitted.append(
                OmittedItem(
                    name=_candidate_name(candidate),
                    reason="budget",
                    score=candidate.score,
                )
            )
            continue
        if used_tokens + candidate.token_estimate <= budget:
            selected.append(candidate)
            used_tokens += candidate.token_estimate
            if range_key is not None and not candidate.kind.startswith("diagnostic."):
                selected_ranges.append(range_key)
        else:
            omitted.append(
                OmittedItem(
                    name=_candidate_name(candidate),
                    reason="budget",
                    score=candidate.score,
                )
            )
    return selected, omitted


def _should_skip_vendor_diagnostic(
    candidate: _Candidate, omitted: list[OmittedItem]
) -> bool:
    return (
        candidate.kind.startswith("diagnostic.")
        and candidate.metadata.get("is_vendor") is True
        and any(
            item.reason == "budget" and not _is_vendor_path(item.name)
            for item in omitted
        )
    )


def _compact_large_required_enclosing_candidates(
    candidates: list[_Candidate],
    budget: int,
    notes: list[str],
    trace: list[dict[str, Any]],
) -> list[_Candidate]:
    token_limit = max(250, budget // 3)
    compacted: list[_Candidate] = []
    for candidate in candidates:
        if (
            not candidate.required
            or not candidate.kind.startswith("enclosing.")
            or candidate.token_estimate <= token_limit
        ):
            compacted.append(candidate)
            continue
        compacted_candidate = _compact_candidate(candidate, token_limit)
        compacted.append(compacted_candidate)
        notes.append(
            f"{candidate.kind} was compacted from "
            f"{candidate.token_estimate} to {compacted_candidate.token_estimate} "
            "estimated tokens to preserve budget for local context."
        )
        trace.append(
            {
                "stage": "compact",
                "kind": candidate.kind,
                "file": candidate.file,
                "original_tokens": candidate.token_estimate,
                "tokens": compacted_candidate.token_estimate,
            }
        )
    return compacted


def _compact_candidate(candidate: _Candidate, token_limit: int) -> _Candidate:
    text = _compact_text(candidate.text, token_limit)
    return _Candidate(
        kind=candidate.kind,
        file=candidate.file,
        line_range=candidate.line_range,
        text=text,
        score=candidate.score,
        token_estimate=estimate_token_count(text),
        reason=candidate.reason,
        confidence=candidate.confidence,
        extractor=candidate.extractor,
        required=candidate.required,
        metadata={
            **candidate.metadata,
            "compacted": True,
            "original_token_estimate": candidate.token_estimate,
        },
        score_trace=candidate.score_trace,
    )


def _compact_text(text: str, token_limit: int) -> str:
    lines = text.splitlines(keepends=True)
    marker = "\n... omitted remainder from compacted enclosing context ...\n"
    max_chars = max(1, token_limit * 4 - len(marker))
    if len(lines) <= 2:
        return text[:max_chars].rstrip() + marker

    kept_lines: list[str] = []
    for line in lines:
        candidate_text = "".join([*kept_lines, line]).rstrip() + marker
        if estimate_token_count(candidate_text) > token_limit:
            break
        kept_lines.append(line)
    omitted_line_count = max(0, len(lines) - len(kept_lines))
    if omitted_line_count == 0:
        return text
    if not kept_lines:
        return text[:max_chars].rstrip() + marker
    return (
        "".join(kept_lines).rstrip()
        + f"\n... omitted {omitted_line_count} lines from compacted enclosing context ...\n"
    )


def _budget_sort_key(
    candidate: _Candidate, goal: str
) -> tuple[float, float, str, int, int]:
    effective_score = candidate.score
    if goal == "failure-modes" and candidate.kind.startswith("diagnostic."):
        effective_score += -5.0 if candidate.metadata.get("is_vendor") is True else 5.0
    ratio = effective_score / max(candidate.token_estimate, 1)
    start_line, end_line = candidate.line_range or (0, 0)
    return (-ratio, -effective_score, candidate.file or "", start_line, end_line)


def _candidate_range_key(candidate: _Candidate) -> tuple[str, int, int] | None:
    if candidate.file is None or candidate.line_range is None:
        return None
    start_line, end_line = candidate.line_range
    return candidate.file, start_line, end_line


def _is_redundant_range(
    candidate: tuple[str, int, int],
    selected: list[tuple[str, int, int]],
    *,
    goal: str,
) -> bool:
    candidate_file, candidate_start, candidate_end = candidate
    for selected_file, selected_start, selected_end in selected:
        if candidate_file != selected_file:
            continue
        if (
            goal == "explain"
            and candidate_start <= selected_end
            and selected_start <= candidate_end
        ):
            return True
        if candidate_start <= selected_start and candidate_end >= selected_end:
            return True
    return False


def _score_candidates(
    candidates: list[_Candidate],
    anchor: AnchorResult,
    query: dict[str, Any],
) -> list[_Candidate]:
    ranking_anchor = RankingAnchor(
        file_path=anchor.file_path,
        line=anchor.line,
        node_name=anchor.node_name,
        qualified_name=anchor.qualified_name,
        symbol_key=anchor.symbol_key,
    )
    query_text = _query_text(query)
    scored: list[_Candidate] = []
    for candidate in candidates:
        result = score_candidate(
            RankingCandidate(
                kind=candidate.kind,
                file_path=candidate.file,
                line_range=candidate.line_range,
                text=candidate.text,
                token_estimate=candidate.token_estimate,
                confidence=candidate.confidence,
                metadata=candidate.metadata,
            ),
            ranking_anchor,
            query_text=query_text,
            goal=str(query.get("goal", "explain")),
        )
        scored.append(
            _Candidate(
                kind=candidate.kind,
                file=candidate.file,
                line_range=candidate.line_range,
                text=candidate.text,
                score=result.score,
                token_estimate=candidate.token_estimate,
                reason=candidate.reason,
                confidence=candidate.confidence,
                extractor=candidate.extractor,
                required=candidate.required,
                metadata=candidate.metadata,
                score_trace=result.score_trace,
            )
        )
    return scored


def _query_text(query: dict[str, Any]) -> str | None:
    symbol = query.get("symbol")
    if symbol is not None:
        return str(symbol)
    file_path = query.get("file")
    if file_path is not None:
        return str(file_path)
    return None


def _chunk_for_node(conn: Any, file_id: int, node_id: int) -> Any:
    return conn.execute(
        """
        SELECT chunk.id, chunk.node_id, chunk.kind, chunk.start_line, chunk.end_line,
               chunk.text, chunk.token_estimate, node.kind AS node_kind,
               node.name AS node_name, node.qualified_name, node.symbol_key,
               node.confidence, node.extractor, file.path AS file_path
        FROM chunk
        JOIN file ON file.id = chunk.file_id
        JOIN node ON node.id = chunk.node_id
        WHERE chunk.file_id = ? AND chunk.node_id = ?
        ORDER BY chunk.start_line ASC, chunk.id ASC
        LIMIT 1
        """,
        (file_id, node_id),
    ).fetchone()


def _chunk_candidate(row: Any, kind: str, reason: str, score: float) -> _Candidate:
    return _Candidate(
        kind=kind,
        file=None if row["start_line"] is None else _file_path_for_chunk_row(row),
        line_range=_line_range(int(row["start_line"]), int(row["end_line"])),
        text=str(row["text"]),
        score=score,
        token_estimate=int(row["token_estimate"]),
        reason=reason,
        confidence=0.7 if row["confidence"] is None else float(row["confidence"]),
        extractor=None if row["extractor"] is None else str(row["extractor"]),
        required=kind.startswith(("target.", "enclosing.")),
        metadata={
            "chunk_id": int(row["id"]),
            "node_id": None if row["node_id"] is None else int(row["node_id"]),
            "node_kind": None if row["node_kind"] is None else str(row["node_kind"]),
            "node_name": None if row["node_name"] is None else str(row["node_name"]),
            "qualified_name": None
            if row["qualified_name"] is None
            else str(row["qualified_name"]),
            "symbol_key": None if row["symbol_key"] is None else str(row["symbol_key"]),
        },
    )


def _file_path_for_chunk_row(row: Any) -> str | None:
    if "file_path" in set(row.keys()):
        return None if row["file_path"] is None else str(row["file_path"])
    return None


def _snapshot_id_for_file(conn: Any, file_id: int) -> int:
    row = conn.execute(
        "SELECT snapshot_id FROM file WHERE id = ?", (file_id,)
    ).fetchone()
    return int(row["snapshot_id"])


def _source_snippet(
    repo: Path,
    file_path: str,
    start_line: int,
    end_line: int,
    notes: list[str],
) -> Any:
    source = _read_source(repo, file_path, notes)
    if source is None:
        return None
    try:
        return snippet_by_line_range(file_path, source, start_line, end_line)
    except ValueError:
        notes.append(f"Indexed line range is outside source bounds for {file_path}.")
        return None


def _is_vendor_path(file_path: str | None) -> bool:
    if file_path is None:
        return False
    return bool({part.lower() for part in Path(file_path).parts} & VENDOR_PATH_HINTS)


def _read_source(
    repo: Path, file_path: str, notes: list[str] | None = None
) -> str | None:
    path = repo / file_path
    if not path.exists():
        return None
    content = path.read_bytes()
    validation = validate_source_bytes(file_path, content)
    if not validation.ok:
        if notes is not None:
            notes.extend(issue.message for issue in validation.issues)
        return None
    return content.decode("utf-8")


def _selected_chunk_ids(candidates: list[_Candidate]) -> set[int]:
    return {
        int(candidate.metadata["chunk_id"])
        for candidate in candidates
        if candidate.metadata.get("chunk_id") is not None
    }


def _line_range(start_line: int | None, end_line: int | None) -> tuple[int, int] | None:
    if start_line is None or end_line is None:
        return None
    return start_line, end_line


def _node_metadata(row: Any) -> dict[str, Any]:
    return {
        "node_id": int(row["id"]),
        "node_kind": str(row["kind"]),
        "node_name": None if row["name"] is None else str(row["name"]),
        "qualified_name": None
        if row["qualified_name"] is None
        else str(row["qualified_name"]),
        "symbol_key": None if row["symbol_key"] is None else str(row["symbol_key"]),
    }


def _anchor_dict(anchor: AnchorResult) -> dict[str, Any]:
    return {
        "file": anchor.file_path,
        "line": anchor.line,
        "node_id": anchor.node_id,
        "node_kind": anchor.node_kind,
        "node_name": anchor.node_name,
        "qualified_name": anchor.qualified_name,
        "symbol_key": anchor.symbol_key,
        "chunk_id": anchor.chunk_id,
    }


def _metadata(value: str) -> dict[str, Any]:
    decoded = loads(value)
    if isinstance(decoded, dict):
        return decoded
    return {}


def _candidate_name(candidate: _Candidate) -> str | None:
    if candidate.file is None or candidate.line_range is None:
        return candidate.kind
    start_line, end_line = candidate.line_range
    if start_line == end_line:
        return f"{candidate.file}:{start_line}"
    return f"{candidate.file}:{start_line}-{end_line}"
