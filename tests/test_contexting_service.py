from __future__ import annotations

from pathlib import Path

from codectx.contexting import ContextingError, ContextResult, build_context


def test_build_context_returns_placeholder_result(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = build_context(repo, symbol="PaymentService", goal="explain")

    assert isinstance(result, ContextResult)
    assert "codectx command 'context' is defined but not implemented yet." in (
        result.rendered_text
    )
    assert "docs/04-task-decomposition.md" in result.rendered_text
    assert result.output_path is None


def test_build_context_validates_goal_format_and_budget(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    bad_goal = build_context(repo, symbol="PaymentService", goal="unknown")
    bad_format = build_context(repo, symbol="PaymentService", output_format="unknown")
    bad_budget = build_context(repo, symbol="PaymentService", budget=0)

    assert isinstance(bad_goal, ContextingError)
    assert "Unsupported context goal" in bad_goal.message
    assert isinstance(bad_format, ContextingError)
    assert "Unsupported context format" in bad_format.message
    assert isinstance(bad_budget, ContextingError)
    assert "budget" in bad_budget.message


def test_build_context_validates_anchor_shape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    missing_anchor = build_context(repo)
    duplicate_anchor = build_context(
        repo, symbol="PaymentService", file_path="src/Foo.java"
    )

    assert isinstance(missing_anchor, ContextingError)
    assert "Provide either --symbol or --file" in missing_anchor.message
    assert isinstance(duplicate_anchor, ContextingError)
    assert "Provide only one context anchor" in duplicate_anchor.message


def test_build_context_validates_file_line_anchor_shape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    missing_line = build_context(repo, file_path="src/Foo.java")
    bad_line = build_context(repo, file_path="src/Foo.java", line=0)
    symbol_with_line = build_context(repo, symbol="PaymentService", line=10)

    assert isinstance(missing_line, ContextingError)
    assert "--line is required" in missing_line.message
    assert isinstance(bad_line, ContextingError)
    assert "Line number must be 1 or greater" in bad_line.message
    assert isinstance(symbol_with_line, ContextingError)
    assert "--line can only be used with --file" in symbol_with_line.message


def test_build_context_validates_and_resolves_output_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    output_path = tmp_path / "context.md"

    result = build_context(repo, symbol="PaymentService", output_path=output_path)
    missing_parent = build_context(
        repo,
        symbol="PaymentService",
        output_path=tmp_path / "missing" / "context.md",
    )

    assert isinstance(result, ContextResult)
    assert result.output_path == output_path.resolve()
    assert isinstance(missing_parent, ContextingError)
    assert "Output directory does not exist" in missing_parent.message
