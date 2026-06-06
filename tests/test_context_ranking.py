from __future__ import annotations

from codectx.context.ranking import (
    RankingAnchor,
    RankingCandidate,
    score_candidate,
    score_file_candidate,
)


def test_score_candidate_prefers_target_definition_over_unrelated_sibling() -> None:
    anchor = RankingAnchor(
        file_path="src/Foo.java",
        line=3,
        node_name="run",
        qualified_name="Foo.run()",
        symbol_key="java:src/Foo.java#run",
    )

    target = score_candidate(
        RankingCandidate(
            kind="target.definition",
            file_path="src/Foo.java",
            line_range=(2, 4),
            text="void run() {}\n",
            token_estimate=4,
            confidence=1.0,
            metadata={"node_name": "run", "qualified_name": "Foo.run()"},
        ),
        anchor,
        query_text="run",
    )
    sibling = score_candidate(
        RankingCandidate(
            kind="sibling.definition",
            file_path="src/Foo.java",
            line_range=(20, 22),
            text="void unrelated() {}\n",
            token_estimate=6,
            confidence=1.0,
            metadata={"node_name": "unrelated", "qualified_name": "Foo.unrelated()"},
        ),
        anchor,
        query_text="run",
    )

    assert target.score > sibling.score
    assert target.score_trace["target"] == 5.0
    assert target.score_trace["exact_match"] == 3.0
    assert sibling.score_trace["target"] == 0.0
    assert sibling.score_trace["exact_match"] == 0.0
    assert target.score_trace["total"] == target.score


def test_score_file_candidate_boosts_file_symbols_without_line_proximity() -> None:
    symbol = score_file_candidate(
        RankingCandidate(
            kind="file.symbol",
            file_path="src/Foo.java",
            line_range=(50, 55),
            text="void run() {}\n",
            token_estimate=4,
            confidence=1.0,
            metadata={"node_name": "run"},
        ),
        "src/Foo.java",
        query_text="src/Foo.java",
    )
    external = score_file_candidate(
        RankingCandidate(
            kind="neighborhood.callee",
            file_path="src/Helper.java",
            line_range=(1, 1),
            text="void helper() {}\n",
            token_estimate=4,
            confidence=1.0,
            metadata={"edge_id": 1, "edge_kind": "calls", "node_name": "helper"},
        ),
        "src/Foo.java",
        query_text="src/Foo.java",
    )

    assert symbol.score > external.score
    assert symbol.score_trace["file_symbol"] == 2.2
    assert symbol.score_trace["same_file"] == 1.4
    assert symbol.score_trace["source_proximity"] == 0.0
    assert external.score_trace["graph_proximity"] == 1.5


def test_score_candidate_records_edge_test_confidence_and_token_components() -> None:
    anchor = RankingAnchor(file_path="src/Foo.java", line=10, node_name="run")

    scored = score_candidate(
        RankingCandidate(
            kind="neighborhood.callee",
            file_path="test/FooTest.java",
            line_range=(8, 12),
            text="void run_invokes_helper() {}\n",
            token_estimate=25,
            confidence=0.4,
            metadata={"edge_id": 12, "edge_kind": "calls", "node_name": "helper"},
        ),
        anchor,
        query_text="run",
    )

    assert scored.score_trace == {
        "target": 0.0,
        "exact_match": 0.0,
        "edge_relevance": 2.0,
        "graph_proximity": 1.5,
        "source_proximity": 0.0,
        "lexical_match": 1.0,
        "enclosing_context": 0.0,
        "test_context": 0.7,
        "confidence": 0.2,
        "token_cost": -0.02,
        "redundancy": 0.0,
        "total": 5.38,
    }


