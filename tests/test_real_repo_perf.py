from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def test_load_manifest_reads_default_targets() -> None:
    module = _load_module()

    targets = module.load_manifest()

    assert [target.id for target in targets] == [
        "mundane-java-di",
        "cpp-helper-libs",
        "commons-math",
    ]
    assert targets[0].thresholds["index_seconds"] == 30
    assert targets[1].exclude_patterns == ("third_party/**",)
    assert targets[2].thresholds["changed_index_seconds"] == 80


def test_load_manifest_rejects_invalid_threshold(tmp_path: Path) -> None:
    module = _load_module()
    thresholds = _thresholds()
    thresholds["index_seconds"] = 0
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": [_manifest_target(thresholds=thresholds)],
            }
        ),
        encoding="utf-8",
    )

    try:
        module.load_manifest(manifest)
    except ValueError as exc:
        assert "thresholds.index_seconds" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected ValueError")


def test_load_manifest_rejects_missing_threshold(tmp_path: Path) -> None:
    module = _load_module()
    thresholds = _thresholds()
    del thresholds["context_seconds"]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": [_manifest_target(thresholds=thresholds)],
            }
        ),
        encoding="utf-8",
    )

    try:
        module.load_manifest(manifest)
    except ValueError as exc:
        assert "context_seconds" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected ValueError")


def test_main_skips_when_env_var_is_disabled(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    module = _load_module()
    monkeypatch.delenv(module.ENABLE_ENV, raising=False)

    result = module.main([])

    assert result == 0
    assert f"set {module.ENABLE_ENV}=1" in capsys.readouterr().out


def test_main_skips_when_enabled_repos_are_missing(
    tmp_path: Path, monkeypatch, capsys
) -> None:  # type: ignore[no-untyped-def]
    module = _load_module()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": [_manifest_target(id="missing", path=tmp_path / "missing")],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(module.ENABLE_ENV, "1")

    result = module.main(["--manifest", str(manifest), "--output-dir", str(tmp_path)])

    assert result == 0
    assert "wrote real-repo performance results" in capsys.readouterr().out
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary[0]["status"] == "skipped"
    assert summary[0]["message"] == "required real repository is missing"


def test_threshold_failures_reports_only_exceeded_metrics() -> None:
    module = _load_module()

    failures = module._threshold_failures(
        [
            {
                "id": "repo",
                "status": "ok",
                "integrity": "ok",
                "queries": {
                    "symbol_query": "ok",
                    "search": "ok",
                    "context": "ok",
                },
                "metrics": {"index_seconds": 2.0, "db_source_size_ratio": 3.0},
                "thresholds": {"index_seconds": 1.0, "db_source_size_ratio": 5.0},
            }
        ]
    )

    assert failures == ["repo: index_seconds=2.0 > 1.0"]


def test_threshold_failures_report_failed_gate_statuses() -> None:
    module = _load_module()

    failures = module._threshold_failures(
        [
            {
                "id": "repo",
                "status": "ok",
                "integrity": "failed",
                "queries": {
                    "symbol_query": "ok",
                    "search": "failed",
                    "context": "ok",
                },
                "metrics": {"index_seconds": 1.0},
                "thresholds": {"index_seconds": 2.0},
            }
        ]
    )

    assert failures == ["repo: integrity=failed", "repo: search=failed"]


def test_indexed_source_size_uses_scan_filters(tmp_path: Path) -> None:
    module = _load_module()
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "third_party").mkdir()
    source = "class App {}\n"
    ignored_source = "class Vendored {}\n"
    (repo / "src" / "App.java").write_text(source, encoding="utf-8")
    (repo / "third_party" / "Vendored.java").write_text(
        ignored_source, encoding="utf-8"
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": [
                    _manifest_target(
                        path=repo,
                        exclude_patterns=["third_party/**"],
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    target = module.load_manifest(manifest)[0]

    assert module._indexed_source_size(target) == len(source.encode("utf-8"))


def _load_module() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "real_repo_perf.py"
    spec = importlib.util.spec_from_file_location("real_repo_perf", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest_target(
    *,
    id: str = "repo",
    path: str | Path = "/missing",
    thresholds: dict[str, float] | None = None,
    exclude_patterns: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": id,
        "language": "java",
        "path": str(path),
        "symbol_query": "Symbol",
        "search_query": "query",
        "context_symbol": "Symbol",
        "context_goal": "explain",
        "context_budget": 1000,
        "thresholds": thresholds if thresholds is not None else _thresholds(),
        "exclude_patterns": exclude_patterns or [],
    }


def _thresholds() -> dict[str, float]:
    return {
        "index_seconds": 10,
        "unchanged_index_seconds": 10,
        "changed_index_seconds": 10,
        "integrity_seconds": 10,
        "symbol_query_seconds": 10,
        "search_seconds": 10,
        "context_seconds": 10,
        "db_source_size_ratio": 10,
    }
