from __future__ import annotations

from json import loads
from pathlib import Path

from codectx.context.anchors import AnchorResult, resolve_file_line_anchor
from codectx.context.formatters import format_json
from codectx.context.planner import build_context_bundle, build_explain_bundle
from codectx.frontends.base import (
    ChunkFact,
    DiagnosticFact,
    EdgeFact,
    NodeFact,
    OccurrenceFact,
)
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
    ]
    assert bundle.items[0].rank == 1
    assert bundle.items[0].score_trace["target"] == 5.0
    assert bundle.items[0].score_trace["exact_match"] == 3.0
    assert loads(format_json(bundle))["items"][0]["score_trace"]["total"] == (
        bundle.items[0].score
    )
    assert bundle.items[0].file == "src/PaymentService.java"
    assert bundle.items[0].line_range == (4, 6)
    assert "authorize" in bundle.items[0].text
    assert bundle.items[1].reason == "enclosing type"
    assert bundle.items[2].text == "import java.util.List;\n"
    assert bundle.omitted[0].reason == "overlap"
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
    assert [omitted.reason for omitted in bundle.omitted] == ["budget", "overlap"]
    assert any(
        omitted.name == "src/PaymentService.java:7" for omitted in bundle.omitted
    )


def test_build_explain_bundle_compacts_large_required_enclosing_scope(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_large_enclosing_graph(store, repo)
        anchor = resolve_file_line_anchor(store.conn, snapshot_id, "src/Large.java", 4)
        assert isinstance(anchor, AnchorResult)

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=900,
            index_health={},
        )

    assert [item.kind for item in bundle.items[:2]] == [
        "target.definition",
        "enclosing.type",
    ]
    enclosing = bundle.items[1]
    assert enclosing.token_estimate <= 300
    assert enclosing.metadata["compacted"] is True
    assert enclosing.metadata["original_token_estimate"] > 300
    assert "... omitted " in enclosing.text
    assert "compacted from" in bundle.uncertainty_notes[0]
    assert any(
        item.kind == "import" and "java.util.List" in item.text for item in bundle.items
    )
    assert any(
        entry["stage"] == "compact"
        and entry["kind"] == "enclosing.type"
        and entry["original_tokens"] == enclosing.metadata["original_token_estimate"]
        for entry in bundle.trace
    )


def test_build_explain_bundle_does_not_compact_target_even_when_large(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_large_target_graph(store, repo)
        anchor = resolve_file_line_anchor(store.conn, snapshot_id, "src/Only.java", 2)
        assert isinstance(anchor, AnchorResult)

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=900,
            index_health={},
        )

    assert bundle.items[0].kind == "target.definition"
    assert bundle.items[0].token_estimate > 300
    assert "compacted" not in bundle.items[0].metadata


def test_build_explain_bundle_compacts_single_line_enclosing_under_limit(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_single_line_large_enclosing_graph(store, repo)
        anchor = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/OneLine.java", 1
        )
        assert isinstance(anchor, AnchorResult)

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=900,
            index_health={},
        )

    enclosing = bundle.items[1]
    assert enclosing.kind == "enclosing.type"
    assert enclosing.token_estimate <= 300
    assert "omitted remainder" in enclosing.text


def test_build_explain_bundle_selects_optional_candidates_by_score_per_token(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_budget_ranking_graph(store, repo)
        anchor = resolve_file_line_anchor(store.conn, snapshot_id, "src/Foo.java", 2)
        assert isinstance(anchor, AnchorResult)

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=27,
            index_health={},
        )

    assert [item.kind for item in bundle.items] == [
        "target.definition",
        "enclosing.file",
        "neighborhood.callee",
    ]
    assert bundle.items[2].metadata["node_name"] == "cheap"
    assert [omitted.reason for omitted in bundle.omitted] == ["budget", "budget"]
    assert any(omitted.name == "src/Foo.java:5" for omitted in bundle.omitted)


def test_build_explain_bundle_omits_overlapping_optional_candidates(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_overlap_graph(store, repo)
        anchor = resolve_file_line_anchor(store.conn, snapshot_id, "src/Foo.java", 2)
        assert isinstance(anchor, AnchorResult)

        bundle = build_explain_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=100,
            index_health={},
        )

    assert [item.kind for item in bundle.items] == [
        "target.definition",
        "enclosing.file",
    ]
    assert [omitted.reason for omitted in bundle.omitted] == ["overlap", "overlap"]
    assert bundle.omitted[0].name == "src/Foo.java:4"


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


