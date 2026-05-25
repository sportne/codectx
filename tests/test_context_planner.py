from __future__ import annotations

from pathlib import Path

from codectx.context.anchors import AnchorResult, resolve_file_line_anchor
from codectx.context.planner import build_explain_bundle
from codectx.frontends.base import ChunkFact, NodeFact, OccurrenceFact
from codectx.graph.store import GraphStore
from codectx.scanner.models import FileRecord
from codectx.source.spans import SourceSpan


def test_build_explain_bundle_includes_target_enclosing_import_and_sibling(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_explain_graph(store, repo)
        anchor = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/PaymentService.java", 5
        )
        assert isinstance(anchor, AnchorResult)

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=1000,
            index_health={"files": "1", "nodes": "3"},
        )

    assert [item.kind for item in bundle.items] == [
        "target.definition",
        "enclosing.type",
        "import",
        "sibling.definition",
    ]
    assert bundle.items[0].rank == 1
    assert bundle.items[0].file == "src/PaymentService.java"
    assert bundle.items[0].line_range == (4, 6)
    assert "authorize" in bundle.items[0].text
    assert bundle.items[1].reason == "enclosing type"
    assert bundle.items[2].text == "import java.util.List;\n"
    assert bundle.items[3].reason == "same-file sibling"
    assert bundle.index_health == {"files": "1", "nodes": "3"}
    assert bundle.anchor["qualified_name"] == "acme.PaymentService.authorize()"


def test_build_explain_bundle_records_omitted_optional_candidates_by_budget(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_explain_graph(store, repo)
        anchor = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/PaymentService.java", 5
        )
        assert isinstance(anchor, AnchorResult)

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=1,
            index_health={},
        )

    assert [item.kind for item in bundle.items] == [
        "target.definition",
        "enclosing.type",
    ]
    assert [omitted.reason for omitted in bundle.omitted] == ["budget", "budget"]
    assert any(
        omitted.name == "src/PaymentService.java:7" for omitted in bundle.omitted
    )


def test_build_explain_bundle_uses_anchor_chunk_without_node(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_fallback_graph(store, repo)
        anchor = resolve_file_line_anchor(store.conn, snapshot_id, "src/Readme.java", 1)
        assert isinstance(anchor, AnchorResult)

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=100,
            index_health={},
        )

    assert [item.kind for item in bundle.items] == ["target.file"]
    assert bundle.items[0].text == "read me"
    assert bundle.items[0].metadata["chunk_id"] == anchor.chunk_id


def test_build_explain_bundle_uses_source_line_fallback(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_fallback_graph(store, repo)
        anchor = resolve_file_line_anchor(store.conn, snapshot_id, "src/Notes.java", 2)
        assert isinstance(anchor, AnchorResult)

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=100,
            index_health={},
        )

    assert [item.kind for item in bundle.items] == ["target.source"]
    assert bundle.items[0].text == "second line\n"
    assert "source-line fallback" in bundle.uncertainty_notes[0]


def test_build_explain_bundle_uses_node_source_range_before_nearest_chunk(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_node_without_chunk_graph(store, repo)
        anchor = resolve_file_line_anchor(store.conn, snapshot_id, "src/Foo.java", 3)
        assert isinstance(anchor, AnchorResult)
        assert anchor.node_id is not None
        assert anchor.chunk_text == "void sibling() {}\n"

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=100,
            index_health={},
        )

    assert bundle.items[0].kind == "target.source"
    assert bundle.items[0].line_range == (2, 3)
    assert "void target()" in bundle.items[0].text
    assert "void sibling()" not in bundle.items[0].text
    assert "source-range fallback" in bundle.uncertainty_notes[0]


def test_build_explain_bundle_adds_file_enclosing_context_for_top_level_node(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_top_level_graph(store, repo)
        anchor = resolve_file_line_anchor(store.conn, snapshot_id, "src/main.cpp", 1)
        assert isinstance(anchor, AnchorResult)

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=100,
            index_health={},
        )

    assert [item.kind for item in bundle.items[:2]] == [
        "target.definition",
        "enclosing.file",
    ]
    assert bundle.items[1].reason == "enclosing file"


def test_build_explain_bundle_uses_source_fallback_for_file_enclosing_context(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_top_level_graph(store, repo, include_file_chunk=False)
        anchor = resolve_file_line_anchor(store.conn, snapshot_id, "src/main.cpp", 1)
        assert isinstance(anchor, AnchorResult)

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=100,
            index_health={},
        )

    assert [item.kind for item in bundle.items[:2]] == [
        "target.definition",
        "enclosing.file",
    ]
    assert bundle.items[1].text == "int main() { return 0; }\n"
    assert "Enclosing file used source fallback." in bundle.uncertainty_notes


