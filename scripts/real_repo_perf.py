"""Run optional real-repository performance and storage gates."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from codectx.contexting import ContextResult, build_context
from codectx.indexing import HealthResult, IndexResult, read_health, run_index
from codectx.querying import SearchResult, SymbolSearchResult, search, search_symbols
from codectx.scanner.repo import ScanOptions, scan_repository

ENABLE_ENV = "CODECTX_REAL_REPO_PERF"
ENFORCE_ENV = "CODECTX_REAL_REPO_PERF_ENFORCE"
DEFAULT_MANIFEST = Path(__file__).with_name("real_repo_perf_targets.json")
REQUIRED_THRESHOLDS = frozenset(
    {
        "index_seconds",
        "unchanged_index_seconds",
        "changed_index_seconds",
        "integrity_seconds",
        "symbol_query_seconds",
        "search_seconds",
        "context_seconds",
        "db_source_size_ratio",
    }
)

T = TypeVar("T")


@dataclass(frozen=True)
class PerfTarget:
    """One real repository performance target."""

    id: str
    language: str
    path: Path
    symbol_query: str
    search_query: str
    context_symbol: str
    context_goal: str
    context_budget: int
    thresholds: dict[str, float]
    include_patterns: tuple[str, ...]
    exclude_patterns: tuple[str, ...]
    force_include_patterns: tuple[str, ...]
    use_ignore_files: bool


def load_manifest(path: Path = DEFAULT_MANIFEST) -> tuple[PerfTarget, ...]:
    """Load and validate the performance manifest."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        raise ValueError("manifest version must be 1")
    targets = raw.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("manifest must contain at least one target")
    return tuple(_target(value) for value in targets)


