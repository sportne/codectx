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
