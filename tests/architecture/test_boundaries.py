from __future__ import annotations

import ast
from pathlib import Path

import pytest

from . import _helpers as helpers

FORBIDDEN_IMPORTS_BY_LAYER = {
    "source": (
        "codectx.scanner",
        "codectx.frontends",
        "codectx.graph",
        "codectx.context",
        "codectx.cli",
    ),
    "scanner": (
        "codectx.frontends",
        "codectx.graph",
        "codectx.context",
        "codectx.cli",
    ),
    "frontends": (
        "codectx.scanner",
        "codectx.graph",
        "codectx.context",
        "codectx.cli",
    ),
    "graph": (
        "codectx.scanner",
        "codectx.frontends",
        "codectx.context",
        "codectx.cli",
    ),
    "context": (
        "codectx.scanner",
        "codectx.frontends",
        "codectx.cli",
    ),
}

MODULE_IMPORT_ALLOWLIST = {
    "sqlite3": ("codectx.graph",),
    "tree_sitter": ("codectx.frontends",),
}


@pytest.mark.parametrize(
    ("layer_name", "forbidden_prefixes"),
    list(FORBIDDEN_IMPORTS_BY_LAYER.items()),
)
def test_layer_import_boundaries(
    layer_name: str, forbidden_prefixes: tuple[str, ...]
) -> None:
    layer_root = helpers.PACKAGE_DIR / layer_name
    violations: list[str] = []

    for source_file in helpers.iter_python_files(layer_root):
        for reference in helpers.iter_import_references(source_file):
            for forbidden_prefix in forbidden_prefixes:
                if helpers.is_forbidden_module(reference.module, forbidden_prefix):
                    violations.append(
                        helpers.format_reference(
                            reference.path,
                            reference.lineno,
                            f"{layer_name} must not import '{reference.module}'",
                        )
                    )
                    break

    assert not violations, (
        f"Forbidden imports found in layer '{layer_name}':\n" + "\n".join(violations)
    )


@pytest.mark.parametrize(
    ("module_prefix", "allowed_package_prefixes"),
    list(MODULE_IMPORT_ALLOWLIST.items()),
)
def test_sensitive_imports_stay_in_approved_layers(
    module_prefix: str, allowed_package_prefixes: tuple[str, ...]
) -> None:
    violations: list[str] = []

    for source_file in helpers.iter_python_files(helpers.PACKAGE_DIR):
        importer = helpers.module_name_for_path(source_file)
        for reference in helpers.iter_import_references(source_file):
            if not helpers.is_forbidden_module(reference.module, module_prefix):
                continue
            if any(
                helpers.is_forbidden_module(importer, allowed_prefix)
                for allowed_prefix in allowed_package_prefixes
            ):
                continue
            violations.append(
                helpers.format_reference(
                    reference.path,
                    reference.lineno,
                    f"'{reference.module}' import is only allowed in {allowed_package_prefixes}",
                )
            )

    assert not violations, "\n".join(violations)


def test_direct_print_calls_stay_in_cli() -> None:
    violations: list[str] = []

    for source_file in helpers.iter_python_files(helpers.PACKAGE_DIR):
        importer = helpers.module_name_for_path(source_file)
        if helpers.is_forbidden_module(importer, "codectx.cli"):
            continue
        tree = helpers.parse_module(source_file)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                violations.append(
                    helpers.format_reference(
                        source_file,
                        node.lineno,
                        "direct print() is only allowed in codectx.cli",
                    )
                )

    assert not violations, "\n".join(violations)


def test_cli_keeps_indexing_orchestration_in_indexing_service() -> None:
    cli_path = helpers.PACKAGE_DIR / "cli.py"
    forbidden = (
        "codectx.frontends",
        "codectx.graph.store",
        "codectx.scanner",
    )
    violations: list[str] = []

    for reference in helpers.iter_import_references(cli_path):
        if any(
            helpers.is_forbidden_module(reference.module, forbidden_prefix)
            for forbidden_prefix in forbidden
        ):
            violations.append(
                helpers.format_reference(
                    reference.path,
                    reference.lineno,
                    f"cli must delegate indexing orchestration instead of importing '{reference.module}'",
                )
            )

    assert not violations, "\n".join(violations)


def test_cli_imports_index_and_health_services_from_indexing_module() -> None:
    cli_path = helpers.PACKAGE_DIR / "cli.py"
    imported_names: set[str] = set()

    tree = helpers.parse_module(cli_path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if helpers.resolve_from_import(cli_path, node) != "codectx.indexing":
            continue
        imported_names.update(alias.name for alias in node.names)

    assert {"run_index", "read_health"} <= imported_names


def test_indexing_orchestration_has_single_service_module() -> None:
    disallowed_service_names = {
        "index_service",
        "indexing_service",
        "indexer",
        "indexers",
    }
    duplicate_services = sorted(
        path
        for path in helpers.iter_python_files(helpers.PACKAGE_DIR)
        if path.stem in disallowed_service_names
    )

    assert duplicate_services == []


def test_internal_private_modules_are_not_imported_cross_layer() -> None:
    violations: list[str] = []

    for source_file in helpers.iter_python_files(helpers.PACKAGE_DIR):
        importer_layer = _layer_for_path(source_file)
        for reference in helpers.iter_import_references(source_file):
            if not reference.module.startswith("codectx."):
                continue
            imported_layer = _layer_for_module(reference.module)
            if imported_layer == importer_layer:
                continue
            if any(
                part.startswith("_") and not part.startswith("__")
                for part in reference.module.split(".")[1:]
            ):
                violations.append(
                    helpers.format_reference(
                        reference.path,
                        reference.lineno,
                        f"cross-layer private import '{reference.module}' is forbidden",
                    )
                )

    assert not violations, "\n".join(violations)


def test_internal_private_symbols_are_not_imported_cross_layer() -> None:
    violations: list[str] = []

    for source_file in helpers.iter_python_files(helpers.PACKAGE_DIR):
        importer_layer = _layer_for_path(source_file)
        tree = helpers.parse_module(source_file)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            resolved = helpers.resolve_from_import(source_file, node)
            if resolved is None or not resolved.startswith("codectx."):
                continue
            imported_layer = _layer_for_module(resolved)
            if imported_layer == importer_layer:
                continue
            for alias in node.names:
                if alias.name.startswith("_") and not alias.name.startswith("__"):
                    violations.append(
                        helpers.format_reference(
                            source_file,
                            node.lineno,
                            f"cross-layer private symbol '{resolved}.{alias.name}' is forbidden",
                        )
                    )

    assert not violations, "\n".join(violations)


def test_relative_import_resolution_handles_package_context(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    module_path = src_dir / "codectx" / "context" / "example.py"
    module_path.parent.mkdir(parents=True)
    module_path.write_text(
        "\n".join(
            (
                "from codectx import graph",
                "from ..graph import store",
                "from . import planner",
            )
        ),
        encoding="utf-8",
    )

    original_src_dir = helpers.SRC_DIR
    helpers.SRC_DIR = src_dir
    try:
        modules = {
            reference.module
            for reference in helpers.iter_import_references(module_path)
        }
    finally:
        helpers.SRC_DIR = original_src_dir

    assert {
        "codectx.graph",
        "codectx.graph.store",
        "codectx.context.planner",
    } <= modules


def _layer_for_path(path: Path) -> str:
    relative_parts = path.relative_to(helpers.PACKAGE_DIR).parts
    if len(relative_parts) == 1:
        return "__root__"
    return relative_parts[0]


def _layer_for_module(module: str) -> str:
    parts = module.split(".")
    if len(parts) < 2:
        return "__root__"
    return parts[1]
