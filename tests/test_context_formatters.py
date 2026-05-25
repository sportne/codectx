from __future__ import annotations

from json import loads

from codectx.context.bundle import ContextBundle, ContextItem, OmittedItem
from codectx.context.formatters import format_json, format_markdown, format_text


def test_format_markdown_renders_bundle_with_balanced_code_fences() -> None:
    bundle = _bundle()

    rendered = format_markdown(bundle)

    assert rendered.startswith("# codectx context bundle\n")
    assert "- goal: explain" in rendered
    assert "- file: src/Foo.java" in rendered
    assert "## Index Health" in rendered
    assert "- files: 1" in rendered
    assert "### 1. target.definition" in rendered
    assert "- file: src/Foo.java:2-4" in rendered
    assert "- reason: target definition" in rendered
    assert "- confidence: 0.95" in rendered
    assert "```java\nclass Foo {}\n```" in rendered
    assert "- src/Foo.java:9: budget score=0.5" in rendered
    assert "- parse diagnostics omitted" in rendered
    assert "- stage=rank" in rendered
    assert rendered.count("```") == 2


def test_format_markdown_renders_empty_sections_and_unknown_location() -> None:
    bundle = ContextBundle(
        query={},
        anchor={"file": None},
        index_health={},
        items=[
            ContextItem(
                rank=1,
                kind="note",
                file=None,
                line_range=None,
                text="plain text",
                score=1.0,
                token_estimate=3,
                reason="fallback",
                confidence=0.5,
                extractor=None,
            )
        ],
        omitted=[OmittedItem(name=None, reason="duplicate", score=None)],
        trace=[{}],
    )

    rendered = format_markdown(bundle)

    assert "- none" in rendered
    assert "- file: <unknown>" in rendered
    assert "```\nplain text\n```" in rendered
    assert "- <unnamed>: duplicate" in rendered
    assert "## Uncertainty\nNone." in rendered
    assert "## Trace\n- none" in rendered


def test_format_markdown_renders_single_line_and_extension_languages() -> None:
    bundle = ContextBundle(
        query={"goal": "explain"},
        anchor={"line": 1},
        index_health={"integrity": None},
        items=[
            ContextItem(
                rank=1,
                kind="cpp",
                file="src/main.cpp",
                line_range=(1, 1),
                text="int main() {}\n",
                score=1.0,
                token_estimate=4,
                reason="target",
                confidence=1.0,
                extractor=None,
            ),
            ContextItem(
                rank=2,
                kind="text",
                file="README",
                line_range=None,
                text="read me\n",
                score=0.5,
                token_estimate=2,
                reason="file",
                confidence=1.0,
                extractor=None,
            ),
        ],
    )

    rendered = format_markdown(bundle)

    assert "- integrity: <none>" in rendered
    assert "- file: src/main.cpp:1" in rendered
    assert "```cpp\nint main() {}\n```" in rendered
    assert "- file: README" in rendered


def test_format_markdown_uses_longer_fence_for_embedded_backticks() -> None:
    bundle = ContextBundle(
        query={"goal": "explain"},
        anchor={"file": "README.md"},
        index_health={},
        items=[
            ContextItem(
                rank=1,
                kind="markdown",
                file="README.md",
                line_range=(1, 3),
                text="before\n```python\nprint('nested')\n```\nafter\n",
                score=1.0,
                token_estimate=10,
                reason="target",
                confidence=1.0,
                extractor=None,
            )
        ],
    )

    rendered = format_markdown(bundle)

    assert "````\nbefore\n```python\nprint('nested')\n```\nafter\n````" in rendered
    assert rendered.count("````") == 2


def test_format_json_serializes_bundle_with_required_fields() -> None:
    rendered = format_json(_bundle())

    parsed = loads(rendered)

    assert parsed["query"]["goal"] == "explain"
    assert parsed["anchor"]["file"] == "src/Foo.java"
    assert parsed["index_health"]["files"] == "1"
    assert parsed["items"][0]["line_range"] == [2, 4]
    assert parsed["items"][0]["text"] == "class Foo {}\n"
    assert parsed["items"][0]["score"] == 5.0
    assert parsed["items"][0]["reason"] == "target definition"
    assert parsed["items"][0]["confidence"] == 0.95
    assert parsed["items"][0]["metadata"] == {"symbol": "Foo"}
    assert parsed["omitted"][0]["reason"] == "budget"
    assert parsed["uncertainty_notes"] == ["parse diagnostics omitted"]
    assert parsed["trace"] == [{"stage": "rank"}]
    assert rendered.endswith("\n")


def test_format_text_renders_plain_text_bundle() -> None:
    rendered = format_text(_bundle())

    assert rendered.startswith("codectx context bundle\n")
    assert "Query\n- budget: 100\n- goal: explain" in rendered
    assert "Anchor\n- file: src/Foo.java" in rendered
    assert "Index Health\n- files: 1\n- nodes: 1" in rendered
    assert "1. target.definition" in rendered
    assert "file: src/Foo.java:2-4" in rendered
    assert "reason: target definition" in rendered
    assert "score: 5" in rendered
    assert "confidence: 0.95" in rendered
    assert "tokens: 4" in rendered
    assert "extractor: test" in rendered
    assert "snippet:\nclass Foo {}\n" in rendered
    assert "- src/Foo.java:9: budget score=0.5" in rendered
    assert "- parse diagnostics omitted" in rendered
    assert "```" not in rendered


def test_format_text_renders_empty_sections() -> None:
    rendered = format_text(
        ContextBundle(query={}, anchor={}, index_health={}, items=[])
    )

    assert "Query\n- none" in rendered
    assert "Context Items\nNo context items selected." in rendered
    assert "Omitted\nNone." in rendered
    assert "Uncertainty\nNone." in rendered
    assert "Trace\nNone." in rendered


def _bundle() -> ContextBundle:
    return ContextBundle(
        query={"goal": "explain", "budget": 100},
        anchor={"file": "src/Foo.java", "line": 3, "node_id": 1},
        index_health={"files": "1", "nodes": "1"},
        items=[
            ContextItem(
                rank=1,
                kind="target.definition",
                file="src/Foo.java",
                line_range=(2, 4),
                text="class Foo {}\n",
                score=5.0,
                token_estimate=4,
                reason="target definition",
                confidence=0.95,
                extractor="test",
                metadata={"symbol": "Foo"},
            )
        ],
        omitted=[OmittedItem(name="src/Foo.java:9", reason="budget", score=0.5)],
        uncertainty_notes=["parse diagnostics omitted"],
        trace=[{"stage": "rank"}],
    )
