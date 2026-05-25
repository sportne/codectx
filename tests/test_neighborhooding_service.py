from __future__ import annotations

from pathlib import Path

from codectx.neighborhooding import NeighborhoodPlaceholderResult, build_neighborhood


def test_build_neighborhood_returns_placeholder_response(tmp_path: Path) -> None:
    result = build_neighborhood(
        tmp_path,
        "PaymentService",
        db_path=tmp_path / "graph.sqlite",
        depth=2,
    )

    assert isinstance(result, NeighborhoodPlaceholderResult)
    assert "codectx command 'neighborhood' is defined but not implemented yet." in (
        result.message
    )
    assert "docs/04-task-decomposition.md" in result.message
