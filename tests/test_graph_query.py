from __future__ import annotations

from pathlib import Path

from codectx.frontends.base import NodeFact
from codectx.graph.query import search_symbols
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
    store.insert_nodes(
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
                metadata={},
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
    return snapshot_id