def test_score_candidate_applies_goal_specific_edge_weights() -> None:
    anchor = RankingAnchor(file_path="src/Foo.java", line=1, node_name="Foo")
    call = RankingCandidate(
        kind="neighborhood.callee",
        file_path="src/Foo.java",
        line_range=(3, 3),
        text="void helper() {}\n",
        token_estimate=5,
        confidence=1.0,
        metadata={"edge_id": 1, "edge_kind": "calls", "node_name": "helper"},
    )
    dependency = RankingCandidate(
        kind="neighborhood.type",
        file_path="src/Bar.java",
        line_range=(1, 1),
        text="class Bar {}\n",
        token_estimate=4,
        confidence=1.0,
        metadata={"edge_id": 2, "edge_kind": "uses_type", "node_name": "Bar"},
    )

    call_neighborhood_call = score_candidate(
        call, anchor, goal="call-neighborhood"
    ).score_trace["edge_relevance"]
    call_neighborhood_dependency = score_candidate(
        dependency, anchor, goal="call-neighborhood"
    ).score_trace["edge_relevance"]
    dependencies_call = score_candidate(call, anchor, goal="dependencies").score_trace[
        "edge_relevance"
    ]
    dependencies_dependency = score_candidate(
        dependency, anchor, goal="dependencies"
    ).score_trace["edge_relevance"]
    failure_references = score_candidate(
        RankingCandidate(
            kind="neighborhood.reference",
            file_path="src/Foo.java",
            line_range=(4, 4),
            text="field",
            token_estimate=2,
            confidence=1.0,
            metadata={"edge_id": 3, "edge_kind": "references"},
        ),
        anchor,
        goal="failure-modes",
    ).score_trace["edge_relevance"]

    assert call_neighborhood_call > call_neighborhood_dependency
    assert dependencies_dependency > dependencies_call
    assert failure_references > dependencies_call


def test_failure_modes_goal_boosts_error_related_candidates() -> None:
    anchor = RankingAnchor(file_path="src/PaymentService.java", line=5, node_name="pay")
    validation = score_candidate(
        RankingCandidate(
            kind="neighborhood.callee",
            file_path="src/PaymentService.java",
            line_range=(8, 8),
            text="boolean validatePayment() { throw new IllegalStateException(); }\n",
            token_estimate=16,
            confidence=0.8,
            metadata={
                "edge_id": 10,
                "edge_kind": "calls",
                "node_name": "validatePayment",
            },
        ),
        anchor,
        goal="failure-modes",
    )
    helper = score_candidate(
        RankingCandidate(
            kind="neighborhood.callee",
            file_path="src/PaymentService.java",
            line_range=(9, 9),
            text="boolean helper() { return true; }\n",
            token_estimate=8,
            confidence=0.8,
            metadata={"edge_id": 11, "edge_kind": "calls", "node_name": "helper"},
        ),
        anchor,
        goal="failure-modes",
    )

    assert validation.score > helper.score
    assert validation.score_trace["goal_relevance"] == 4.0
    assert "goal_relevance" not in helper.score_trace


def test_failure_modes_goal_scopes_parser_diagnostic_relevance() -> None:
    anchor = RankingAnchor(
        file_path="libs/path_finding/src/a_star.cpp",
        line=201,
        node_name="solve_a_star",
    )

    same_file = score_candidate(
        RankingCandidate(
            kind="diagnostic.parser",
            file_path="libs/path_finding/src/a_star.cpp",
            line_range=(210, 210),
            text="broken macro",
            token_estimate=4,
            confidence=0.8,
            metadata={"diagnostic_relation": "anchor-file"},
        ),
        anchor,
        goal="failure-modes",
    )
    related = score_candidate(
        RankingCandidate(
            kind="diagnostic.parser",
            file_path="libs/path_finding/include/cpp_helper_libs/path_finding/a_star.hpp",
            line_range=(98, 98),
            text="const AStarConfig &config = {}) noexcept;",
            token_estimate=8,
            confidence=0.8,
            metadata={"diagnostic_relation": "related"},
        ),
        anchor,
        goal="failure-modes",
    )
    unrelated = score_candidate(
        RankingCandidate(
            kind="diagnostic.parser",
            file_path="libs/quantities/src/force.cpp",
            line_range=(21, 21),
            text="CPPHL_DEFINE_SCALED_QUANTITY_CORE_METHODS(Force, kToRawScales)",
            token_estimate=12,
            confidence=0.8,
            metadata={"diagnostic_relation": "unrelated"},
        ),
        anchor,
        goal="failure-modes",
    )

    assert same_file.score_trace["goal_relevance"] == 4.0
    assert related.score_trace["goal_relevance"] == 2.0
    assert "goal_relevance" not in unrelated.score_trace


