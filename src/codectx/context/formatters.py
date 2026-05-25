"""Context bundle output formatters."""

from __future__ import annotations

from collections.abc import Mapping
from json import dumps

from codectx.context.bundle import ContextBundle


def format_markdown(bundle: ContextBundle) -> str:
    """Render a context bundle as deterministic Markdown."""
    lines: list[str] = [
        "# codectx context bundle",
        "",
        "## Query",
    ]
    lines.extend(_mapping_lines(bundle.query))
    lines.extend(["", "## Anchor"])
    lines.extend(_mapping_lines(bundle.anchor))
    lines.extend(["", "## Index Health"])
    lines.extend(_mapping_lines(bundle.index_health))
    lines.extend(["", "## Context Items"])
    if not bundle.items:
        lines.append("No context items selected.")
    for item in bundle.items:
        location = _location(item.file, item.line_range)
        lines.extend(
            [
                f"### {item.rank}. {item.kind}",
                "",
                f"- file: {location}",
                f"- reason: {item.reason}",
                f"- score: {item.score:g}",
                f"- confidence: {item.confidence:g} ({_confidence_label(item.confidence)})",
                f"- tokens: {item.token_estimate}",
            ]
        )
        if item.extractor is not None:
            lines.append(f"- extractor: {item.extractor}")
        lines.append(f"- score_trace: {_format_mapping_inline(item.score_trace)}")
        language = _language_for_file(item.file)
        fence = _fence_for_text(item.text)
        lines.extend(["", f"{fence}{language}", item.text.rstrip("\n"), fence, ""])

    lines.extend(["## Omitted"])
    if not bundle.omitted:
        lines.append("None.")
    for omitted in bundle.omitted:
        score = "" if omitted.score is None else f" score={omitted.score:g}"
        name = omitted.name or "<unnamed>"
        lines.append(f"- {name}: {omitted.reason}{score}")

    lines.extend(["", "## Uncertainty"])
    if not bundle.uncertainty_notes:
        lines.append("None.")
    for note in bundle.uncertainty_notes:
        lines.append(f"- {_format_uncertainty_note(note)}")

    warning_lines = _warning_lines(bundle.index_health)
    lines.extend(["", "## Warnings"])
    if not warning_lines:
        lines.append("None.")
    else:
        lines.extend(warning_lines)

    lines.extend(["", "## Trace"])
    if not bundle.trace:
        lines.append("None.")
    for trace_item in bundle.trace:
        lines.append(f"- {_format_mapping_inline(trace_item)}")

    return "\n".join(lines).rstrip() + "\n"


def format_json(bundle: ContextBundle) -> str:
    """Render a context bundle as stable structured JSON."""
    return dumps(bundle.to_dict(), indent=2, sort_keys=True) + "\n"


def format_text(bundle: ContextBundle) -> str:
    """Render a context bundle as deterministic plain text."""
    lines: list[str] = ["codectx context bundle", "", "Query"]
    lines.extend(_mapping_lines(bundle.query))
    lines.extend(["", "Anchor"])
    lines.extend(_mapping_lines(bundle.anchor))
    lines.extend(["", "Index Health"])
    lines.extend(_mapping_lines(bundle.index_health))
    lines.extend(["", "Context Items"])
    if not bundle.items:
        lines.append("No context items selected.")
    for item in bundle.items:
        lines.extend(
            [
                f"{item.rank}. {item.kind}",
                f"file: {_location(item.file, item.line_range)}",
                f"reason: {item.reason}",
                f"score: {item.score:g}",
                f"confidence: {item.confidence:g} ({_confidence_label(item.confidence)})",
                f"tokens: {item.token_estimate}",
            ]
        )
        if item.extractor is not None:
            lines.append(f"extractor: {item.extractor}")
        lines.append(f"score_trace: {_format_mapping_inline(item.score_trace)}")
        lines.extend(["snippet:", item.text.rstrip("\n"), ""])

    lines.extend(["Omitted"])
    if not bundle.omitted:
        lines.append("None.")
    for omitted in bundle.omitted:
        score = "" if omitted.score is None else f" score={omitted.score:g}"
        name = omitted.name or "<unnamed>"
        lines.append(f"- {name}: {omitted.reason}{score}")

    lines.extend(["", "Uncertainty"])
    if not bundle.uncertainty_notes:
        lines.append("None.")
    for note in bundle.uncertainty_notes:
        lines.append(f"- {_format_uncertainty_note(note)}")

    warning_lines = _warning_lines(bundle.index_health)
    lines.extend(["", "Warnings"])
    if not warning_lines:
        lines.append("None.")
    else:
        lines.extend(warning_lines)

    lines.extend(["", "Trace"])
    if not bundle.trace:
        lines.append("None.")
    for trace_item in bundle.trace:
        lines.append(f"- {_format_mapping_inline(trace_item)}")

    return "\n".join(lines).rstrip() + "\n"


def _mapping_lines(values: dict[str, object]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {key}: {_format_value(value)}" for key, value in sorted(values.items())]


def _format_mapping_inline(values: Mapping[str, object]) -> str:
    if not values:
        return "none"
    return ", ".join(
        f"{key}={_format_value(value)}" for key, value in sorted(values.items())
    )


def _format_value(value: object) -> str:
    if value is None:
        return "<none>"
    return str(value)


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.9:
        return "resolved/high"
    if confidence >= 0.6:
        return "strong heuristic"
    if confidence >= 0.3:
        return "weak heuristic"
    return "low confidence"


def _format_uncertainty_note(note: str) -> str:
    if note.startswith("Unresolved "):
        return f"unresolved relationship: {note}"
    return note


def _warning_lines(index_health: dict[str, object]) -> list[str]:
    diagnostics = _int_value(index_health.get("diagnostics"))
    if diagnostics <= 0:
        return []
    return [f"- parser diagnostics recorded: {diagnostics}"]


def _int_value(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _location(file_path: str | None, line_range: tuple[int, int] | None) -> str:
    if file_path is None:
        return "<unknown>"
    if line_range is None:
        return file_path
    start_line, end_line = line_range
    if start_line == end_line:
        return f"{file_path}:{start_line}"
    return f"{file_path}:{start_line}-{end_line}"


def _language_for_file(file_path: str | None) -> str:
    if file_path is None:
        return ""
    suffix = file_path.rsplit(".", 1)[-1].lower()
    return {
        "cc": "cpp",
        "cpp": "cpp",
        "cxx": "cpp",
        "h": "cpp",
        "hpp": "cpp",
        "java": "java",
    }.get(suffix, "")


def _fence_for_text(text: str) -> str:
    longest = 0
    current = 0
    for char in text:
        if char == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return "`" * max(3, longest + 1)
