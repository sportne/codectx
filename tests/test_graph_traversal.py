from __future__ import annotations

from pathlib import Path

from codectx.frontends.base import EdgeFact, NodeFact
from codectx.graph.store import GraphStore
from codectx.graph.traversal import bounded_neighborhood
from codectx.scanner.models import FileRecord
from codectx.source.spans import SourceSpan


def test_bounded_neighborhood_traverses_depth_direction_kind_and_limit(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id, ids = _seed_neighborhood(store, tmp_path)

        result = bounded_neighborhood(
            store.conn,
            snapshot_id,
            ids["Service.authorize"],
            depth=2,
            direction="out",
            edge_kinds=("calls", "uses_type"),
            limit=3,
        )

    assert [(node.node_id, node.depth) for node in result.nodes] == [
        (ids["Service.authorize"], 0),
        (ids["Gateway"], 1),
        (ids["Service.validate"], 1),
    ]
    assert [
        (edge.kind, edge.dst_node_id, edge.unresolved_dst) for edge in result.edges
    ] == [
        ("calls", ids["Service.validate"], None),
        ("calls", None, "gateway.charge"),
        ("uses_type", ids["Gateway"], None),
    ]


def test_bounded_neighborhood_supports_inbound_and_cycles(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id, ids = _seed_neighborhood(store, tmp_path)

        result = bounded_neighborhood(
            store.conn,
            snapshot_id,
            ids["Service.validate"],
            depth=1,
            direction="in",
            edge_kinds=("calls",),
            limit=10,
        )

    assert [(node.node_id, node.depth) for node in result.nodes] == [
        (ids["Service.validate"], 0),
        (ids["Service.authorize"], 1),
    ]
    assert [(edge.src_node_id, edge.dst_node_id) for edge in result.edges] == [
        (ids["Service.authorize"], ids["Service.validate"])
    ]


def test_bounded_neighborhood_limit_omits_edges_to_omitted_nodes(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id, ids = _seed_neighborhood(store, tmp_path)

        result = bounded_neighborhood(
            store.conn,
            snapshot_id,
            ids["Service.authorize"],
            depth=1,
            direction="out",
            edge_kinds=("calls", "uses_type"),
            limit=1,
        )

    assert [(node.node_id, node.depth) for node in result.nodes] == [
        (ids["Service.authorize"], 0)
    ]
    assert [(edge.dst_node_id, edge.unresolved_dst) for edge in result.edges] == [
        (None, "gateway.charge")
    ]


def test_bounded_neighborhood_rejects_invalid_parameters(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        snapshot_id, ids = _seed_neighborhood(store, tmp_path)

        for kwargs in (
            {"depth": -1},
            {"limit": 0},
            {"direction": "sideways"},
        ):
            try:
                bounded_neighborhood(
                    store.conn,
                    snapshot_id,
                    ids["Service.authorize"],
                    **kwargs,
                )
            except ValueError:
                pass
            else:  # pragma: no cover - assertion branch
                raise AssertionError(f"expected ValueError for {kwargs}")


def _seed_neighborhood(store: GraphStore, repo: Path) -> tuple[int, dict[str, int]]:
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
            NodeFact(
                kind="type",
                language="java",
                name="Gateway",
                qualified_name="Gateway",
                symbol_key="java:src/Service.java#Gateway",
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
            ),
            EdgeFact(
                kind="calls",
                src_key="java:src/Service.java#Service.authorize()",
                dst_key=None,
                unresolved_src=None,
                unresolved_dst="gateway.charge",
                file_path="src/Service.java",
                span=span,
                confidence=0.45,
                extractor="test",
            ),
            EdgeFact(
                kind="uses_type",
                src_key="java:src/Service.java#Service.authorize()",
                dst_key="java:src/Service.java#Gateway",
                unresolved_src=None,
                unresolved_dst=None,
                file_path="src/Service.java",
                span=span,
                confidence=0.5,
                extractor="test",
            ),
            EdgeFact(
                kind="calls",
                src_key="java:src/Service.java#Service.validate()",
                dst_key="java:src/Service.java#Service.authorize()",
                unresolved_src=None,
                unresolved_dst=None,
                file_path="src/Service.java",
                span=span,
                confidence=0.75,
                extractor="test",
            ),
        ],
        file_ids,
        node_ids,
    )
    return snapshot_id, {
        "Service.authorize": node_ids["java:src/Service.java#Service.authorize()"],
        "Service.validate": node_ids["java:src/Service.java#Service.validate()"],
        "Gateway": node_ids["java:src/Service.java#Gateway"],
    }