def test_build_explain_bundle_reports_invalid_source_fallback(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_invalid_source_fallback_graph(store, repo)
        anchor = resolve_file_line_anchor(store.conn, snapshot_id, "src/Bad.java", 1)
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
    assert any("not valid UTF-8" in note for note in bundle.uncertainty_notes)


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


def test_build_explain_bundle_adds_neighborhood_and_test_candidates(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_neighborhood_context_graph(store, repo)
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

    assert [item.kind for item in bundle.items] == [
        "target.definition",
        "enclosing.type",
        "neighborhood.type",
        "test.related",
    ]
    assert [item.reason for item in bundle.items[2:4]] == [
        "referenced type",
        "related test",
    ]
    assert bundle.items[2].metadata["node_name"] == "Gateway"
    assert bundle.items[3].file == "test/PaymentServiceAuthorizeTest.java"
    assert [omitted.reason for omitted in bundle.omitted] == ["overlap", "overlap"]
    assert any("gateway.charge" in note for note in bundle.uncertainty_notes)
    assert {
        "stage": "candidates",
        "optional_count": 4,
        "diagnostic_count": 0,
        "relationship_count": 3,
        "test_count": 1,
    } in bundle.trace


def test_build_explain_bundle_omits_neighborhood_items_when_over_budget(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_neighborhood_context_graph(store, repo)
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
    assert [omitted.reason for omitted in bundle.omitted] == [
        "budget",
        "overlap",
        "overlap",
        "budget",
    ]
    assert bundle.omitted[0].name == "src/Gateway.java:1"
    assert bundle.omitted[-1].name == "test/PaymentServiceAuthorizeTest.java:2-4"


def test_build_failure_modes_bundle_prioritizes_validation_and_failure_tests(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_failure_modes_graph(store, repo)
        anchor = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/PaymentService.java", 4
        )
        assert isinstance(anchor, AnchorResult)

        bundle = build_context_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=1000,
            index_health={"diagnostics": "1"},
            query={"goal": "failure-modes", "budget": 1000},
        )

    selected_names = [item.metadata.get("node_name") for item in bundle.items]
    assert selected_names[:2] == ["authorize", "PaymentService"]
    assert "validatePayment" in selected_names
    assert "helper" in selected_names
    assert selected_names.index("validatePayment") < selected_names.index("helper")
    diagnostic = next(item for item in bundle.items if item.kind == "diagnostic.parser")
    assert diagnostic.file == "src/PaymentService.java"
    assert diagnostic.line_range == (5, 5)
    assert diagnostic.reason == (
        "parser diagnostic: error parse_error: Java parse error near throw"
    )
    assert diagnostic.extractor == "treesitter-java"
    assert diagnostic.metadata["message"] == "Java parse error near throw"
    assert diagnostic.score_trace["goal_relevance"] == 4.0
    assert any(
        item.kind == "test.related"
        and item.file == "test/PaymentServiceFailureTest.java"
        for item in bundle.items
    )
    validation = next(
        item
        for item in bundle.items
        if item.metadata.get("node_name") == "validatePayment"
    )
    assert validation.score_trace["goal_relevance"] == 4.0
    assert bundle.index_health["diagnostics"] == "1"


def test_build_failure_modes_bundle_deprioritizes_vendor_diagnostics(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_failure_modes_graph(
            store, repo, include_vendor_diagnostic=True
        )
        anchor = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/PaymentService.java", 4
        )
        assert isinstance(anchor, AnchorResult)

        bundle = build_context_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=90,
            index_health={"diagnostics": "2"},
            query={"goal": "failure-modes", "budget": 90},
        )

    diagnostics = [item for item in bundle.items if item.kind == "diagnostic.parser"]
    assert [item.file for item in diagnostics] == ["src/PaymentService.java"]
    assert diagnostics[0].score_trace["goal_relevance"] == 4.0
    assert all(item.file != "third_party/googletest/gtest.cc" for item in bundle.items)
    assert any(
        omitted.name == "third_party/googletest/gtest.cc:1"
        and omitted.reason == "budget"
        for omitted in bundle.omitted
    )


def test_build_failure_modes_bundle_skips_vendor_diagnostic_for_omitted_test(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_failure_modes_graph(
            store, repo, include_vendor_diagnostic=True
        )
        anchor = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/PaymentService.java", 4
        )
        assert isinstance(anchor, AnchorResult)

        bundle = build_context_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=102,
            index_health={"diagnostics": "2"},
            query={"goal": "failure-modes", "budget": 102},
        )

    assert all(item.file != "third_party/googletest/gtest.cc" for item in bundle.items)
    assert any(
        omitted.name == "test/PaymentServiceFailureTest.java:2-4"
        and omitted.reason == "budget"
        for omitted in bundle.omitted
    )
    assert any(
        omitted.name == "third_party/googletest/gtest.cc:1"
        and omitted.reason == "budget"
        for omitted in bundle.omitted
    )


def test_build_failure_modes_bundle_keeps_related_diagnostics_only(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_failure_modes_graph(
            store,
            repo,
            include_related_diagnostic=True,
            include_unrelated_diagnostic=True,
        )
        anchor = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/PaymentService.java", 4
        )
        assert isinstance(anchor, AnchorResult)

        bundle = build_context_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=1000,
            index_health={"diagnostics": "3"},
            query={"goal": "failure-modes", "budget": 1000},
        )

    diagnostics = [item for item in bundle.items if item.kind == "diagnostic.parser"]
    assert [item.file for item in diagnostics] == [
        "src/PaymentService.java",
        "include/PaymentService.hpp",
    ]
    assert diagnostics[0].score_trace["goal_relevance"] == 4.0
    assert diagnostics[1].score_trace["goal_relevance"] == 2.0
    assert all(item.file != "src/Unrelated.cpp" for item in bundle.items)
    assert bundle.index_health["diagnostics"] == "3"


def test_build_dependencies_bundle_prioritizes_imports_types_and_fields(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_dependencies_graph(store, repo)
        anchor = resolve_file_line_anchor(
            store.conn, snapshot_id, "src/PaymentService.java", 5
        )
        assert isinstance(anchor, AnchorResult)

        bundle = build_context_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=1000,
            index_health={},
            query={"goal": "dependencies", "budget": 1000},
        )

    item_names = [item.metadata.get("node_name") for item in bundle.items]
    item_kinds = [item.kind for item in bundle.items]
    assert "import" in item_kinds
    assert "neighborhood.type" in item_kinds
    assert "neighborhood.reference" in item_kinds
    assert "neighborhood.callee" in item_kinds
    assert item_names.index("Gateway") < item_names.index("validate")
    assert item_names.index("gateway") < item_names.index("validate")
    dependency_items = [
        item
        for item in bundle.items
        if item.kind in {"import", "neighborhood.type", "neighborhood.reference"}
    ]
    assert all("goal_relevance" in item.score_trace for item in dependency_items)
    assert any(item.text == "import java.util.List;\n" for item in dependency_items)


def test_build_call_neighborhood_bundle_includes_callers_callees_and_unresolved(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_call_neighborhood_graph(store, repo)
        anchor = resolve_file_line_anchor(store.conn, snapshot_id, "src/Foo.java", 5)
        assert isinstance(anchor, AnchorResult)

        bundle = build_context_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=1000,
            index_health={},
            query={"goal": "call-neighborhood", "budget": 1000},
        )

    item_by_name = {
        item.metadata.get("node_name"): item
        for item in bundle.items
        if item.metadata.get("node_name") is not None
    }
    assert item_by_name["validate"].kind == "neighborhood.callee"
    assert item_by_name["controller"].kind == "neighborhood.caller"
    assert item_by_name["controller"].metadata["direction"] == "in"
    assert item_by_name["validate"].score_trace["goal_relevance"] == 1.8
    assert item_by_name["controller"].score_trace["goal_relevance"] == 2.0
    assert any("externalGateway.charge" in note for note in bundle.uncertainty_notes)


