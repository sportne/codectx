from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def test_validate_production_release_tag() -> None:
    module = _load_module()

    metadata = module.validate_release_tag(
        "v0.1.0", package_version="0.1.0", module_version="0.1.0"
    )

    assert metadata.package_version == "0.1.0"
    assert metadata.asset_version == "0.1.0"
    assert metadata.release_kind == "production"
    assert metadata.prerelease is False
    assert metadata.title == "codectx 0.1.0"


def test_validate_smoke_release_tag() -> None:
    module = _load_module()

    metadata = module.validate_release_tag(
        "release-smoke/v0.1.0-smoke-202605300915",
        package_version="0.1.0",
        module_version="0.1.0",
    )

    assert metadata.package_version == "0.1.0"
    assert metadata.asset_version == "0.1.0-smoke-202605300915"
    assert metadata.release_kind == "smoke"
    assert metadata.prerelease is True
    assert "not a production" in metadata.notes


def test_validate_release_tag_rejects_bad_shape() -> None:
    module = _load_module()

    try:
        module.validate_release_tag(
            "release-test/v0.1.0", package_version="0.1.0", module_version="0.1.0"
        )
    except ValueError as exc:
        assert "release-smoke" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected ValueError")


def test_validate_release_tag_rejects_invalid_smoke_timestamp() -> None:
    module = _load_module()

    try:
        module.validate_release_tag(
            "release-smoke/v0.1.0-smoke-202613400999",
            package_version="0.1.0",
            module_version="0.1.0",
        )
    except ValueError as exc:
        assert "invalid release-smoke timestamp" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected ValueError")


def test_validate_release_tag_rejects_version_mismatch() -> None:
    module = _load_module()

    try:
        module.validate_release_tag(
            "v0.1.0", package_version="0.1.1", module_version="0.1.0"
        )
    except ValueError as exc:
        assert "pyproject version 0.1.1" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected ValueError")


def test_write_github_env(tmp_path: Path) -> None:
    module = _load_module()
    metadata = module.validate_release_tag(
        "release-smoke/v0.1.0-smoke-202605300915",
        package_version="0.1.0",
        module_version="0.1.0",
    )
    env_path = tmp_path / "github.env"

    module.write_github_env(env_path, metadata)

    assert "ASSET_VERSION=0.1.0-smoke-202605300915" in env_path.read_text(
        encoding="utf-8"
    )
    assert "RELEASE_PRERELEASE=true" in env_path.read_text(encoding="utf-8")


def _load_module() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "validate_release_tag.py"
    spec = importlib.util.spec_from_file_location("validate_release_tag", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