def main(argv: list[str] | None = None) -> int:
    """Run the optional real-repo performance gate."""
    parser = argparse.ArgumentParser(
        description=(
            "Run optional real-repository performance and storage gates. "
            f"Set {ENABLE_ENV}=1 to enable."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args(argv)

    if os.environ.get(ENABLE_ENV) != "1":
        print(f"skipped: set {ENABLE_ENV}=1 to run real-repo performance gates")
        return 0

    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else Path(tempfile.gettempdir()) / f"codectx-real-repo-perf-{_timestamp()}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    targets = load_manifest(args.manifest)
    summary = _run(targets, output_dir)
    _write_summary(output_dir / "summary.md", summary)
    _write_summary_json(output_dir / "summary.json", summary)
    failures = _threshold_failures(summary)
    print(f"wrote real-repo performance results to {output_dir}")
    if failures:
        print("threshold failures:")
        for failure in failures:
            print(f"- {failure}")
    enforce = args.enforce or os.environ.get(ENFORCE_ENV) == "1"
    return 1 if enforce and failures else 0


def _run(targets: tuple[PerfTarget, ...], output_dir: Path) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for target in targets:
        if not target.path.is_dir():
            summary.append(
                {
                    "id": target.id,
                    "path": str(target.path),
                    "status": "skipped",
                    "message": "required real repository is missing",
                }
            )
            continue
        working_repo = _copy_target_repo(target, output_dir)
        db_path = output_dir / "db" / f"{target.id}.sqlite"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        working_target = _target_with_path(target, working_repo)
        source_bytes = _indexed_source_size(working_target)

        current_target = working_target
        current_db_path = db_path
        index_result, index_seconds = _timed(
            lambda current_target=current_target, current_db_path=current_db_path: (
                run_index(
                    current_target.path,
                    db_path=current_db_path,
                    rebuild=True,
                    include_patterns=current_target.include_patterns,
                    exclude_patterns=current_target.exclude_patterns,
                    force_include_patterns=current_target.force_include_patterns,
                    use_ignore_files=current_target.use_ignore_files,
                )
            )
        )
        if not isinstance(index_result, IndexResult):
            summary.append(
                {
                    "id": target.id,
                    "path": str(working_target.path),
                    "status": "index_failed",
                    "message": index_result.message,
                }
            )
            continue
        unchanged_result, unchanged_seconds = _timed(
            lambda current_target=current_target, current_db_path=current_db_path: (
                run_index(
                    current_target.path,
                    db_path=current_db_path,
                    include_patterns=current_target.include_patterns,
                    exclude_patterns=current_target.exclude_patterns,
                    force_include_patterns=current_target.force_include_patterns,
                    use_ignore_files=current_target.use_ignore_files,
                )
            )
        )
        _touch_first_indexed_source(working_target)
        changed_result, changed_seconds = _timed(
            lambda current_target=current_target, current_db_path=current_db_path: (
                run_index(
                    current_target.path,
                    db_path=current_db_path,
                    include_patterns=current_target.include_patterns,
                    exclude_patterns=current_target.exclude_patterns,
                    force_include_patterns=current_target.force_include_patterns,
                    use_ignore_files=current_target.use_ignore_files,
                )
            )
        )

        health_result, integrity_seconds = _timed(
            lambda current_target=current_target, current_db_path=current_db_path: (
                read_health(
                    current_target.path,
                    db_path=current_db_path,
                    include_integrity=True,
                )
            )
        )
        symbol_result, symbol_seconds = _timed(
            lambda current_target=current_target, current_db_path=current_db_path: (
                search_symbols(
                    current_target.path,
                    current_target.symbol_query,
                    db_path=current_db_path,
                )
            )
        )
        search_result, search_seconds = _timed(
            lambda current_target=current_target, current_db_path=current_db_path: (
                search(
                    current_target.path,
                    current_target.search_query,
                    db_path=current_db_path,
                )
            )
        )
        context_result, context_seconds = _timed(
            lambda current_target=current_target, current_db_path=current_db_path: (
                build_context(
                    current_target.path,
                    db_path=current_db_path,
                    symbol=current_target.context_symbol,
                    goal=current_target.context_goal,
                    budget=current_target.context_budget,
                    output_format="json",
                )
            )
        )
        db_bytes = db_path.stat().st_size
        metrics = {
            "index_seconds": round(index_seconds, 4),
            "unchanged_index_seconds": round(unchanged_seconds, 4),
            "changed_index_seconds": round(changed_seconds, 4),
            "integrity_seconds": round(integrity_seconds, 4),
            "symbol_query_seconds": round(symbol_seconds, 4),
            "search_seconds": round(search_seconds, 4),
            "context_seconds": round(context_seconds, 4),
            "source_bytes": float(source_bytes),
            "db_bytes": float(db_bytes),
            "db_source_size_ratio": round(db_bytes / max(source_bytes, 1), 4),
        }
        summary.append(
            {
                "id": target.id,
                "language": target.language,
                "path": str(target.path),
                "working_path": str(working_target.path),
                "status": "ok",
                "integrity": health_result.integrity
                if isinstance(health_result, HealthResult)
                else "failed",
                "stats": dict(index_result.stats),
                "metrics": metrics,
                "source_size_basis": "indexed_supported_sources",
                "thresholds": target.thresholds,
                "queries": {
                    "unchanged_index": _result_status(unchanged_result, IndexResult),
                    "changed_index": _result_status(changed_result, IndexResult),
                    "symbol_query": _result_status(symbol_result, SymbolSearchResult),
                    "search": _result_status(search_result, SearchResult),
                    "context": _result_status(context_result, ContextResult),
                },
            }
        )
    return summary


def _threshold_failures(summary: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    for target in summary:
        if target.get("status") == "skipped":
            continue
        if target.get("status") != "ok":
            failures.append(
                f"{target.get('id', '<unknown>')}: status={target.get('status')}"
            )
            continue
        if target.get("integrity") != "ok":
            failures.append(
                f"{target.get('id', '<unknown>')}: integrity={target.get('integrity')}"
            )
        queries = target.get("queries", {})
        if not isinstance(queries, dict):
            failures.append(f"{target.get('id', '<unknown>')}: missing query statuses")
        else:
            for query_name, status in sorted(queries.items()):
                if status != "ok":
                    failures.append(
                        f"{target.get('id', '<unknown>')}: {query_name}={status}"
                    )
        metrics = target.get("metrics", {})
        thresholds = target.get("thresholds", {})
        if not isinstance(metrics, dict) or not isinstance(thresholds, dict):
            failures.append(f"{target.get('id', '<unknown>')}: missing metrics")
            continue
        for key, threshold in thresholds.items():
            value = metrics.get(key)
            if isinstance(value, int | float) and value > float(threshold):
                failures.append(f"{target['id']}: {key}={value} > {threshold}")
    return failures


def _write_summary(path: Path, summary: list[dict[str, Any]]) -> None:
    lines = ["# codectx real-repo performance", ""]
    for target in summary:
        lines.extend([f"## {target['id']}", "", f"- status: {target['status']}"])
        if target["status"] != "ok":
            lines.extend([f"- message: {target.get('message', '<none>')}", ""])
            continue
        lines.extend(
            [
                f"- integrity: {target['integrity']}",
                f"- source size basis: {target['source_size_basis']}",
                "- stats: "
                + ", ".join(
                    f"{key}={value}" for key, value in sorted(target["stats"].items())
                ),
                "",
                "| Metric | Value | Threshold |",
                "| --- | ---: | ---: |",
            ]
        )
        for key, value in sorted(target["metrics"].items()):
            lines.append(f"| {key} | {value} | {target['thresholds'].get(key, '')} |")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_summary_json(path: Path, summary: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _target(value: object) -> PerfTarget:
    if not isinstance(value, dict):
        raise ValueError("target must be an object")
    thresholds = value.get("thresholds")
    if not isinstance(thresholds, dict) or not thresholds:
        raise ValueError("thresholds must be a non-empty object")
    threshold_keys = set(thresholds)
    missing_thresholds = REQUIRED_THRESHOLDS - threshold_keys
    unknown_thresholds = threshold_keys - REQUIRED_THRESHOLDS
    if missing_thresholds:
        names = ", ".join(sorted(missing_thresholds))
        raise ValueError(f"thresholds missing required metric(s): {names}")
    if unknown_thresholds:
        names = ", ".join(sorted(unknown_thresholds))
        raise ValueError(f"thresholds contains unknown metric(s): {names}")
    return PerfTarget(
        id=_required_str(value, "id"),
        language=_required_str(value, "language"),
        path=Path(_required_str(value, "path")),
        symbol_query=_required_str(value, "symbol_query"),
        search_query=_required_str(value, "search_query"),
        context_symbol=_required_str(value, "context_symbol"),
        context_goal=_required_str(value, "context_goal"),
        context_budget=_positive_int(value, "context_budget"),
        thresholds={
            key: _number(raw, f"thresholds.{key}") for key, raw in thresholds.items()
        },
        include_patterns=_optional_str_tuple(value, "include_patterns"),
        exclude_patterns=_optional_str_tuple(value, "exclude_patterns"),
        force_include_patterns=_optional_str_tuple(value, "force_include_patterns"),
        use_ignore_files=_optional_bool(value, "use_ignore_files", default=True),
    )


def _target_with_path(target: PerfTarget, path: Path) -> PerfTarget:
    return PerfTarget(
        id=target.id,
        language=target.language,
        path=path,
        symbol_query=target.symbol_query,
        search_query=target.search_query,
        context_symbol=target.context_symbol,
        context_goal=target.context_goal,
        context_budget=target.context_budget,
        thresholds=target.thresholds,
        include_patterns=target.include_patterns,
        exclude_patterns=target.exclude_patterns,
        force_include_patterns=target.force_include_patterns,
        use_ignore_files=target.use_ignore_files,
    )


def _timed(operation: Callable[[], T]) -> tuple[T, float]:
    started = time.perf_counter()
    result = operation()
    return result, time.perf_counter() - started


def _result_status(result: object, expected_type: type[object]) -> str:
    return "ok" if isinstance(result, expected_type) else "failed"


def _indexed_source_size(target: PerfTarget) -> int:
    return sum(
        record.size_bytes
        for record in scan_repository(target.path, options=_scan_options(target))
    )


def _copy_target_repo(target: PerfTarget, output_dir: Path) -> Path:
    destination = output_dir / "repos" / target.id
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(
        target.path,
        destination,
        ignore=shutil.ignore_patterns(".git", ".codectx", "__pycache__"),
    )
    return destination


def _touch_first_indexed_source(target: PerfTarget) -> None:
    records = scan_repository(target.path, options=_scan_options(target))
    if not records:
        return
    path = target.path / records[0].path
    suffix = (
        "\n// codectx incremental performance change\n"
        if records[0].language in {"java", "cpp"}
        else "\n"
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(suffix)


def _scan_options(target: PerfTarget) -> ScanOptions:
    return ScanOptions(
        include_patterns=target.include_patterns,
        exclude_patterns=target.exclude_patterns,
        force_include_patterns=target.force_include_patterns,
        use_ignore_files=target.use_ignore_files,
    )


def _required_str(value: dict[str, object], key: str) -> str:
    found = value.get(key)
    if not isinstance(found, str) or not found:
        raise ValueError(f"{key} must be a non-empty string")
    return found


def _positive_int(value: dict[str, object], key: str) -> int:
    found = value.get(key)
    if not isinstance(found, int) or found <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return found


def _number(value: object, label: str) -> float:
    if not isinstance(value, int | float) or value <= 0:
        raise ValueError(f"{label} must be a positive number")
    return float(value)


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


def _timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


if __name__ == "__main__":
    raise SystemExit(main())