def test_build_explain_bundle_records_missing_enclosing_source(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_explain_graph(store, repo, include_type_chunk=False)
        anchor = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/PaymentService.java", 5
        )
        assert isinstance(anchor, AnchorResult)
        (repo / "src" / "PaymentService.java").unlink()

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=100,
            index_health={},
        )

    assert bundle.items[0].kind == "target.definition"
    assert "Enclosing type source could not be read." in bundle.uncertainty_notes


def test_build_explain_bundle_uses_source_fallback_for_enclosing_type(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_explain_graph(store, repo, include_type_chunk=False)
        anchor = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/PaymentService.java", 5
        )
        assert isinstance(anchor, AnchorResult)

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=1000,
            index_health={},
        )

    assert [item.kind for item in bundle.items[:2]] == [
        "target.definition",
        "enclosing.type",
    ]
    assert "class PaymentService" in bundle.items[1].text
    assert "source fallback" in bundle.uncertainty_notes[0]


def test_build_explain_bundle_records_missing_source_without_target(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        store.apply_schema()
        repo_id = store.create_repo(repo)
        snapshot_id = store.create_snapshot(repo_id)
        store.insert_files(
            snapshot_id,
            [
                FileRecord(
                    path="src/Missing.java",
                    language="java",
                    content_hash="missing",
                    size_bytes=20,
                    line_count=2,
                )
            ],
        )
        anchor = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/Missing.java", 1
        )
        assert isinstance(anchor, AnchorResult)

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=100,
            index_health={},
        )

    assert bundle.items == []
    assert "could not be read" in bundle.uncertainty_notes[0]


def test_build_explain_bundle_uses_occurrence_text_when_import_line_is_invalid(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_invalid_import_graph(store, repo)
        anchor = resolve_file_line_anchor(store.conn, snapshot_id, "src/Foo.java", 1)
        assert isinstance(anchor, AnchorResult)

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=100,
            index_health={},
        )

    assert [item.kind for item in bundle.items] == ["target.file", "include"]
    assert bundle.items[1].text == "bad.hpp"


def _seed_explain_graph(
    store: GraphStore, repo: Path, *, include_type_chunk: bool = True
) -> int:
    source = (
        "package acme;\n"
        "import java.util.List;\n"
        "class PaymentService {\n"
        "  boolean authorize() {\n"
        "    return true;\n"
        "  }\n"
        "  void helper() {}\n"
        "}\n"
    )
    _write(repo / "src" / "PaymentService.java", source)
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
                size_bytes=len(source.encode("utf-8")),
                line_count=8,
            )
        ],
    )
    node_ids = store.insert_nodes(
        snapshot_id,
        [
            _node("type", "PaymentService", "acme.PaymentService", 3, 8),
            _node("callable", "authorize", "acme.PaymentService.authorize()", 4, 6),
            _node("callable", "helper", "acme.PaymentService.helper()", 7, 7),
        ],
        file_ids,
    )
    store.insert_occurrences(
        [
            OccurrenceFact(
                file_path="src/PaymentService.java",
                role="import",
                text="java.util.List",
                span=SourceSpan(
                    file_path="src/PaymentService.java",
                    start_byte=14,
                    end_byte=36,
                    start_line=2,
                    start_col=0,
                    end_line=2,
                    end_col=22,
                ),
                node_key=None,
                resolved_key=None,
                confidence=0.8,
                extractor="test",
                metadata={"static": False},
            )
        ],
        file_ids,
        node_ids,
    )
    chunks = [
        ChunkFact(
            file_path="src/PaymentService.java",
            node_key="java:src/PaymentService.java#authorize",
            kind="definition",
            start_line=4,
            end_line=6,
            text="  boolean authorize() {\n    return true;\n  }\n",
            token_estimate=12,
        ),
        ChunkFact(
            file_path="src/PaymentService.java",
            node_key="java:src/PaymentService.java#helper",
            kind="definition",
            start_line=7,
            end_line=7,
            text="  void helper() {}\n",
            token_estimate=5,
        ),
    ]
    if include_type_chunk:
        chunks.insert(
            0,
            ChunkFact(
                file_path="src/PaymentService.java",
                node_key="java:src/PaymentService.java#PaymentService",
                kind="definition",
                start_line=3,
                end_line=8,
                text="class PaymentService {\n  boolean authorize() {\n    return true;\n  }\n  void helper() {}\n}\n",
                token_estimate=23,
            ),
        )
    store.insert_chunks(chunks, file_ids, node_ids)
    return snapshot_id


def _seed_fallback_graph(store: GraphStore, repo: Path) -> int:
    _write(repo / "src" / "Readme.java", "read me\n")
    _write(repo / "src" / "Notes.java", "first line\nsecond line\n")
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    file_ids = store.insert_files(
        snapshot_id,
        [
            FileRecord(
                path="src/Readme.java",
                language="java",
                content_hash="def456",
                size_bytes=8,
                line_count=1,
            ),
            FileRecord(
                path="src/Notes.java",
                language="java",
                content_hash="ghi789",
                size_bytes=23,
                line_count=2,
            ),
        ],
    )
    store.insert_chunks(
        [
            ChunkFact(
                file_path="src/Readme.java",
                node_key=None,
                kind="file",
                start_line=1,
                end_line=1,
                text="read me",
                token_estimate=2,
            )
        ],
        file_ids,
        {},
    )
    return snapshot_id