def test_build_call_neighborhood_bundle_uses_source_fallback_for_callers(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_call_neighborhood_graph(
            store, repo, include_caller_chunk=False
        )
        anchor = resolve_file_line_anchor(store.conn, snapshot_id, "src/Foo.java", 5)
        assert isinstance(anchor, AnchorResult)

        bundle = build_context_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=1000,
            index_health={},
            query={"goal": "call-neighborhood", "budget": 1000},
        )

    caller = next(
        item for item in bundle.items if item.metadata.get("node_name") == "controller"
    )
    assert caller.kind == "neighborhood.caller"
    assert caller.text == "  void controller() { target(); }\n"
    assert "Direct caller used source fallback." in bundle.uncertainty_notes


def test_build_call_neighborhood_bundle_prunes_by_budget_after_call_context(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "graph.sqlite"
    repo = tmp_path / "repo"
    with GraphStore(db_path) as store:
        snapshot_id = _seed_call_neighborhood_graph(store, repo)
        anchor = resolve_file_line_anchor(store.conn, snapshot_id, "src/Foo.java", 5)
        assert isinstance(anchor, AnchorResult)

        bundle = build_context_bundle(
            store.conn,
            snapshot_id,
            repo,
            anchor,
            budget=68,
            index_health={},
            query={"goal": "call-neighborhood", "budget": 68},
        )

    item_names = [item.metadata.get("node_name") for item in bundle.items]
    assert item_names == ["target", "Foo", "validate"]
    assert bundle.items[2].kind == "neighborhood.callee"
    assert [(omitted.name, omitted.reason) for omitted in bundle.omitted] == [
        ("src/Foo.java:2", "budget")
    ]


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


def _seed_large_enclosing_graph(store: GraphStore, repo: Path) -> int:
    large_body = "".join(f"  void helper{i:03d}() {{}}\n" for i in range(240))
    source = (
        "import java.util.List;\n"
        f"class Large {{\n  void target() {{\n    helper000();\n  }}\n{large_body}}}\n"
    )
    _write(repo / "src" / "Large.java", source)
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    file_ids = store.insert_files(
        snapshot_id,
        [
            FileRecord(
                path="src/Large.java",
                language="java",
                content_hash="large-enclosing",
                size_bytes=len(source.encode("utf-8")),
                line_count=246,
            )
        ],
    )
    node_ids = store.insert_nodes(
        snapshot_id,
        [
            _java_node(
                "type",
                "Large",
                "Large",
                "java:src/Large.java#Large",
                "src/Large.java",
                2,
                246,
            ),
            _java_node(
                "callable",
                "target",
                "Large.target()",
                "java:src/Large.java#Large.target()",
                "src/Large.java",
                3,
                5,
            ),
            _java_node(
                "callable",
                "helper000",
                "Large.helper000()",
                "java:src/Large.java#Large.helper000()",
                "src/Large.java",
                6,
                6,
            ),
        ],
        file_ids,
    )
    store.insert_occurrences(
        [
            OccurrenceFact(
                file_path="src/Large.java",
                role="import",
                text="java.util.List",
                span=SourceSpan(
                    file_path="src/Large.java",
                    start_byte=0,
                    end_byte=22,
                    start_line=1,
                    start_col=0,
                    end_line=1,
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
    store.insert_edges(
        snapshot_id,
        [
            _edge(
                "calls",
                "java:src/Large.java#Large.target()",
                "java:src/Large.java#Large.helper000()",
                "src/Large.java",
                4,
            )
        ],
        file_ids,
        node_ids,
    )
    store.insert_chunks(
        [
            ChunkFact(
                file_path="src/Large.java",
                node_key="java:src/Large.java#Large",
                kind="definition",
                start_line=2,
                end_line=246,
                text=source,
                token_estimate=1_500,
            ),
            ChunkFact(
                file_path="src/Large.java",
                node_key="java:src/Large.java#Large.target()",
                kind="definition",
                start_line=3,
                end_line=5,
                text="  void target() {\n    helper000();\n  }\n",
                token_estimate=10,
            ),
            ChunkFact(
                file_path="src/Large.java",
                node_key="java:src/Large.java#Large.helper000()",
                kind="definition",
                start_line=6,
                end_line=6,
                text="  void helper000() {}\n",
                token_estimate=6,
            ),
        ],
        file_ids,
        node_ids,
    )
    return snapshot_id


def _seed_single_line_large_enclosing_graph(store: GraphStore, repo: Path) -> int:
    source = (
        "class OneLine { void target() {} "
        + " ".join(f"void helper{i:03d}() {{}}" for i in range(240))
        + " }\n"
    )
    _write(repo / "src" / "OneLine.java", source)
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    file_ids = store.insert_files(
        snapshot_id,
        [
            FileRecord(
                path="src/OneLine.java",
                language="java",
                content_hash="single-line-large-enclosing",
                size_bytes=len(source.encode("utf-8")),
                line_count=1,
            )
        ],
    )
    node_ids = store.insert_nodes(
        snapshot_id,
        [
            _java_node(
                "type",
                "OneLine",
                "OneLine",
                "java:src/OneLine.java#OneLine",
                "src/OneLine.java",
                1,
                1,
            ),
            _java_node(
                "callable",
                "target",
                "OneLine.target()",
                "java:src/OneLine.java#OneLine.target()",
                "src/OneLine.java",
                1,
                1,
            ),
        ],
        file_ids,
    )
    store.insert_chunks(
        [
            ChunkFact(
                file_path="src/OneLine.java",
                node_key="java:src/OneLine.java#OneLine",
                kind="definition",
                start_line=1,
                end_line=1,
                text=source,
                token_estimate=1_500,
            ),
            ChunkFact(
                file_path="src/OneLine.java",
                node_key="java:src/OneLine.java#OneLine.target()",
                kind="definition",
                start_line=1,
                end_line=1,
                text="void target() {}",
                token_estimate=5,
            ),
        ],
        file_ids,
        node_ids,
    )
    return snapshot_id


def _seed_large_target_graph(store: GraphStore, repo: Path) -> int:
    target_body = "".join(f"    step{i:03d}();\n" for i in range(240))
    source = f"class Only {{\n  void target() {{\n{target_body}  }}\n}}\n"
    _write(repo / "src" / "Only.java", source)
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    file_ids = store.insert_files(
        snapshot_id,
        [
            FileRecord(
                path="src/Only.java",
                language="java",
                content_hash="large-target",
                size_bytes=len(source.encode("utf-8")),
                line_count=244,
            )
        ],
    )
    node_ids = store.insert_nodes(
        snapshot_id,
        [
            _java_node(
                "type",
                "Only",
                "Only",
                "java:src/Only.java#Only",
                "src/Only.java",
                1,
                244,
            ),
            _java_node(
                "callable",
                "target",
                "Only.target()",
                "java:src/Only.java#Only.target()",
                "src/Only.java",
                2,
                243,
            ),
        ],
        file_ids,
    )
    store.insert_chunks(
        [
            ChunkFact(
                file_path="src/Only.java",
                node_key="java:src/Only.java#Only",
                kind="definition",
                start_line=1,
                end_line=244,
                text=source,
                token_estimate=1_500,
            ),
            ChunkFact(
                file_path="src/Only.java",
                node_key="java:src/Only.java#Only.target()",
                kind="definition",
                start_line=2,
                end_line=243,
                text=f"  void target() {{\n{target_body}  }}\n",
                token_estimate=1_400,
            ),
        ],
        file_ids,
        node_ids,
    )
    return snapshot_id


def _seed_neighborhood_context_graph(store: GraphStore, repo: Path) -> int:
    service_source = (
        "package acme;\n"
        "class PaymentService {\n"
        "  private Gateway gateway;\n"
        "  boolean authorize() {\n"
        "    validate();\n"
        "    return gateway.ready();\n"
        "  }\n"
        "  boolean validate() { return true; }\n"
        "}\n"
    )
    gateway_source = "class Gateway {}\n"
    test_source = (
        "class PaymentServiceAuthorizeTest {\n"
        "  void authorize_allowsValidPayment() {\n"
        "    new PaymentService().authorize();\n"
        "  }\n"
        "}\n"
    )
    _write(repo / "src" / "PaymentService.java", service_source)
    _write(repo / "src" / "Gateway.java", gateway_source)
    _write(repo / "test" / "PaymentServiceAuthorizeTest.java", test_source)
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    file_ids = store.insert_files(
        snapshot_id,
        [
            FileRecord(
                path="src/PaymentService.java",
                language="java",
                content_hash="service",
                size_bytes=len(service_source.encode("utf-8")),
                line_count=9,
            ),
            FileRecord(
                path="src/Gateway.java",
                language="java",
                content_hash="gateway",
                size_bytes=len(gateway_source.encode("utf-8")),
                line_count=1,
            ),
            FileRecord(
                path="test/PaymentServiceAuthorizeTest.java",
                language="java",
                content_hash="test",
                size_bytes=len(test_source.encode("utf-8")),
                line_count=5,
                is_test=True,
            ),
        ],
    )
    nodes = [
        _java_node(
            "type",
            "PaymentService",
            "acme.PaymentService",
            "java:src/PaymentService.java#PaymentService",
            "src/PaymentService.java",
            2,
            9,
        ),
        _java_node(
            "field",
            "gateway",
            "acme.PaymentService.gateway",
            "java:src/PaymentService.java#PaymentService.gateway",
            "src/PaymentService.java",
            3,
            3,
        ),
        _java_node(
            "callable",
            "authorize",
            "acme.PaymentService.authorize()",
            "java:src/PaymentService.java#PaymentService.authorize()",
            "src/PaymentService.java",
            4,
            7,
        ),
        _java_node(
            "callable",
            "validate",
            "acme.PaymentService.validate()",
            "java:src/PaymentService.java#PaymentService.validate()",
            "src/PaymentService.java",
            8,
            8,
        ),
        _java_node(
            "type",
            "Gateway",
            "acme.Gateway",
            "java:src/Gateway.java#Gateway",
            "src/Gateway.java",
            1,
            1,
        ),
        _java_node(
            "callable",
            "authorize_allowsValidPayment",
            "PaymentServiceAuthorizeTest.authorize_allowsValidPayment()",
            "java:test/PaymentServiceAuthorizeTest.java#authorize_allowsValidPayment()",
            "test/PaymentServiceAuthorizeTest.java",
            2,
            4,
        ),
    ]
    node_ids = store.insert_nodes(snapshot_id, nodes, file_ids)
    store.insert_edges(
        snapshot_id,
        [
            _edge(
                "calls",
                "java:src/PaymentService.java#PaymentService.authorize()",
                "java:src/PaymentService.java#PaymentService.validate()",
                "src/PaymentService.java",
                5,
            ),
            _edge(
                "calls",
                "java:src/PaymentService.java#PaymentService.authorize()",
                None,
                "src/PaymentService.java",
                6,
                unresolved_dst="gateway.charge",
                confidence=0.4,
            ),
            _edge(
                "uses_type",
                "java:src/PaymentService.java#PaymentService.authorize()",
                "java:src/Gateway.java#Gateway",
                "src/PaymentService.java",
                3,
            ),
            _edge(
                "references",
                "java:src/PaymentService.java#PaymentService.authorize()",
                "java:src/PaymentService.java#PaymentService.gateway",
                "src/PaymentService.java",
                6,
            ),
        ],
        file_ids,
        node_ids,
    )
    store.insert_chunks(
        [
            ChunkFact(
                file_path="src/PaymentService.java",
                node_key="java:src/PaymentService.java#PaymentService",
                kind="definition",
                start_line=2,
                end_line=9,
                text=service_source.split("\n", 1)[1],
                token_estimate=34,
            ),
            ChunkFact(
                file_path="src/PaymentService.java",
                node_key="java:src/PaymentService.java#PaymentService.gateway",
                kind="definition",
                start_line=3,
                end_line=3,
                text="  private Gateway gateway;\n",
                token_estimate=7,
            ),
            ChunkFact(
                file_path="src/PaymentService.java",
                node_key="java:src/PaymentService.java#PaymentService.authorize()",
                kind="definition",
                start_line=4,
                end_line=7,
                text=(
                    "  boolean authorize() {\n"
                    "    validate();\n"
                    "    return gateway.ready();\n"
                    "  }\n"
                ),
                token_estimate=16,
            ),
            ChunkFact(
                file_path="src/PaymentService.java",
                node_key="java:src/PaymentService.java#PaymentService.validate()",
                kind="definition",
                start_line=8,
                end_line=8,
                text="  boolean validate() { return true; }\n",
                token_estimate=9,
            ),
            ChunkFact(
                file_path="src/Gateway.java",
                node_key="java:src/Gateway.java#Gateway",
                kind="definition",
                start_line=1,
                end_line=1,
                text=gateway_source,
                token_estimate=4,
            ),
            ChunkFact(
                file_path="test/PaymentServiceAuthorizeTest.java",
                node_key=(
                    "java:test/PaymentServiceAuthorizeTest.java#"
                    "authorize_allowsValidPayment()"
                ),
                kind="definition",
                start_line=2,
                end_line=4,
                text=(
                    "  void authorize_allowsValidPayment() {\n"
                    "    new PaymentService().authorize();\n"
                    "  }\n"
                ),
                token_estimate=15,
            ),
        ],
        file_ids,
        node_ids,
    )
    return snapshot_id


def _seed_failure_modes_graph(
    store: GraphStore,
    repo: Path,
    *,
    include_vendor_diagnostic: bool = False,
    include_related_diagnostic: bool = False,
    include_unrelated_diagnostic: bool = False,
) -> int:
    service_source = (
        "class PaymentService {\n"
        "  boolean authorize() {\n"
        "    return validatePayment() && helper();\n"
        "  }\n"
        "  boolean validatePayment() { throw new IllegalStateException(); }\n"
        "  boolean helper() { return true; }\n"
        "}\n"
    )
    test_source = (
        "class PaymentServiceFailureTest {\n"
        "  void authorize_failsInvalidPayment() {\n"
        "    new PaymentService().authorize();\n"
        "  }\n"
        "}\n"
    )
    _write(repo / "src" / "PaymentService.java", service_source)
    _write(repo / "test" / "PaymentServiceFailureTest.java", test_source)
    vendor_source = "BROKEN_VENDOR_MACRO(\n"
    if include_vendor_diagnostic:
        _write(repo / "third_party" / "googletest" / "gtest.cc", vendor_source)
    related_source = "const PaymentServiceConfig &config = {}) noexcept;\n"
    if include_related_diagnostic:
        _write(repo / "include" / "PaymentService.hpp", related_source)
    unrelated_source = "BROKEN_UNRELATED_MACRO(\n"
    if include_unrelated_diagnostic:
        _write(repo / "src" / "Unrelated.cpp", unrelated_source)
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    records = [
        FileRecord(
            path="src/PaymentService.java",
            language="java",
            content_hash="service-failure",
            size_bytes=len(service_source.encode("utf-8")),
            line_count=7,
        ),
        FileRecord(
            path="test/PaymentServiceFailureTest.java",
            language="java",
            content_hash="test-failure",
            size_bytes=len(test_source.encode("utf-8")),
            line_count=5,
            is_test=True,
        ),
    ]
    if include_vendor_diagnostic:
        records.append(
            FileRecord(
                path="third_party/googletest/gtest.cc",
                language="cpp",
                content_hash="vendor-failure",
                size_bytes=len(vendor_source.encode("utf-8")),
                line_count=1,
                metadata={"is_vendor": True},
            )
        )
    if include_related_diagnostic:
        records.append(
            FileRecord(
                path="include/PaymentService.hpp",
                language="cpp",
                content_hash="related-diagnostic",
                size_bytes=len(related_source.encode("utf-8")),
                line_count=1,
            )
        )
    if include_unrelated_diagnostic:
        records.append(
            FileRecord(
                path="src/Unrelated.cpp",
                language="cpp",
                content_hash="unrelated-diagnostic",
                size_bytes=len(unrelated_source.encode("utf-8")),
                line_count=1,
            )
        )
    file_ids = store.insert_files(snapshot_id, records)
    nodes = [
        _java_node(
            "type",
            "PaymentService",
            "PaymentService",
            "java:src/PaymentService.java#PaymentService",
            "src/PaymentService.java",
            1,
            7,
        ),
        _java_node(
            "callable",
            "authorize",
            "PaymentService.authorize()",
            "java:src/PaymentService.java#PaymentService.authorize()",
            "src/PaymentService.java",
            2,
            4,
        ),
        _java_node(
            "callable",
            "validatePayment",
            "PaymentService.validatePayment()",
            "java:src/PaymentService.java#PaymentService.validatePayment()",
            "src/PaymentService.java",
            5,
            5,
        ),
        _java_node(
            "callable",
            "helper",
            "PaymentService.helper()",
            "java:src/PaymentService.java#PaymentService.helper()",
            "src/PaymentService.java",
            6,
            6,
        ),
        _java_node(
            "callable",
            "authorize_failsInvalidPayment",
            "PaymentServiceFailureTest.authorize_failsInvalidPayment()",
            "java:test/PaymentServiceFailureTest.java#authorize_failsInvalidPayment()",
            "test/PaymentServiceFailureTest.java",
            2,
            4,
        ),
    ]
    node_ids = store.insert_nodes(snapshot_id, nodes, file_ids)
    store.insert_edges(
        snapshot_id,
        [
            _edge(
                "calls",
                "java:src/PaymentService.java#PaymentService.authorize()",
                "java:src/PaymentService.java#PaymentService.validatePayment()",
                "src/PaymentService.java",
                3,
            ),
            _edge(
                "calls",
                "java:src/PaymentService.java#PaymentService.authorize()",
                "java:src/PaymentService.java#PaymentService.helper()",
                "src/PaymentService.java",
                3,
            ),
        ],
        file_ids,
        node_ids,
    )
    diagnostics = [
        DiagnosticFact(
            file_path="src/PaymentService.java",
            severity="error",
            message="Java parse error near throw",
            extractor="treesitter-java",
            span=SourceSpan(
                file_path="src/PaymentService.java",
                start_byte=0,
                end_byte=10,
                start_line=5,
                start_col=2,
                end_line=5,
                end_col=20,
            ),
            code="parse_error",
            metadata={"node": "ERROR"},
        )
    ]
    if include_vendor_diagnostic:
        diagnostics.append(
            DiagnosticFact(
                file_path="third_party/googletest/gtest.cc",
                severity="error",
                message="C++ parse error in vendored googletest",
                extractor="treesitter-cpp",
                span=SourceSpan(
                    file_path="third_party/googletest/gtest.cc",
                    start_byte=0,
                    end_byte=len(vendor_source.encode("utf-8")),
                    start_line=1,
                    start_col=0,
                    end_line=1,
                    end_col=len(vendor_source),
                ),
                code="parse_error",
                metadata={"node": "ERROR"},
            )
        )
    if include_related_diagnostic:
        diagnostics.append(
            DiagnosticFact(
                file_path="include/PaymentService.hpp",
                severity="error",
                message="C++ parse error in related header",
                extractor="treesitter-cpp",
                span=SourceSpan(
                    file_path="include/PaymentService.hpp",
                    start_byte=0,
                    end_byte=len(related_source.encode("utf-8")),
                    start_line=1,
                    start_col=0,
                    end_line=1,
                    end_col=len(related_source),
                ),
                code="parse_error",
                metadata={"node": "ERROR"},
            )
        )
    if include_unrelated_diagnostic:
        diagnostics.append(
            DiagnosticFact(
                file_path="src/Unrelated.cpp",
                severity="error",
                message="C++ parse error in unrelated source",
                extractor="treesitter-cpp",
                span=SourceSpan(
                    file_path="src/Unrelated.cpp",
                    start_byte=0,
                    end_byte=len(unrelated_source.encode("utf-8")),
                    start_line=1,
                    start_col=0,
                    end_line=1,
                    end_col=len(unrelated_source),
                ),
                code="parse_error",
                metadata={"node": "ERROR"},
            )
        )
    store.insert_diagnostics(snapshot_id, diagnostics, file_ids)
    store.insert_chunks(
        [
            ChunkFact(
                file_path="src/PaymentService.java",
                node_key="java:src/PaymentService.java#PaymentService",
                kind="definition",
                start_line=1,
                end_line=7,
                text=service_source,
                token_estimate=42,
            ),
            ChunkFact(
                file_path="src/PaymentService.java",
                node_key="java:src/PaymentService.java#PaymentService.authorize()",
                kind="definition",
                start_line=2,
                end_line=4,
                text=(
                    "  boolean authorize() {\n"
                    "    return validatePayment() && helper();\n"
                    "  }\n"
                ),
                token_estimate=15,
            ),
            ChunkFact(
                file_path="src/PaymentService.java",
                node_key=(
                    "java:src/PaymentService.java#PaymentService.validatePayment()"
                ),
                kind="definition",
                start_line=5,
                end_line=5,
                text=(
                    "  boolean validatePayment() { "
                    "throw new IllegalStateException(); }\n"
                ),
                token_estimate=14,
            ),
            ChunkFact(
                file_path="src/PaymentService.java",
                node_key="java:src/PaymentService.java#PaymentService.helper()",
                kind="definition",
                start_line=6,
                end_line=6,
                text="  boolean helper() { return true; }\n",
                token_estimate=8,
            ),
            ChunkFact(
                file_path="test/PaymentServiceFailureTest.java",
                node_key=(
                    "java:test/PaymentServiceFailureTest.java#"
                    "authorize_failsInvalidPayment()"
                ),
                kind="definition",
                start_line=2,
                end_line=4,
                text=(
                    "  void authorize_failsInvalidPayment() {\n"
                    "    new PaymentService().authorize();\n"
                    "  }\n"
                ),
                token_estimate=15,
            ),
        ],
        file_ids,
        node_ids,
    )
    return snapshot_id


def _seed_dependencies_graph(store: GraphStore, repo: Path) -> int:
    service_source = (
        "package acme;\n"
        "import java.util.List;\n"
        "class PaymentService {\n"
        "  private Gateway gateway;\n"
        "  boolean authorize() {\n"
        "    return gateway.ready() && validate();\n"
        "  }\n"
        "  boolean validate() { return true; }\n"
        "}\n"
    )
    gateway_source = "class Gateway {}\n"
    _write(repo / "src" / "PaymentService.java", service_source)
    _write(repo / "src" / "Gateway.java", gateway_source)
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    file_ids = store.insert_files(
        snapshot_id,
        [
            FileRecord(
                path="src/PaymentService.java",
                language="java",
                content_hash="service-dependencies",
                size_bytes=len(service_source.encode("utf-8")),
                line_count=9,
            ),
            FileRecord(
                path="src/Gateway.java",
                language="java",
                content_hash="gateway-dependencies",
                size_bytes=len(gateway_source.encode("utf-8")),
                line_count=1,
            ),
        ],
    )
    nodes = [
        _java_node(
            "type",
            "PaymentService",
            "acme.PaymentService",
            "java:src/PaymentService.java#PaymentService",
            "src/PaymentService.java",
            3,
            9,
        ),
        _java_node(
            "field",
            "gateway",
            "acme.PaymentService.gateway",
            "java:src/PaymentService.java#PaymentService.gateway",
            "src/PaymentService.java",
            4,
            4,
        ),
        _java_node(
            "callable",
            "authorize",
            "acme.PaymentService.authorize()",
            "java:src/PaymentService.java#PaymentService.authorize()",
            "src/PaymentService.java",
            5,
            7,
        ),
        _java_node(
            "callable",
            "validate",
            "acme.PaymentService.validate()",
            "java:src/PaymentService.java#PaymentService.validate()",
            "src/PaymentService.java",
            8,
            8,
        ),
        _java_node(
            "type",
            "Gateway",
            "acme.Gateway",
            "java:src/Gateway.java#Gateway",
            "src/Gateway.java",
            1,
            1,
        ),
    ]
    node_ids = store.insert_nodes(snapshot_id, nodes, file_ids)
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
            )
        ],
        file_ids,
        node_ids,
    )
    store.insert_edges(
        snapshot_id,
        [
            _edge(
                "uses_type",
                "java:src/PaymentService.java#PaymentService.authorize()",
                "java:src/Gateway.java#Gateway",
                "src/PaymentService.java",
                4,
            ),
            _edge(
                "references",
                "java:src/PaymentService.java#PaymentService.authorize()",
                "java:src/PaymentService.java#PaymentService.gateway",
                "src/PaymentService.java",
                6,
            ),
            _edge(
                "calls",
                "java:src/PaymentService.java#PaymentService.authorize()",
                "java:src/PaymentService.java#PaymentService.validate()",
                "src/PaymentService.java",
                6,
            ),
        ],
        file_ids,
        node_ids,
    )
    store.insert_chunks(
        [
            ChunkFact(
                file_path="src/PaymentService.java",
                node_key="java:src/PaymentService.java#PaymentService",
                kind="definition",
                start_line=3,
                end_line=9,
                text=service_source.split("\n", 2)[2],
                token_estimate=34,
            ),
            ChunkFact(
                file_path="src/PaymentService.java",
                node_key="java:src/PaymentService.java#PaymentService.gateway",
                kind="definition",
                start_line=4,
                end_line=4,
                text="  private Gateway gateway;\n",
                token_estimate=7,
            ),
            ChunkFact(
                file_path="src/PaymentService.java",
                node_key="java:src/PaymentService.java#PaymentService.authorize()",
                kind="definition",
                start_line=5,
                end_line=7,
                text=(
                    "  boolean authorize() {\n"
                    "    return gateway.ready() && validate();\n"
                    "  }\n"
                ),
                token_estimate=15,
            ),
            ChunkFact(
                file_path="src/PaymentService.java",
                node_key="java:src/PaymentService.java#PaymentService.validate()",
                kind="definition",
                start_line=8,
                end_line=8,
                text="  boolean validate() { return true; }\n",
                token_estimate=9,
            ),
            ChunkFact(
                file_path="src/Gateway.java",
                node_key="java:src/Gateway.java#Gateway",
                kind="definition",
                start_line=1,
                end_line=1,
                text=gateway_source,
                token_estimate=4,
            ),
        ],
        file_ids,
        node_ids,
    )
    return snapshot_id


def _seed_call_neighborhood_graph(
    store: GraphStore, repo: Path, *, include_caller_chunk: bool = True
) -> int:
    source = (
        "class Foo {\n"
        "  void controller() { target(); }\n"
        "  void helper() {}\n"
        "  void target() {\n"
        "    validate();\n"
        "    externalGateway.charge();\n"
        "  }\n"
        "  void validate() {}\n"
        "}\n"
    )
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
                content_hash="call-neighborhood",
                size_bytes=len(source.encode("utf-8")),
                line_count=9,
            )
        ],
    )
    nodes = [
        _java_node(
            "type",
            "Foo",
            "Foo",
            "java:src/Foo.java#Foo",
            "src/Foo.java",
            1,
            9,
        ),
        _java_node(
            "callable",
            "controller",
            "Foo.controller()",
            "java:src/Foo.java#Foo.controller()",
            "src/Foo.java",
            2,
            2,
        ),
        _java_node(
            "callable",
            "target",
            "Foo.target()",
            "java:src/Foo.java#Foo.target()",
            "src/Foo.java",
            4,
            7,
        ),
        _java_node(
            "callable",
            "validate",
            "Foo.validate()",
            "java:src/Foo.java#Foo.validate()",
            "src/Foo.java",
            8,
            8,
        ),
    ]
    node_ids = store.insert_nodes(snapshot_id, nodes, file_ids)
    store.insert_edges(
        snapshot_id,
        [
            _edge(
                "calls",
                "java:src/Foo.java#Foo.target()",
                "java:src/Foo.java#Foo.validate()",
                "src/Foo.java",
                5,
            ),
            _edge(
                "calls",
                "java:src/Foo.java#Foo.target()",
                None,
                "src/Foo.java",
                6,
                unresolved_dst="externalGateway.charge",
                confidence=0.35,
            ),
            _edge(
                "calls",
                "java:src/Foo.java#Foo.controller()",
                "java:src/Foo.java#Foo.target()",
                "src/Foo.java",
                2,
            ),
        ],
        file_ids,
        node_ids,
    )
    chunks = [
        ChunkFact(
            file_path="src/Foo.java",
            node_key="java:src/Foo.java#Foo",
            kind="definition",
            start_line=1,
            end_line=9,
            text=source,
            token_estimate=40,
        ),
        ChunkFact(
            file_path="src/Foo.java",
            node_key="java:src/Foo.java#Foo.target()",
            kind="definition",
            start_line=4,
            end_line=7,
            text=(
                "  void target() {\n"
                "    validate();\n"
                "    externalGateway.charge();\n"
                "  }\n"
            ),
            token_estimate=16,
        ),
        ChunkFact(
            file_path="src/Foo.java",
            node_key="java:src/Foo.java#Foo.validate()",
            kind="definition",
            start_line=8,
            end_line=8,
            text="  void validate() {}\n",
            token_estimate=5,
        ),
    ]
    if include_caller_chunk:
        chunks.insert(
            1,
            ChunkFact(
                file_path="src/Foo.java",
                node_key="java:src/Foo.java#Foo.controller()",
                kind="definition",
                start_line=2,
                end_line=2,
                text="  void controller() { target(); }\n",
                token_estimate=8,
            ),
        )
    store.insert_chunks(chunks, file_ids, node_ids)
    return snapshot_id


