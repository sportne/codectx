from __future__ import annotations

import pytest

from codectx.source.spans import (
    SourceSpan,
    byte_range_to_span,
    byte_to_line_col,
    line_count,
    line_range_to_byte_range,
    line_start_offsets,
)


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


def test_line_start_offsets_and_line_count() -> None:
    content = "alpha\nb\u00e9ta\ngamma".encode()

    assert line_start_offsets(content) == (0, 6, 12)
    assert line_count(content) == 3
    assert line_start_offsets(b"") == ()
    assert line_count(b"") == 0


def test_byte_to_line_col_uses_utf8_byte_columns() -> None:
    content = "a\nb\u00e9ta\n".encode()
    starts = line_start_offsets(content)

    assert byte_to_line_col(starts, 0, content_length=len(content)) == (1, 0)
    assert byte_to_line_col(starts, 2, content_length=len(content)) == (2, 0)
    assert byte_to_line_col(starts, 4, content_length=len(content)) == (2, 2)
    assert byte_to_line_col(starts, len(content), content_length=len(content)) == (
        2,
        6,
    )


def test_byte_to_line_col_rejects_invalid_offsets() -> None:
    starts = (5,)

    with pytest.raises(ValueError, match="non-negative"):
        byte_to_line_col(starts, -1)
    with pytest.raises(ValueError, match="content length"):
        byte_to_line_col((0,), 2, content_length=1)
    with pytest.raises(ValueError, match="empty"):
        byte_to_line_col((), 0)
    with pytest.raises(ValueError, match="precedes"):
        byte_to_line_col(starts, 4)


def test_byte_range_to_span_round_trips_known_utf8_position() -> None:
    content = "alpha\nb\u00e9ta\ngamma".encode()
    start_byte = content.index("b\u00e9ta".encode())
    end_byte = start_byte + len("b\u00e9ta".encode())

    span = byte_range_to_span("src/Foo.java", content, start_byte, end_byte)

    assert span == SourceSpan(
        file_path="src/Foo.java",
        start_byte=6,
        end_byte=11,
        start_line=2,
        start_col=0,
        end_line=2,
        end_col=5,
    )


def test_byte_range_to_span_end_line_is_inclusive_for_exclusive_range() -> None:
    span = byte_range_to_span("src/Foo.java", b"one\ntwo", 0, 4)

    assert span.end_line == 1
    assert span.end_col == 4
    assert span.contains_line(1)
    assert not span.contains_line(2)


def test_byte_range_to_span_rejects_invalid_range() -> None:
    with pytest.raises(ValueError, match="byte range"):
        byte_range_to_span("src/Foo.java", b"abc", 2, 1)


def test_line_range_to_byte_range_includes_complete_lines() -> None:
    content = b"one\ntwo\nthree"

    start_byte, end_byte = line_range_to_byte_range(content, 2, 2)

    assert content[start_byte:end_byte] == b"two\n"


def test_line_range_to_byte_range_rejects_out_of_bounds_range() -> None:
    with pytest.raises(ValueError, match="line range"):
        line_range_to_byte_range(b"one\n", 2, 2)
