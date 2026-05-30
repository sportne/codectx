"""Validate release tags and emit GitHub Actions release metadata."""

from __future__ import annotations

import argparse
import ast
import json
import re
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

PRODUCTION_TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")
SMOKE_TAG_RE = re.compile(
    r"^release-smoke/v(?P<version>\d+\.\d+\.\d+)-smoke-(?P<stamp>\d{12})$"
)


@dataclass(frozen=True)
class ReleaseMetadata:
    """Validated release metadata shared by local tests and GitHub Actions."""

    release_tag: str
    package_version: str
    asset_version: str
    release_kind: str
    prerelease: bool
    title: str
    notes: str


def validate_release_tag(
    release_tag: str, *, package_version: str, module_version: str
) -> ReleaseMetadata:
    """Validate a production or smoke release tag against package versions."""
    production_match = PRODUCTION_TAG_RE.fullmatch(release_tag)
    if production_match is not None:
        release_version = production_match.group("version")
        _verify_version_match(
            release_tag, release_version, package_version, module_version
        )
        return ReleaseMetadata(
            release_tag=release_tag,
            package_version=release_version,
            asset_version=release_version,
            release_kind="production",
            prerelease=False,
            title=f"codectx {release_version}",
            notes=(
                f"Release {release_version}. The attached artifacts include a "
                "source distribution, wheel, and runnable PEX for supported "
                "Linux and Windows CPython targets."
            ),
        )

    smoke_match = SMOKE_TAG_RE.fullmatch(release_tag)
    if smoke_match is not None:
        base_version = smoke_match.group("version")
        stamp = smoke_match.group("stamp")
        _validate_stamp(stamp)
        _verify_version_match(
            release_tag, base_version, package_version, module_version
        )
        asset_version = f"{base_version}-smoke-{stamp}"
        return ReleaseMetadata(
            release_tag=release_tag,
            package_version=base_version,
            asset_version=asset_version,
            release_kind="smoke",
            prerelease=True,
            title=f"codectx release smoke {asset_version}",
            notes=(
                f"Release-smoke verification for {base_version}. This prerelease "
                "validates artifact publishing only and is not a production "
                "codectx release."
            ),
        )

    raise ValueError(
        "release tag must be vMAJOR.MINOR.PATCH or "
        "release-smoke/vMAJOR.MINOR.PATCH-smoke-YYYYMMDDHHMM"
    )


def load_package_version(pyproject_path: Path) -> str:
    """Read the package version from pyproject.toml."""
    with pyproject_path.open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    if not isinstance(version, str):
        raise ValueError("project.version must be a string")
    return version


def load_module_version(module_path: Path) -> str:
    """Read __version__ from src/codectx/__init__.py without importing it."""
    module = ast.parse(module_path.read_text(encoding="utf-8"))
    for node in module.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__version__"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise ValueError("__version__ not found")


def write_github_env(path: Path, metadata: ReleaseMetadata) -> None:
    """Append release metadata to a GitHub Actions environment file."""
    lines = [
        f"RELEASE_TAG={metadata.release_tag}",
        f"PACKAGE_VERSION={metadata.package_version}",
        f"ASSET_VERSION={metadata.asset_version}",
        f"RELEASE_KIND={metadata.release_kind}",
        f"RELEASE_PRERELEASE={str(metadata.prerelease).lower()}",
        f"RELEASE_TITLE={metadata.title}",
        f"RELEASE_NOTES={metadata.notes}",
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for release tag validation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--module", type=Path, default=Path("src/codectx/__init__.py"))
    parser.add_argument("--github-env", type=Path, default=None)
    args = parser.parse_args(argv)

    metadata = validate_release_tag(
        args.tag,
        package_version=load_package_version(args.pyproject),
        module_version=load_module_version(args.module),
    )
    if args.github_env is not None:
        write_github_env(args.github_env, metadata)
    else:
        print(json.dumps(asdict(metadata), sort_keys=True))
    return 0


def _verify_version_match(
    release_tag: str, release_version: str, package_version: str, module_version: str
) -> None:
    if package_version != release_version:
        raise ValueError(
            f"pyproject version {package_version} does not match {release_tag}"
        )
    if module_version != release_version:
        raise ValueError(
            f"module version {module_version} does not match {release_tag}"
        )


def _validate_stamp(stamp: str) -> None:
    try:
        parsed = datetime.strptime(stamp, "%Y%m%d%H%M")
    except ValueError as exc:
        raise ValueError(f"invalid release-smoke timestamp: {stamp}") from exc
    if parsed.strftime("%Y%m%d%H%M") != stamp:
        raise ValueError(f"invalid release-smoke timestamp: {stamp}")


if __name__ == "__main__":
    raise SystemExit(main())
