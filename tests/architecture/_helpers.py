from __future__ import annotations

import ast
import os
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
PACKAGE_DIR = SRC_DIR / "codectx"

_SKIPPED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "build",
    "dist",
    "__pycache__",
    "venv",
}


@dataclass(frozen=True, slots=True)
class ImportReference:
    path: Path
    lineno: int
    module: str


def iter_python_files(root: Path) -> Iterator[Path]:
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in _SKIPPED_PARTS)
        current_dir = Path(directory)
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                yield current_dir / filename


@cache
def parse_module(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def module_name_for_path(path: Path) -> str:
    relative = path.relative_to(SRC_DIR).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def package_name_for_path(path: Path) -> str:
    module_name = module_name_for_path(path)
    if path.name == "__init__.py":
        return module_name
    return ".".join(module_name.split(".")[:-1])


def resolve_from_import(path: Path, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module

    package_name = package_name_for_path(path)
    if package_name == "":
        return None

    package_parts = package_name.split(".")
    if node.level - 1 > len(package_parts):
        return None

    base_parts = package_parts[: len(package_parts) - (node.level - 1)]
    if node.module is not None:
        base_parts.extend(node.module.split("."))
    return ".".join(base_parts)


def iter_import_references(path: Path) -> Iterator[ImportReference]:
    tree = parse_module(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield ImportReference(path=path, lineno=node.lineno, module=alias.name)
        elif isinstance(node, ast.ImportFrom):
            resolved = resolve_from_import(path, node)
            if resolved is None:
                continue
            for alias in node.names:
                module = resolved if alias.name == "*" else f"{resolved}.{alias.name}"
                yield ImportReference(path=path, lineno=node.lineno, module=module)


def format_reference(path: Path, lineno: int, detail: str) -> str:
    return f"{path.relative_to(ROOT_DIR)}:{lineno}: {detail}"


def is_forbidden_module(module: str, forbidden_prefix: str) -> bool:
    return module == forbidden_prefix or module.startswith(f"{forbidden_prefix}.")
