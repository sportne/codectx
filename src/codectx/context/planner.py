"""Initial context bundle planning for explain requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from json import loads
from pathlib import Path
from typing import Any

from codectx.context.anchors import AnchorResult
from codectx.context.bundle import ContextBundle, ContextItem, OmittedItem
from codectx.source.snippets import snippet_by_line_range
from codectx.source.tokens import estimate_token_count


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
    """Build a deterministic v0 explain bundle for an anchor."""
    repo_path = Path(repo)
    notes = list(uncertainty_notes or [])
    trace: list[dict[str, Any]] = [
        {"stage": "anchor", "file": anchor.file_path, "line": anchor.line}
    ]

    candidates: list[_Candidate] = []
    target = _target_candidate(conn, repo_path, anchor, notes)
    if target is not None:
        candidates.append(target)
        trace.append({"stage": "candidate", "kind": target.kind, "required": True})
    enclosing = _enclosing_candidates(conn, repo_path, anchor, notes)
    candidates.extend(enclosing)
    for candidate in enclosing:
        trace.append({"stage": "candidate", "kind": candidate.kind, "required": True})

    optional_candidates = [
        *_import_include_candidates(conn, repo_path, anchor),
        *_sibling_candidates(conn, anchor, _selected_chunk_ids(candidates)),
    ]
    trace.append({"stage": "candidates", "optional_count": len(optional_candidates)})

    selected, omitted = _select_candidates(candidates, optional_candidates, budget)
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
        )
        for rank, candidate in enumerate(selected, start=1)
    ]

    return ContextBundle(
        query=query or {"goal": "explain", "budget": budget},
        anchor=_anchor_dict(anchor),
        index_health=dict(sorted(index_health.items())),
        items=items,
        omitted=omitted,
        uncertainty_notes=notes,
        trace=trace,
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
    required: list[_Candidate], optional: list[_Candidate], budget: int
) -> tuple[list[_Candidate], list[OmittedItem]]:
    selected = list(required)
    used_tokens = sum(candidate.token_estimate for candidate in selected)
    omitted: list[OmittedItem] = []
    for candidate in optional:
        if used_tokens + candidate.token_estimate <= budget:
            selected.append(candidate)
            used_tokens += candidate.token_estimate
        else:
            omitted.append(
                OmittedItem(
                    name=_candidate_name(candidate),
                    reason="budget",
                    score=candidate.score,
                )
            )
    return selected, omitted


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
    source = _read_source(repo, file_path)
    if source is None:
        return None
    try:
        return snippet_by_line_range(file_path, source, start_line, end_line)
    except ValueError:
        notes.append(f"Indexed line range is outside source bounds for {file_path}.")
        return None


def _read_source(repo: Path, file_path: str) -> str | None:
    path = repo / file_path
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


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
