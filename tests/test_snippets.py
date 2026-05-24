from __future__ import annotations

import pytest

from codectx.source.snippets import (
    SourceSnippet,
    snippet_by_byte_span,
    snippet_by_line_range,
)
from codectx.source.tokens import estimate_token_count


def test_snippet_by_byte_span_returns_exact_utf8_text() -> None:
    content = "alpha\nb\u00e9ta\ngamma"
    content_bytes = content.encode()
    start_byte = content_bytes.index("b\u00e9ta".encode())
    end_byte = start_byte + len("b\u00e9ta".encode())

    snippet = snippet_by_byte_span("src/Foo.java", content, start_byte, end_byte)

    assert snippet == SourceSnippet(
        file_path="src/Foo.java",
        text="b\u00e9ta",
        start_line=2,
        end_line=2,
        start_byte=6,
        end_byte=11,
        token_estimate=1,
    )


def test_snippet_by_line_range_returns_complete_lines() -> None:
    snippet = snippet_by_line_range("src/Foo.java", "one\ntwo\nthree", 2, 2)

    assert snippet.text == "two\n"
    assert snippet.start_line == 2
    assert snippet.end_line == 2
    assert snippet.start_byte == 4
    assert snippet.end_byte == 8


def test_snippet_by_line_range_expands_context_and_clamps_to_file_bounds() -> None:
    snippet = snippet_by_line_range(
        "src/Foo.java", "one\ntwo\nthree\nfour\n", 2, 3, context_lines=2
    )

    assert snippet.text == "one\ntwo\nthree\nfour\n"
    assert snippet.start_line == 1
    assert snippet.end_line == 4


def test_snippet_by_byte_span_expands_context_to_complete_lines() -> None:
    content = b"one\ntwo\nthree\n"

    snippet = snippet_by_byte_span(
        "src/Foo.java", content, start_byte=4, end_byte=7, context_lines=1
    )

    assert snippet.text == "one\ntwo\nthree\n"
    assert snippet.start_line == 1
    assert snippet.end_line == 3


def test_snippet_rejects_negative_context_lines() -> None:
    with pytest.raises(ValueError, match="context_lines"):
        snippet_by_line_range("src/Foo.java", "one\n", 1, 1, context_lines=-1)

    with pytest.raises(ValueError, match="context_lines"):
        snippet_by_byte_span("src/Foo.java", "one\n", 0, 1, context_lines=-1)


@pytest.mark.parametrize(
    ("start_line", "end_line"),
    [
        (0, 1),
        (2, 1),
        (1, 999),
    ],
)
def test_snippet_by_line_range_rejects_invalid_requested_range(
    start_line: int, end_line: int
) -> None:
    with pytest.raises(ValueError, match="line range"):
        snippet_by_line_range(
            "src/Foo.java",
            "one\ntwo\n",
            start_line,
            end_line,
            context_lines=1,
        )


def test_estimate_token_count_uses_ceil_chars_over_four() -> None:
    assert estimate_token_count("") == 0
    assert estimate_token_count("a") == 1
    assert estimate_token_count("abcd") == 1
    assert estimate_token_count("abcde") == 2
