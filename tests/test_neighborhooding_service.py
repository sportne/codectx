from __future__ import annotations

from pathlib import Path

import codectx.neighborhooding as neighborhooding
from codectx.frontends.base import EdgeFact, NodeFact
from codectx.graph.store import GraphStore
from codectx.neighborhooding import (
    NeighborhoodError,
    NeighborhoodResult,
    build_neighborhood,
)
from codectx.querying import QueryingError
from codectx.scanner.models import FileRecord
from codectx.source.spans import SourceSpan


def test_build_neighborhood_returns_bounded_result(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        _seed_service_graph(store, repo)

    result = build_neighborhood(repo, "authorize", db_path=db_path, depth=1)

    assert isinstance(result, NeighborhoodResult)
    assert result.symbol == "authorize"
    assert [node.depth for node in result.nodes] == [0, 1]
    assert [edge.kind for edge in result.edges] == ["calls"]


def test_build_neighborhood_reports_missing_index_symbol_and_bad_args(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    missing = build_neighborhood(repo, "authorize", db_path=tmp_path / "missing.sqlite")
    bad_depth = build_neighborhood(repo, "authorize", depth=-1)
    bad_limit = build_neighborhood(repo, "authorize", limit=0)
    bad_direction = build_neighborhood(repo, "authorize", direction="sideways")

    assert isinstance(missing, NeighborhoodError)
    assert "No codectx index found" in missing.message
    assert isinstance(bad_depth, NeighborhoodError)
    assert "depth" in bad_depth.message
    assert isinstance(bad_limit, NeighborhoodError)
    assert "limit" in bad_limit.message
    assert isinstance(bad_direction, NeighborhoodError)
    assert "direction" in bad_direction.message

    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        _seed_service_graph(store, repo)

    no_symbol = build_neighborhood(repo, "missing", db_path=db_path)

    assert isinstance(no_symbol, NeighborhoodError)
    assert "No indexed symbol matched" in no_symbol.message


def test_build_neighborhood_adapts_symbol_search_errors(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        _seed_service_graph(store, repo)

    monkeypatch.setattr(
        neighborhooding,
        "search_symbols",
        lambda *_args, **_kwargs: QueryingError("symbol search failed"),
    )

    result = build_neighborhood(repo, "authorize", db_path=db_path)

    assert isinstance(result, NeighborhoodError)
    assert result.message == "symbol search failed"


def _seed_service_graph(store: GraphStore, repo: Path) -> None:
    repo.mkdir(exist_ok=True)
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    span = SourceSpan("src/Service.java", 0, 10, 1, 0, 1, 10)
    file_ids = store.insert_files(
        snapshot_id,
        [
            FileRecord(
                path="src/Service.java",
                language="java",
                content_hash="abc123",
                size_bytes=100,
                line_count=10,
            )
        ],
    )
    node_ids = store.insert_nodes(
        snapshot_id,
        [
            NodeFact(
                kind="callable",
                language="java",
                name="authorize",
                qualified_name="Service.authorize",
                symbol_key="java:src/Service.java#Service.authorize()",
                file_path="src/Service.java",
                span=span,
                confidence=1.0,
                extractor="test",
            ),
            NodeFact(
                kind="callable",
                language="java",
                name="validate",
                qualified_name="Service.validate",
                symbol_key="java:src/Service.java#Service.validate()",
                file_path="src/Service.java",
                span=span,
                confidence=1.0,
                extractor="test",
            ),
        ],
        file_ids,
    )
    store.insert_edges(
        snapshot_id,
        [
            EdgeFact(
                kind="calls",
                src_key="java:src/Service.java#Service.authorize()",
                dst_key="java:src/Service.java#Service.validate()",
                unresolved_src=None,
                unresolved_dst=None,
                file_path="src/Service.java",
                span=span,
                confidence=0.75,
                extractor="test",
            )
        ],
        file_ids,
        node_ids,
    )
