from __future__ import annotations

from codectx.context.bundle import ContextBundle, ContextItem, OmittedItem


def test_context_bundle_serializes_to_plain_dictionary() -> None:
    item = ContextItem(
        rank=1,
        kind="definition",
        file="src/main/java/acme/PaymentService.java",
        line_range=(10, 20),
        text="class PaymentService {}",
        score=0.95,
        token_estimate=42,
        reason="anchor definition",
        confidence=1.0,
        extractor="java-tree-sitter",
        metadata={"symbol": "PaymentService"},
    )
    omitted = OmittedItem(name="PaymentRepository", reason="budget", score=0.25)
    bundle = ContextBundle(
        query={"goal": "explain"},
        anchor={"symbol": "PaymentService"},
        index_health={"integrity": "ok"},
        items=[item],
        omitted=[omitted],
        uncertainty_notes=["heuristic call edge omitted"],
        trace=[{"stage": "rank"}],
    )

    assert bundle.to_dict() == {
        "query": {"goal": "explain"},
        "anchor": {"symbol": "PaymentService"},
        "index_health": {"integrity": "ok"},
        "items": [
            {
                "rank": 1,
                "kind": "definition",
                "file": "src/main/java/acme/PaymentService.java",
                "line_range": (10, 20),
                "text": "class PaymentService {}",
                "score": 0.95,
                "token_estimate": 42,
                "reason": "anchor definition",
                "confidence": 1.0,
                "extractor": "java-tree-sitter",
                "metadata": {"symbol": "PaymentService"},
            }
        ],
        "omitted": [{"name": "PaymentRepository", "reason": "budget", "score": 0.25}],
        "uncertainty_notes": ["heuristic call edge omitted"],
        "trace": [{"stage": "rank"}],
    }
