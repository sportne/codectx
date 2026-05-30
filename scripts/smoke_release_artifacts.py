"""Smoke-test built source and wheel distributions in isolated virtualenvs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

STABLE_BUNDLE_FIELDS = {
    "anchor",
    "index_health",
    "items",
    "omitted",
    "query",
    "trace",
    "uncertainty_notes",
}


def main(argv: list[str] | None = None) -> int:
    """Run installed-artifact smoke checks for built release packages."""
    args = _parse_args(argv)
    repo_root = args.repo_root.resolve()
    dist_dir = args.dist_dir.resolve()
    version = _package_version(repo_root / "pyproject.toml")
    artifacts = (
        dist_dir / f"codectx-{version}.tar.gz",
        dist_dir / f"codectx-{version}-py3-none-any.whl",
    )
    missing = [artifact for artifact in artifacts if not artifact.is_file()]
    if missing:
        names = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"missing release artifact(s): {names}")

    fixture = repo_root / "tests" / "fixtures" / "java_basic"
    if not fixture.is_dir():
        raise FileNotFoundError(f"missing smoke fixture: {fixture}")

    with tempfile.TemporaryDirectory(prefix="codectx-package-smoke-") as tmp:
        tmp_path = Path(tmp)
        for artifact in artifacts:
            _smoke_artifact(
                artifact=artifact,
                fixture=fixture,
                expected_version=version,
                workspace=tmp_path / artifact.name.replace(".", "-"),
            )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=Path("dist"),
        help="Directory containing built release artifacts.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root containing pyproject.toml and test fixtures.",
    )
    return parser.parse_args(argv)


def _package_version(pyproject_path: Path) -> str:
    with pyproject_path.open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    if not isinstance(version, str):
        raise ValueError("project.version must be a string")
    return version


def _smoke_artifact(
    *,
    artifact: Path,
    fixture: Path,
    expected_version: str,
    workspace: Path,
) -> None:
    workspace.mkdir(parents=True)
    venv_path = workspace / "venv"
    _run([sys.executable, "-m", "venv", str(venv_path)], cwd=workspace)
    python = _venv_executable(venv_path, "python")
    codectx = _venv_executable(venv_path, "codectx")
    _run([str(python), "-m", "pip", "install", "--upgrade", "pip"], cwd=workspace)
    _run([str(python), "-m", "pip", "install", str(artifact)], cwd=workspace)

    version_result = _run(
        [str(codectx), "--version"], cwd=workspace, capture_output=True
    )
    expected_output = f"codectx {expected_version}"
    if version_result.stdout.strip() != expected_output:
        raise AssertionError(
            f"{artifact.name} reported {version_result.stdout.strip()!r}; "
            f"expected {expected_output!r}"
        )

    db_path = workspace / "graph.sqlite"
    context_path = workspace / "context.json"
    _run(
        [
            str(codectx),
            "index",
            str(fixture),
            "--db",
            str(db_path),
            "--rebuild",
        ],
        cwd=workspace,
    )
    _run(
        [
            str(codectx),
            "health",
            "--repo",
            str(fixture),
            "--db",
            str(db_path),
            "--integrity",
        ],
        cwd=workspace,
    )
    context_result = _run(
        [
            str(codectx),
            "context",
            "--repo",
            str(fixture),
            "--db",
            str(db_path),
            "--symbol",
            "PaymentService.authorize",
            "--goal",
            "explain",
            "--budget",
            "1000",
            "--format",
            "json",
        ],
        cwd=workspace,
        capture_output=True,
    )
    context_path.write_text(context_result.stdout, encoding="utf-8")
    _assert_stable_bundle_fields(context_path)
    print(f"smoked installed artifact: {artifact.name}")


def _assert_stable_bundle_fields(path: Path) -> None:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(bundle, dict):
        raise AssertionError(f"context bundle is not a JSON object: {path}")
    missing = STABLE_BUNDLE_FIELDS - set(bundle)
    if missing:
        names = ", ".join(sorted(missing))
        raise AssertionError(f"context bundle is missing stable field(s): {names}")


def _venv_executable(venv_path: Path, name: str) -> Path:
    if sys.platform == "win32":
        return venv_path / "Scripts" / f"{name}.exe"
    return venv_path / "bin" / name


def _run(
    command: list[str],
    *,
    cwd: Path,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=capture_output,
    )


if __name__ == "__main__":
    raise SystemExit(main())
