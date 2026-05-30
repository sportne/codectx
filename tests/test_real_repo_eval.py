from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def test_load_manifest_reads_default_targets() -> None:
    module = _load_module()

    targets = module.load_manifest()

    assert [target.id for target in targets] == ["mundane-java-di", "cpp-helper-libs"]
    assert targets[0].contexts
    assert targets[1].contexts[-1].expected_usefulness == "weak"
    assert targets[1].contexts[-1].quality_score == 2.1


def test_load_manifest_rejects_invalid_context_budget(tmp_path: Path) -> None:
    module = _load_module()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": [
                    {
                        "id": "repo",
                        "language": "java",
                        "path": "/missing",
                        "expected_status": "example",
                        "contexts": [
                            {
                                "id": "case",
                                "symbol": "Symbol",
                                "goal": "explain",
                                "budget": 0,
                                "expected_usefulness": "useful",
                                "quality_score": 4.0,
                                "notes": "invalid",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    try:
        module.load_manifest(manifest)
    except ValueError as exc:
        assert "budget" in str(exc)
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
                "targets": [
                    {
                        "id": "missing",
                        "language": "java",
                        "path": str(tmp_path / "missing"),
                        "expected_status": "missing",
                        "contexts": [
                            {
                                "id": "case",
                                "symbol": "Symbol",
                                "goal": "explain",
                                "budget": 1000,
                                "expected_usefulness": "unknown",
                                "quality_score": 3.0,
                                "notes": "missing repo",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(module.ENABLE_ENV, "1")

    result = module.main(["--manifest", str(manifest), "--output-dir", str(tmp_path)])

    assert result == 0
    assert "required real repositories are missing" in capsys.readouterr().out


def _load_module() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "real_repo_eval.py"
    spec = importlib.util.spec_from_file_location("real_repo_eval", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