def _seed_budget_ranking_graph(store: GraphStore, repo: Path) -> int:
    source = (
        "class Foo {\n"
        "  void run() { expensive(); cheap(); }\n"
        "  void expensive() {}\n"
        "  void cheap() {}\n"
        "  void lowValue() {}\n"
        "}\n"
    )
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
                content_hash="budget",
                size_bytes=len(source.encode("utf-8")),
                line_count=6,
            )
        ],
    )
    node_ids = store.insert_nodes(
        snapshot_id,
        [
            _java_node(
                "callable",
                "run",
                "Foo.run()",
                "java:src/Foo.java#run",
                "src/Foo.java",
                2,
                2,
            ),
            _java_node(
                "callable",
                "expensive",
                "Foo.expensive()",
                "java:src/Foo.java#expensive",
                "src/Foo.java",
                3,
                3,
            ),
            _java_node(
                "callable",
                "cheap",
                "Foo.cheap()",
                "java:src/Foo.java#cheap",
                "src/Foo.java",
                4,
                4,
            ),
            _java_node(
                "callable",
                "lowValue",
                "Foo.lowValue()",
                "java:src/Foo.java#lowValue",
                "src/Foo.java",
                5,
                5,
            ),
        ],
        file_ids,
    )
    store.insert_edges(
        snapshot_id,
        [
            _edge(
                "calls",
                "java:src/Foo.java#run",
                "java:src/Foo.java#expensive",
                "src/Foo.java",
                2,
            ),
            _edge(
                "calls",
                "java:src/Foo.java#run",
                "java:src/Foo.java#cheap",
                "src/Foo.java",
                2,
            ),
        ],
        file_ids,
        node_ids,
    )
    store.insert_chunks(
        [
            ChunkFact(
                file_path="src/Foo.java",
                node_key="java:src/Foo.java#run",
                kind="definition",
                start_line=2,
                end_line=2,
                text="  void run() { expensive(); cheap(); }\n",
                token_estimate=10,
            ),
            ChunkFact(
                file_path="src/Foo.java",
                node_key="java:src/Foo.java#expensive",
                kind="definition",
                start_line=3,
                end_line=3,
                text="  void expensive() {}\n",
                token_estimate=40,
            ),
            ChunkFact(
                file_path="src/Foo.java",
                node_key="java:src/Foo.java#cheap",
                kind="definition",
                start_line=4,
                end_line=4,
                text="  void cheap() {}\n",
                token_estimate=5,
            ),
            ChunkFact(
                file_path="src/Foo.java",
                node_key="java:src/Foo.java#lowValue",
                kind="definition",
                start_line=5,
                end_line=5,
                text="  void lowValue() {}\n",
                token_estimate=5,
            ),
        ],
        file_ids,
        node_ids,
    )
    return snapshot_id


