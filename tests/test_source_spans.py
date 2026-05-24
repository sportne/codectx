from __future__ import annotations

from codectx.source.spans import SourceSpan


def test_source_span_contains_inclusive_line_range() -> None:
    span = SourceSpan(
        file_path="src/main/java/acme/PaymentService.java",
        start_byte=10,
        end_byte=100,
        start_line=3,
        start_col=2,
        end_line=8,
        end_col=1,
    )

    assert not span.contains_line(2)
    assert span.contains_line(3)
    assert span.contains_line(6)
    assert span.contains_line(8)
    assert not span.contains_line(9)
