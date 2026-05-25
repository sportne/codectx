from __future__ import annotations

from pathlib import Path

from codectx.context.anchors import (
    AnchorError,
    AnchorResult,
    resolve_file_line_anchor,
)
from codectx.frontends.base import ChunkFact, NodeFact
from codectx.graph.store import GraphStore
from codectx.scanner.models import FileRecord
from codectx.source.spans import SourceSpan


def test_resolve_file_line_anchor_prefers_smallest_callable_node(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_anchor_graph(store, tmp_path)

        result = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/PaymentService.java", 4
        )

    assert isinstance(result, AnchorResult)
    assert result.file_path == "src/PaymentService.java"
    assert result.line == 4
    assert result.node_kind == "callable"
    assert result.node_name == "authorize"
    assert result.qualified_name == "acme.PaymentService.authorize()"
    assert result.start_line == 3
    assert result.end_line == 5
    assert result.chunk_kind == "definition"
    assert result.chunk_start_line == 3
    assert result.chunk_end_line == 5
    assert result.chunk_text == "  boolean authorize() {\n    return true;\n  }"


def test_resolve_file_line_anchor_resolves_enclosing_type(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_anchor_graph(store, tmp_path)

        result = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/PaymentService.java", 2
        )

    assert isinstance(result, AnchorResult)
    assert result.node_kind == "type"
    assert result.node_name == "PaymentService"


def test_resolve_file_line_anchor_returns_file_anchor_with_chunk_without_node(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_anchor_graph(store, tmp_path)

        result = resolve_file_line_anchor(store.conn, snapshot_id, "src/README.java", 1)

    assert isinstance(result, AnchorResult)
    assert result.file_path == "src/README.java"
    assert result.node_id is None
    assert result.node_kind is None
    assert result.chunk_kind == "file"
    assert result.chunk_start_line == 1
    assert result.chunk_end_line == 1
    assert result.chunk_text == "read me"


def test_resolve_file_line_anchor_returns_nearest_chunk_without_node(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_anchor_graph(store, tmp_path)

        result = resolve_file_line_anchor(store.conn, snapshot_id, "src/Notes.java", 5)

    assert isinstance(result, AnchorResult)
    assert result.file_path == "src/Notes.java"
    assert result.node_id is None
    assert result.chunk_kind == "note"
    assert result.chunk_start_line == 2
    assert result.chunk_end_line == 3


def test_resolve_file_line_anchor_reports_invalid_line(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_anchor_graph(store, tmp_path)

        result = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/PaymentService.java", 0
        )

    assert isinstance(result, AnchorError)
    assert "Line number must be 1 or greater" in result.message


def test_resolve_file_line_anchor_reports_missing_file(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_anchor_graph(store, tmp_path)

        result = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/Missing.java", 1
        )

    assert isinstance(result, AnchorError)
    assert "File is not indexed" in result.message


def test_resolve_file_line_anchor_reports_line_outside_file(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_anchor_graph(store, tmp_path)

        result = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/PaymentService.java", 99
        )

    assert isinstance(result, AnchorError)
    assert "outside indexed file" in result.message


def _seed_anchor_graph(store: GraphStore, repo: Path) -> int:
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    file_ids = store.insert_files(
        snapshot_id,
        [
            FileRecord(
                path="src/PaymentService.java",
                language="java",
                content_hash="abc123",
                size_bytes=100,
                line_count=7,
            ),
            FileRecord(
                path="src/README.java",
                language="java",
                content_hash="def456",
                size_bytes=10,
                line_count=1,
            ),
            FileRecord(
                path="src/Notes.java",
                language="java",
                content_hash="ghi789",
                size_bytes=50,
                line_count=5,
            ),
        ],
    )
    node_ids = store.insert_nodes(
        snapshot_id,
        [
            _node(
                "type",
                "PaymentService",
                "acme.PaymentService",
                "java:src/PaymentService.java#PaymentService",
                1,
                7,
            ),
            _node(
                "callable",
                "authorize",
                "acme.PaymentService.authorize()",
                "java:src/PaymentService.java#PaymentService.authorize()",
                3,
                5,
            ),
        ],
        file_ids,
    )
    store.insert_chunks(
        [
            ChunkFact(
                file_path="src/PaymentService.java",
                node_key="java:src/PaymentService.java#PaymentService.authorize()",
                kind="definition",
                start_line=3,
                end_line=5,
                text="  boolean authorize() {\n    return true;\n  }",
                token_estimate=12,
            ),
            ChunkFact(
                file_path="src/README.java",
                node_key=None,
                kind="file",
                start_line=1,
                end_line=1,
                text="read me",
                token_estimate=2,
            ),
            ChunkFact(
                file_path="src/Notes.java",
                node_key=None,
                kind="note",
                start_line=2,
                end_line=3,
                text="note line 2\nnote line 3",
                token_estimate=6,
            ),
        ],
        file_ids,
        node_ids,
    )
    return snapshot_id


def _node(
    kind: str,
    name: str,
    qualified_name: str,
    symbol_key: str,
    start_line: int,
    end_line: int,
) -> NodeFact:
    return NodeFact(
        kind=kind,
        language="java",
        name=name,
        qualified_name=qualified_name,
        symbol_key=symbol_key,
        file_path="src/PaymentService.java",
        span=SourceSpan(
            file_path="src/PaymentService.java",
            start_byte=0,
            end_byte=10,
            start_line=start_line,
            start_col=0,
            end_line=end_line,
            end_col=1,
        ),
        confidence=1.0,
        extractor="test",
        metadata={},
    )