def _seed_invalid_import_graph(store: GraphStore, repo: Path) -> int:
    _write(repo / "src" / "Foo.java", "class Foo {}\n")
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    file_ids = store.insert_files(
        snapshot_id,
        [
            FileRecord(
                path="src/Foo.java",
                language="java",
                content_hash="abc123",
                size_bytes=12,
                line_count=5,
            )
        ],
    )
    store.insert_occurrences(
        [
            OccurrenceFact(
                file_path="src/Foo.java",
                role="include",
                text="bad.hpp",
                span=SourceSpan(
                    file_path="src/Foo.java",
                    start_byte=0,
                    end_byte=7,
                    start_line=4,
                    start_col=0,
                    end_line=4,
                    end_col=7,
                ),
                node_key=None,
                resolved_key=None,
                confidence=0.6,
                extractor="test",
                metadata=[],
            )
        ],
        file_ids,
        {},
    )
    store.insert_chunks(
        [
            ChunkFact(
                file_path="src/Foo.java",
                node_key=None,
                kind="file",
                start_line=1,
                end_line=1,
                text="class Foo {}",
                token_estimate=3,
            )
        ],
        file_ids,
        {},
    )
    return snapshot_id


def _seed_node_without_chunk_graph(store: GraphStore, repo: Path) -> int:
    source = "class Foo {\n  void target() {\n  }\n  void sibling() {}\n}\n"
    _write(repo / "src" / "Foo.java", source)
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    file_ids = store.insert_files(
        snapshot_id,
        [
            FileRecord(
                path="src/Foo.java",
                language="java",
                content_hash="abc123",
                size_bytes=len(source.encode("utf-8")),
                line_count=5,
            )
        ],
    )
    node_ids = store.insert_nodes(
        snapshot_id,
        [
            NodeFact(
                kind="callable",
                language="java",
                name="target",
                qualified_name="Foo.target()",
                symbol_key="java:src/Foo.java#target",
                file_path="src/Foo.java",
                span=SourceSpan(
                    file_path="src/Foo.java",
                    start_byte=0,
                    end_byte=10,
                    start_line=2,
                    start_col=0,
                    end_line=3,
                    end_col=1,
                ),
                confidence=1.0,
                extractor="test",
                metadata={},
            )
        ],
        file_ids,
    )
    store.insert_chunks(
        [
            ChunkFact(
                file_path="src/Foo.java",
                node_key=None,
                kind="definition",
                start_line=4,
                end_line=4,
                text="void sibling() {}\n",
                token_estimate=5,
            )
        ],
        file_ids,
        node_ids,
    )
    return snapshot_id


def _seed_top_level_graph(
    store: GraphStore, repo: Path, *, include_file_chunk: bool = True
) -> int:
    source = "int main() { return 0; }\n"
    _write(repo / "src" / "main.cpp", source)
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    file_ids = store.insert_files(
        snapshot_id,
        [
            FileRecord(
                path="src/main.cpp",
                language="cpp",
                content_hash="abc123",
                size_bytes=len(source.encode("utf-8")),
                line_count=1,
            )
        ],
    )
    node_ids = store.insert_nodes(
        snapshot_id,
        [
            NodeFact(
                kind="callable",
                language="cpp",
                name="main",
                qualified_name="main()",
                symbol_key="cpp:src/main.cpp#main",
                file_path="src/main.cpp",
                span=SourceSpan(
                    file_path="src/main.cpp",
                    start_byte=0,
                    end_byte=len(source.encode("utf-8")),
                    start_line=1,
                    start_col=0,
                    end_line=1,
                    end_col=24,
                ),
                confidence=1.0,
                extractor="test",
                metadata={},
            )
        ],
        file_ids,
    )
    chunks = [
        ChunkFact(
            file_path="src/main.cpp",
            node_key="cpp:src/main.cpp#main",
            kind="definition",
            start_line=1,
            end_line=1,
            text=source,
            token_estimate=6,
        )
    ]
    if include_file_chunk:
        chunks.append(
            ChunkFact(
                file_path="src/main.cpp",
                node_key=None,
                kind="file",
                start_line=1,
                end_line=1,
                text=source,
                token_estimate=6,
            ),
        )
    store.insert_chunks(chunks, file_ids, node_ids)
    return snapshot_id


def _node(
    kind: str,
    name: str,
    qualified_name: str,
    start_line: int,
    end_line: int,
) -> NodeFact:
    return NodeFact(
        kind=kind,
        language="java",
        name=name,
        qualified_name=qualified_name,
        symbol_key=f"java:src/PaymentService.java#{name}",
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


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
