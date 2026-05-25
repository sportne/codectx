from __future__ import annotations

import sqlite3
from pathlib import Path

import codectx.graph.query as graph_query
from codectx.frontends.base import ChunkFact, EdgeFact, NodeFact
from codectx.graph.query import (
    get_edge_detail,
    get_node_detail,
    search,
    search_chunks_like,
    search_symbols,
)
from codectx.graph.store import GraphStore
from codectx.scanner.models import FileRecord
from codectx.source.spans import SourceSpan


def test_search_symbols_ranks_exact_prefix_substring_and_path_matches(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_symbols(store, tmp_path)

        results = search_symbols(store.conn, snapshot_id, "PaymentService")

    assert [result.name for result in results] == [
        "PaymentService",
        "PaymentServiceTest",
        "authorizePayment",
        "Gateway",
    ]
    assert [result.score for result in results] == [100, 80, 60, 40]
    exact = results[0]
    assert exact.kind == "type"
    assert exact.language == "java"
    assert exact.qualified_name == "acme.PaymentService"
    assert exact.symbol_key == "java:src/PaymentService.java#PaymentService"
    assert exact.file_path == "src/PaymentService.java"
    assert exact.start_line == 1
    assert exact.end_line == 3
    assert exact.confidence == 1.0
    assert exact.extractor == "test"


def test_search_symbols_is_case_insensitive_and_limited(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_symbols(store, tmp_path)

        results = search_symbols(store.conn, snapshot_id, "payment", limit=2)

    assert [result.name for result in results] == [
        "PaymentService",
        "PaymentServiceTest",
    ]


def test_search_symbols_returns_empty_for_blank_or_missing_query(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_symbols(store, tmp_path)

        assert search_symbols(store.conn, snapshot_id, " ") == []
        assert search_symbols(store.conn, snapshot_id, "Nope") == []


def test_search_symbols_treats_like_wildcards_as_literal_text(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_symbols(store, tmp_path)

        underscore_results = search_symbols(store.conn, snapshot_id, "_")
        percent_results = search_symbols(store.conn, snapshot_id, "%")

    assert [result.name for result in underscore_results] == ["gateway_helper"]
    assert [result.name for result in percent_results] == ["Percent%Helper"]


def test_search_chunks_like_returns_matching_chunks(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_symbols(store, tmp_path)

        results = search_chunks_like(store.conn, snapshot_id, "authorize")

    assert len(results) == 1
    assert results[0].file_path == "src/PaymentService.java"
    assert results[0].start_line == 1
    assert "authorizePayment" in results[0].text


def test_search_uses_like_when_fts_tables_are_absent(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_symbols(store, tmp_path)

        result = search(store.conn, snapshot_id, "authorize")

    assert result.used_fts is False
    assert [symbol.name for symbol in result.symbols] == ["authorizePayment"]
    assert [chunk.file_path for chunk in result.chunks] == ["src/PaymentService.java"]


def test_configure_fts_populates_optional_tables_when_available(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_symbols(store, tmp_path)

        enabled = store.configure_fts(snapshot_id)
        result = search(store.conn, snapshot_id, "authorize")

    with GraphStore(db_path) as probe_store:
        expected_enabled = probe_store.has_fts5()

    assert enabled is expected_enabled
    if enabled:
        assert result.used_fts is True
        assert [symbol.name for symbol in result.symbols] == ["authorizePayment"]
        assert [chunk.file_path for chunk in result.chunks] == [
            "src/PaymentService.java"
        ]


def test_configure_fts_returns_false_when_fts_is_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_symbols(store, tmp_path)
        monkeypatch.setattr(GraphStore, "has_fts5", lambda _store: False)

        enabled = store.configure_fts(snapshot_id)
        fts_tables = store.conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name IN ('symbol_fts', 'chunk_fts')
            """
        ).fetchall()

    assert enabled is False
    assert fts_tables == []


def test_search_falls_back_to_like_when_fts_query_fails(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_symbols(store, tmp_path)
        if not store.configure_fts(snapshot_id):
            return

        def raise_fts_error(*_args, **_kwargs):
            raise sqlite3.OperationalError("simulated missing fts")

        monkeypatch.setattr(graph_query, "_search_symbols_fts", raise_fts_error)
        result = search(store.conn, snapshot_id, "authorize")

    assert result.used_fts is False
    assert [symbol.name for symbol in result.symbols] == ["authorizePayment"]
    assert [chunk.file_path for chunk in result.chunks] == ["src/PaymentService.java"]


def test_get_node_detail_returns_stable_inspection_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_symbols(store, tmp_path)
        node_id = store.conn.execute(
            "SELECT id FROM node WHERE name = 'PaymentService'"
        ).fetchone()["id"]

        detail = get_node_detail(store.conn, snapshot_id, int(node_id))

    assert detail is not None
    assert detail.kind == "type"
    assert detail.language == "java"
    assert detail.name == "PaymentService"
    assert detail.qualified_name == "acme.PaymentService"
    assert detail.symbol_key == "java:src/PaymentService.java#PaymentService"
    assert detail.file_path == "src/PaymentService.java"
    assert detail.start_byte == 0
    assert detail.end_byte == 10
    assert detail.start_line == 1
    assert detail.end_line == 3
    assert detail.confidence == 1.0
    assert detail.extractor == "test"
    assert detail.metadata == {"visibility": "public"}


def test_get_edge_detail_returns_resolved_and_unresolved_endpoints(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_symbols(store, tmp_path)
        edge_id = store.conn.execute(
            "SELECT id FROM edge WHERE unresolved_dst = 'acme.Missing'"
        ).fetchone()["id"]

        detail = get_edge_detail(store.conn, snapshot_id, int(edge_id))

    assert detail is not None
    assert detail.kind == "calls"
    assert detail.source is not None
    assert detail.source.qualified_name == "acme.Authorizer.authorizePayment"
    assert detail.destination is None
    assert detail.unresolved_dst == "acme.Missing"
    assert detail.file_path == "src/PaymentService.java"
    assert detail.start_line == 1
    assert detail.end_line == 3
    assert detail.confidence == 0.7
    assert detail.weight == 0.5
    assert detail.extractor == "test"
    assert detail.metadata == {"reason": "fixture"}


def test_get_inspection_detail_returns_none_for_missing_ids(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_symbols(store, tmp_path)

        node_detail = get_node_detail(store.conn, snapshot_id, 9999)
        edge_detail = get_edge_detail(store.conn, snapshot_id, 9999)

    assert node_detail is None
    assert edge_detail is None


def _seed_symbols(store: GraphStore, repo: Path) -> int:
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    files = [
        FileRecord(
            path="src/PaymentService.java",
            language="java",
            content_hash="abc123",
            size_bytes=100,
            line_count=10,
        ),
        FileRecord(
            path="src/PaymentService/Gateway.java",
            language="java",
            content_hash="def456",
            size_bytes=80,
            line_count=8,
        ),
        FileRecord(
            path="src/Gateway.cpp",
            language="cpp",
            content_hash="ghi789",
            size_bytes=40,
            line_count=4,
        ),
        FileRecord(
            path="src/Percent.cpp",
            language="cpp",
            content_hash="jkl012",
            size_bytes=40,
            line_count=4,
        ),
    ]
    file_ids = store.insert_files(snapshot_id, files)
    span = SourceSpan(
        file_path="src/PaymentService.java",
        start_byte=0,
        end_byte=10,
        start_line=1,
        start_col=0,
        end_line=3,
        end_col=1,
    )
    node_ids = store.insert_nodes(
        snapshot_id,
        [
            NodeFact(
                kind="type",
                language="java",
                name="PaymentService",
                qualified_name="acme.PaymentService",
                symbol_key="java:src/PaymentService.java#PaymentService",
                file_path="src/PaymentService.java",
                span=span,
                confidence=1.0,
                extractor="test",
                metadata={"visibility": "public"},
            ),
            NodeFact(
                kind="type",
                language="java",
                name="PaymentServiceTest",
                qualified_name="acme.PaymentServiceTest",
                symbol_key="java:src/PaymentService.java#PaymentServiceTest",
                file_path="src/PaymentService.java",
                span=span,
                confidence=1.0,
                extractor="test",
                metadata={},
            ),
            NodeFact(
                kind="callable",
                language="java",
                name="authorizePayment",
                qualified_name="acme.Authorizer.authorizePayment",
                symbol_key="java:src/PaymentService.java#Authorizer.authorizePayment",
                file_path="src/PaymentService.java",
                span=span,
                confidence=1.0,
                extractor="test",
                metadata={},
            ),
            NodeFact(
                kind="type",
                language="java",
                name="Gateway",
                qualified_name="acme.Gateway",
                symbol_key="java:src/Gateway.java#Gateway",
                file_path="src/PaymentService/Gateway.java",
                span=span,
                confidence=1.0,
                extractor="test",
                metadata={},
            ),
            NodeFact(
                kind="callable",
                language="cpp",
                name="gateway_helper",
                qualified_name="acme.gateway_helper",
                symbol_key="cpp:src/Gateway.cpp#gateway_helper()",
                file_path="src/Gateway.cpp",
                span=span,
                confidence=1.0,
                extractor="test",
                metadata={},
            ),
            NodeFact(
                kind="callable",
                language="cpp",
                name="Percent%Helper",
                qualified_name="acme.Percent%Helper",
                symbol_key="cpp:src/Percent.cpp#Percent%Helper()",
                file_path="src/Percent.cpp",
                span=span,
                confidence=1.0,
                extractor="test",
                metadata={},
            ),
        ],
        file_ids,
    )
    store.insert_edges(
        snapshot_id,
        [
            EdgeFact(
                kind="calls",
                src_key="java:src/PaymentService.java#Authorizer.authorizePayment",
                dst_key=None,
                unresolved_src=None,
                unresolved_dst="acme.Missing",
                file_path="src/PaymentService.java",
                span=span,
                confidence=0.7,
                extractor="test",
                weight=0.5,
                metadata={"reason": "fixture"},
            )
        ],
        file_ids,
        node_ids,
    )
    store.insert_chunks(
        [
            ChunkFact(
                file_path="src/PaymentService.java",
                node_key="java:src/PaymentService.java#Authorizer.authorizePayment",
                kind="definition",
                start_line=1,
                end_line=3,
                text="void authorizePayment() {}",
                token_estimate=6,
                metadata={},
            )
        ],
        file_ids,
        node_ids,
    )
    return snapshot_id