def _seed_overlap_graph(store: GraphStore, repo: Path) -> int:
    source = "class Foo {\n  void run() { helper(); }\n  void helper() {}\n}\n"
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
                content_hash="overlap",
                size_bytes=len(source.encode("utf-8")),
                line_count=4,
            )
        ],
    )
    node_ids = store.insert_nodes(
        snapshot_id,
        [
            _java_node(
                "callable",
                "run",
                "Foo.run()",
                "java:src/Foo.java#run",
                "src/Foo.java",
                2,
                2,
            ),
            _java_node(
                "callable",
                "helper",
                "Foo.helper()",
                "java:src/Foo.java#helper",
                "src/Foo.java",
                3,
                3,
            ),
        ],
        file_ids,
    )
    store.insert_edges(
        snapshot_id,
        [
            _edge(
                "calls",
                "java:src/Foo.java#run",
                "java:src/Foo.java#helper",
                "src/Foo.java",
                2,
            ),
            _edge(
                "references",
                "java:src/Foo.java#run",
                "java:src/Foo.java#helper",
                "src/Foo.java",
                2,
            ),
        ],
        file_ids,
        node_ids,
    )
    store.insert_chunks(
        [
            ChunkFact(
                file_path="src/Foo.java",
                node_key="java:src/Foo.java#run",
                kind="definition",
                start_line=2,
                end_line=2,
                text="  void run() { helper(); }\n",
                token_estimate=8,
            ),
            ChunkFact(
                file_path="src/Foo.java",
                node_key="java:src/Foo.java#helper",
                kind="definition",
                start_line=4,
                end_line=4,
                text="  void helper() {}\n",
                token_estimate=5,
            ),
            ChunkFact(
                file_path="src/Foo.java",
                node_key=None,
                kind="definition",
                start_line=4,
                end_line=4,
                text="  void helper() {}\n",
                token_estimate=5,
            ),
        ],
        file_ids,
        node_ids,
    )
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


