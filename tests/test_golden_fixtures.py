from __future__ import annotations

import json
import shutil
from pathlib import Path

from codectx.contexting import ContextResult, build_context
from codectx.graph.store import GraphStore
from codectx.indexing import IndexResult, run_index

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_java_basic_golden_graph_and_context(tmp_path: Path) -> None:
    repo = _copy_fixture("java_basic", tmp_path)
    db_path = tmp_path / "graph.sqlite"

    result = run_index(repo, db_path=db_path)

    assert isinstance(result, IndexResult)
    assert _normalize_graph(db_path, result) == _load_json(
        "java_basic/expected_graph.json"
    )
    assert _normalize_context(repo, db_path, "explain") == _load_json(
        "java_basic/expected_context_explain.json"
    )
    assert _normalize_context(repo, db_path, "failure-modes") == _load_json(
        "java_basic/expected_context_failure_modes.json"
    )


def _copy_fixture(name: str, tmp_path: Path) -> Path:
    source = FIXTURE_DIR / name
    destination = tmp_path / name
    shutil.copytree(source, destination)
    return destination


def _normalize_graph(db_path: Path, result: IndexResult) -> dict[str, object]:
    with GraphStore(db_path) as store:
        nodes = [
            {
                "kind": str(row["kind"]),
                "name": str(row["name"]),
                "symbol_key": str(row["symbol_key"]),
            }
            for row in store.conn.execute(
                """
                SELECT node.kind, node.name, node.symbol_key
                FROM node
                WHERE node.snapshot_id = ?
                ORDER BY node.symbol_key
                """,
                (result.snapshot_id,),
            ).fetchall()
        ]
        edges = [
            {
                "dst": None if row["dst"] is None else str(row["dst"]),
                "kind": str(row["kind"]),
                "src": None if row["src"] is None else str(row["src"]),
                "unresolved": (
                    None if row["unresolved"] is None else str(row["unresolved"])
                ),
            }
            for row in store.conn.execute(
                """
                SELECT edge.kind, src.symbol_key AS src, dst.symbol_key AS dst,
                       edge.unresolved_dst AS unresolved
                FROM edge
                LEFT JOIN node AS src ON src.id = edge.src_node_id
                LEFT JOIN node AS dst ON dst.id = edge.dst_node_id
                WHERE edge.snapshot_id = ?
                ORDER BY edge.kind, src, dst, edge.unresolved_dst,
                         edge.start_line, edge.id
                """,
                (result.snapshot_id,),
            ).fetchall()
        ]
    return {
        "edges": edges,
        "nodes": nodes,
        "stats": {
            key: value
            for key, value in sorted(result.stats.items())
            if key != "feature.fts5"
        },
    }


def _normalize_context(repo: Path, db_path: Path, goal: str) -> dict[str, object]:
    result = build_context(
        repo,
        db_path=db_path,
        symbol="authorize",
        goal=goal,
        output_format="json",
    )
    assert isinstance(result, ContextResult)
    rendered = json.loads(result.rendered_text)
    return {
        "anchor": {
            "file": rendered["anchor"]["file"],
            "node_name": rendered["anchor"]["node_name"],
            "qualified_name": rendered["anchor"]["qualified_name"],
        },
        "goal": rendered["query"]["goal"],
        "items": [
            {
                "edge_kind": item["metadata"].get("edge_kind"),
                "file": item["file"],
                "kind": item["kind"],
                "line_range": item["line_range"],
                "node_name": item["metadata"].get("node_name"),
                "reason": item["reason"],
            }
            for item in rendered["items"]
        ],
        "uncertainty_notes": rendered["uncertainty_notes"],
    }


def _load_json(relative_path: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / relative_path).read_text(encoding="utf-8"))
