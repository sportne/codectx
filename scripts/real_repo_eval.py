"""Run optional real-repository context quality evaluation."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codectx.contexting import ContextResult, build_context
from codectx.indexing import HealthResult, IndexResult, read_health, run_index

ENABLE_ENV = "CODECTX_REAL_REPO_EVAL"
DEFAULT_MANIFEST = Path(__file__).with_name("real_repo_eval_targets.json")


@dataclass(frozen=True)
class ContextTarget:
    """One context bundle to generate for a real repository."""

    id: str
    symbol: str
    goal: str
    budget: int
    expected_usefulness: str
    quality_score: float
    notes: str


@dataclass(frozen=True)
class RepoTarget:
    """One real repository to index and evaluate."""

    id: str
    language: str
    path: Path
    expected_status: str
    include_patterns: tuple[str, ...]
    exclude_patterns: tuple[str, ...]
    force_include_patterns: tuple[str, ...]
    use_ignore_files: bool
    contexts: tuple[ContextTarget, ...]


def load_manifest(path: Path = DEFAULT_MANIFEST) -> tuple[RepoTarget, ...]:
    """Load and validate a real-repo evaluation manifest."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        raise ValueError("manifest version must be 1")
    targets = raw.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("manifest must contain at least one target")
    return tuple(_repo_target(value) for value in targets)


