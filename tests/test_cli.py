from __future__ import annotations

import pytest

from codectx.cli import build_parser, main


def test_parser_accepts_all_initial_commands() -> None:
    parser = build_parser()

    assert parser.parse_args(["index", "."]).command == "index"
    assert parser.parse_args(["health"]).command == "health"
    assert parser.parse_args(["search", "PaymentService"]).command == "search"
    assert parser.parse_args(["symbols", "PaymentService"]).command == "symbols"
    assert (
        parser.parse_args(["context", "--symbol", "PaymentService.authorize"]).command
        == "context"
    )
    assert (
        parser.parse_args(["neighborhood", "--symbol", "PaymentService"]).command
        == "neighborhood"
    )
    assert parser.parse_args(["inspect-node", "123"]).command == "inspect-node"
    assert parser.parse_args(["inspect-edge", "456"]).command == "inspect-edge"


def test_parser_version_exits_with_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])

    assert exc_info.value.code == 0
    assert "codectx 0.0.1" in capsys.readouterr().out


def test_main_reports_defined_but_unimplemented_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["search", "PaymentService"]) == 0

    output = capsys.readouterr().out
    assert "codectx command 'search' is defined but not implemented yet." in output
    assert "docs/04-task-decomposition.md" in output