def _seed_invalid_source_fallback_graph(store: GraphStore, repo: Path) -> int:
    path = repo / "src" / "Bad.java"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"class Bad {\xff}\n")
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    store.insert_files(
        snapshot_id,
        [
            FileRecord(
                path="src/Bad.java",
                language="java",
                content_hash="invalid-utf8",
                size_bytes=13,
                line_count=1,
            ),
        ],
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


def _java_node(
    kind: str,
    name: str,
    qualified_name: str,
    symbol_key: str,
    file_path: str,
    start_line: int,
    end_line: int,
) -> NodeFact:
    return NodeFact(
        kind=kind,
        language="java",
        name=name,
        qualified_name=qualified_name,
        symbol_key=symbol_key,
        file_path=file_path,
        span=SourceSpan(
            file_path=file_path,
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


def _edge(
    kind: str,
    src_key: str,
    dst_key: str | None,
    file_path: str,
    line: int,
    *,
    unresolved_dst: str | None = None,
    confidence: float = 0.8,
) -> EdgeFact:
    return EdgeFact(
        kind=kind,
        src_key=src_key,
        dst_key=dst_key,
        unresolved_src=None,
        unresolved_dst=unresolved_dst,
        file_path=file_path,
        span=SourceSpan(
            file_path=file_path,
            start_byte=0,
            end_byte=10,
            start_line=line,
            start_col=0,
            end_line=line,
            end_col=10,
        ),
        confidence=confidence,
        extractor="test",
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
