from __future__ import annotations

from codectx.context.ranking import RankingAnchor, RankingCandidate, score_candidate


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