def main(argv: list[str] | None = None) -> int:
    """Run the optional real-repo evaluation."""
    parser = argparse.ArgumentParser(
        description=(
            "Run optional real-repository context quality evaluation. "
            f"Set {ENABLE_ENV}=1 to enable."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    if os.environ.get(ENABLE_ENV) != "1":
        print(f"skipped: set {ENABLE_ENV}=1 to run real-repo evaluation")
        return 0

    targets = load_manifest(args.manifest)
    missing = [target for target in targets if not target.path.is_dir()]
    if missing:
        missing_paths = ", ".join(f"{target.id}={target.path}" for target in missing)
        print(f"skipped: required real repositories are missing: {missing_paths}")
        return 0

    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else Path(tempfile.gettempdir()) / f"codectx-real-repo-eval-{_timestamp()}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = _run_evaluation(targets, output_dir)
    _write_summary(output_dir / "summary.md", summary)
    _write_summary_json(output_dir / "summary.json", summary)
    print(f"wrote real-repo evaluation results to {output_dir}")
    return 0


def _run_evaluation(
    targets: tuple[RepoTarget, ...], output_dir: Path
) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for target in targets:
        db_path = output_dir / "db" / f"{target.id}.sqlite"
        bundle_dir = output_dir / "bundles" / target.id
        db_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_dir.mkdir(parents=True, exist_ok=True)

        started = time.perf_counter()
        index_result = run_index(
            target.path,
            db_path=db_path,
            rebuild=True,
            include_patterns=target.include_patterns,
            exclude_patterns=target.exclude_patterns,
            force_include_patterns=target.force_include_patterns,
            use_ignore_files=target.use_ignore_files,
        )
        index_seconds = time.perf_counter() - started
        if not isinstance(index_result, IndexResult):
            summary.append(
                {
                    "id": target.id,
                    "path": str(target.path),
                    "status": "index_failed",
                    "message": index_result.message,
                }
            )
            continue

        health_result = read_health(
            target.path, db_path=db_path, include_integrity=True
        )
        target_summary: dict[str, Any] = {
            "id": target.id,
            "language": target.language,
            "path": str(target.path),
            "status": "ok",
            "expected_status": target.expected_status,
            "scan_filters": {
                "include_patterns": list(target.include_patterns),
                "exclude_patterns": list(target.exclude_patterns),
                "force_include_patterns": list(target.force_include_patterns),
                "use_ignore_files": target.use_ignore_files,
            },
            "index_seconds": round(index_seconds, 4),
            "stats": dict(index_result.stats),
            "integrity": (
                health_result.integrity
                if isinstance(health_result, HealthResult)
                else "failed"
            ),
            "contexts": [],
        }
        for context in target.contexts:
            context_result = build_context(
                target.path,
                db_path=db_path,
                symbol=context.symbol,
                goal=context.goal,
                budget=context.budget,
                output_format="markdown",
            )
            context_summary = {
                "id": context.id,
                "symbol": context.symbol,
                "goal": context.goal,
                "budget": context.budget,
                "expected_usefulness": context.expected_usefulness,
                "quality_score": context.quality_score,
                "notes": context.notes,
            }
            if isinstance(context_result, ContextResult):
                output_path = bundle_dir / f"{context.id}.md"
                output_path.write_text(context_result.rendered_text, encoding="utf-8")
                context_summary["status"] = "ok"
                context_summary["output"] = str(output_path)
            else:
                context_summary["status"] = "failed"
                context_summary["message"] = context_result.message
            target_summary["contexts"].append(context_summary)
        summary.append(target_summary)
    return summary


def _write_summary(path: Path, summary: list[dict[str, Any]]) -> None:
    lines = ["# codectx real-repo evaluation", ""]
    for target in summary:
        lines.extend(
            [
                f"## {target['id']}",
                "",
                f"- path: {target['path']}",
                f"- status: {target['status']}",
            ]
        )
        if target["status"] != "ok":
            lines.extend([f"- message: {target.get('message', '<none>')}", ""])
            continue
        lines.extend(
            [
                f"- expected_status: {target['expected_status']}",
                f"- scan_filters: {_format_scan_filters(target['scan_filters'])}",
                f"- index_seconds: {target['index_seconds']}",
                f"- integrity: {target['integrity']}",
                "- stats: "
                + ", ".join(
                    f"{key}={value}" for key, value in sorted(target["stats"].items())
                ),
                "",
                "| Context | Goal | Status | Expected usefulness | Quality score | Output |",
                "| --- | --- | --- | --- | ---: | --- |",
            ]
        )
        for context in target["contexts"]:
            lines.append(
                "| {id} | {goal} | {status} | {expected} | {quality_score:.1f} | {output} |".format(
                    id=context["id"],
                    goal=context["goal"],
                    status=context["status"],
                    expected=context["expected_usefulness"],
                    quality_score=context["quality_score"],
                    output=context.get("output", context.get("message", "")),
                )
            )
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_summary_json(path: Path, summary: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _repo_target(value: object) -> RepoTarget:
    if not isinstance(value, dict):
        raise ValueError("target must be an object")
    contexts = value.get("contexts")
    if not isinstance(contexts, list) or not contexts:
        raise ValueError(f"target {value.get('id', '<unknown>')} must have contexts")
    return RepoTarget(
        id=_required_str(value, "id"),
        language=_required_str(value, "language"),
        path=Path(_required_str(value, "path")),
        expected_status=_required_str(value, "expected_status"),
        include_patterns=_optional_str_tuple(value, "include_patterns"),
        exclude_patterns=_optional_str_tuple(value, "exclude_patterns"),
        force_include_patterns=_optional_str_tuple(value, "force_include_patterns"),
        use_ignore_files=_optional_bool(value, "use_ignore_files", default=True),
        contexts=tuple(_context_target(context) for context in contexts),
    )


def _context_target(value: object) -> ContextTarget:
    if not isinstance(value, dict):
        raise ValueError("context must be an object")
    budget = value.get("budget")
    if not isinstance(budget, int) or budget <= 0:
        raise ValueError("context budget must be a positive integer")
    quality_score = value.get("quality_score")
    if not isinstance(quality_score, int | float) or not 1 <= quality_score <= 5:
        raise ValueError("context quality_score must be a number from 1 to 5")
    return ContextTarget(
        id=_required_str(value, "id"),
        symbol=_required_str(value, "symbol"),
        goal=_required_str(value, "goal"),
        budget=budget,
        expected_usefulness=_required_str(value, "expected_usefulness"),
        quality_score=float(quality_score),
        notes=_required_str(value, "notes"),
    )


def _required_str(value: dict[str, object], key: str) -> str:
    found = value.get(key)
    if not isinstance(found, str) or not found:
        raise ValueError(f"{key} must be a non-empty string")
    return found


def _optional_str_tuple(value: dict[str, object], key: str) -> tuple[str, ...]:
    found = value.get(key, [])
    if not isinstance(found, list) or not all(
        isinstance(item, str) and item for item in found
    ):
        raise ValueError(f"{key} must be a list of non-empty strings")
    return tuple(found)


def _optional_bool(value: dict[str, object], key: str, *, default: bool) -> bool:
    found = value.get(key, default)
    if not isinstance(found, bool):
        raise ValueError(f"{key} must be a boolean")
    return found


def _format_scan_filters(scan_filters: object) -> str:
    if not isinstance(scan_filters, dict):
        return "<invalid>"
    values = []
    for key in (
        "include_patterns",
        "exclude_patterns",
        "force_include_patterns",
        "use_ignore_files",
    ):
        values.append(f"{key}={scan_filters.get(key)!r}")
    return ", ".join(values)


def _timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


if __name__ == "__main__":
    raise SystemExit(main())