def test_dependencies_goal_boosts_dependency_shaped_candidates() -> None:
    anchor = RankingAnchor(file_path="src/PaymentService.java", line=5)
    used_type = score_candidate(
        RankingCandidate(
            kind="neighborhood.type",
            file_path="src/Gateway.java",
            line_range=(1, 1),
            text="class Gateway {}\n",
            token_estimate=4,
            confidence=0.8,
            metadata={
                "edge_id": 20,
                "edge_kind": "uses_type",
                "node_name": "Gateway",
            },
        ),
        anchor,
        goal="dependencies",
    )
    helper_call = score_candidate(
        RankingCandidate(
            kind="neighborhood.callee",
            file_path="src/PaymentService.java",
            line_range=(8, 8),
            text="boolean validate() { return true; }\n",
            token_estimate=8,
            confidence=0.8,
            metadata={"edge_id": 21, "edge_kind": "calls", "node_name": "validate"},
        ),
        anchor,
        goal="dependencies",
    )
    imported = score_candidate(
        RankingCandidate(
            kind="import",
            file_path="src/PaymentService.java",
            line_range=(2, 2),
            text="import java.util.List;\n",
            token_estimate=6,
            confidence=0.8,
        ),
        anchor,
        goal="dependencies",
    )

    assert used_type.score > helper_call.score
    assert imported.score > helper_call.score
    assert used_type.score_trace["goal_relevance"] == 2.4
    assert imported.score_trace["goal_relevance"] == 2.0


def test_dependencies_goal_boosts_constructor_like_callees() -> None:
    anchor = RankingAnchor(file_path="src/main.cpp", line=10)

    constructor = score_candidate(
        RankingCandidate(
            kind="neighborhood.callee",
            file_path="src/Widget.cpp",
            line_range=(3, 5),
            text="Widget::Widget() {}\n",
            token_estimate=6,
            confidence=0.8,
            metadata={
                "edge_id": 30,
                "edge_kind": "calls",
                "node_kind": "callable",
                "node_name": "Widget",
                "qualified_name": "Widget::Widget()",
            },
        ),
        anchor,
        goal="dependencies",
    )
    regular = score_candidate(
        RankingCandidate(
            kind="neighborhood.callee",
            file_path="src/Widget.cpp",
            line_range=(7, 7),
            text="void tick() {}\n",
            token_estimate=5,
            confidence=0.8,
            metadata={
                "edge_id": 31,
                "edge_kind": "calls",
                "node_kind": "callable",
                "node_name": "tick",
                "qualified_name": "Widget::tick()",
            },
        ),
        anchor,
        goal="dependencies",
    )

    assert constructor.score > regular.score
    assert constructor.score_trace["goal_relevance"] == 1.6


def test_call_neighborhood_goal_boosts_callers_and_callees() -> None:
    anchor = RankingAnchor(file_path="src/Foo.java", line=5, node_name="target")
    caller = score_candidate(
        RankingCandidate(
            kind="neighborhood.caller",
            file_path="src/Foo.java",
            line_range=(1, 3),
            text="void caller() { target(); }\n",
            token_estimate=8,
            confidence=0.7,
            metadata={"edge_id": 40, "edge_kind": "calls", "node_name": "caller"},
        ),
        anchor,
        goal="call-neighborhood",
    )
    sibling = score_candidate(
        RankingCandidate(
            kind="sibling.definition",
            file_path="src/Foo.java",
            line_range=(8, 8),
            text="void helper() {}\n",
            token_estimate=5,
            confidence=0.8,
            metadata={"node_name": "helper"},
        ),
        anchor,
        goal="call-neighborhood",
    )

    assert caller.score > sibling.score
    assert caller.score_trace["goal_relevance"] == 2.0
