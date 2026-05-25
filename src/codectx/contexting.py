"""CLI-facing context bundle orchestration services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SUPPORTED_CONTEXT_FORMATS = {"json", "markdown", "text"}
SUPPORTED_CONTEXT_GOALS = {
    "call-neighborhood",
    "dependencies",
    "explain",
    "failure-modes",
}


@dataclass(frozen=True)
class ContextingError:
    """Actionable context generation error suitable for CLI display."""

    message: str


@dataclass(frozen=True)
class ContextResult:
    """Rendered context command response."""

    rendered_text: str
    output_path: Path | None = None


def build_context(
    repo: str | Path,
    *,
    db_path: str | Path | None = None,
    symbol: str | None = None,
    file_path: str | Path | None = None,
    line: int | None = None,
    goal: str = "explain",
    budget: int = 8000,
    output_format: str = "markdown",
    output_path: str | Path | None = None,
) -> ContextResult | ContextingError:
    """Validate context command inputs and return the current placeholder response."""
    error = _validate_request(
        goal=goal,
        budget=budget,
        output_format=output_format,
        symbol=symbol,
        file_path=file_path,
        line=line,
        output_path=output_path,
    )
    if error is not None:
        return error

    resolved_output_path = _resolve_output_path(output_path)
    return ContextResult(
        rendered_text=_placeholder_message("context"),
        output_path=resolved_output_path,
    )


def _validate_request(
    *,
    goal: str,
    budget: int,
    output_format: str,
    symbol: str | None,
    file_path: str | Path | None,
    line: int | None,
    output_path: str | Path | None,
) -> ContextingError | None:
    if goal not in SUPPORTED_CONTEXT_GOALS:
        return ContextingError(f"Unsupported context goal: {goal}")
    if output_format not in SUPPORTED_CONTEXT_FORMATS:
        return ContextingError(f"Unsupported context format: {output_format}")
    if budget <= 0:
        return ContextingError("Context budget must be greater than 0.")
    if symbol is None and file_path is None:
        return ContextingError("Provide either --symbol or --file for context.")
    if symbol is not None and file_path is not None:
        return ContextingError("Provide only one context anchor: --symbol or --file.")
    if symbol is not None and line is not None:
        return ContextingError("--line can only be used with --file.")
    if file_path is not None and line is None:
        return ContextingError("--line is required when using --file.")
    if line is not None and line < 1:
        return ContextingError("Line number must be 1 or greater.")
    if output_path is not None:
        parent = Path(output_path).expanduser().resolve().parent
        if not parent.exists():
            return ContextingError(f"Output directory does not exist: {parent}")
    return None


def _resolve_output_path(output_path: str | Path | None) -> Path | None:
    if output_path is None:
        return None
    return Path(output_path).expanduser().resolve()


def _placeholder_message(command: str) -> str:
    return (
        f"codectx command '{command}' is defined but not implemented yet.\n"
        "See docs/04-task-decomposition.md for the ordered MVP task plan."
    )
