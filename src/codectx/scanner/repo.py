"""Repository walking and source file classification."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pathspec import PathSpec

from codectx.scanner.hashing import content_sha256
from codectx.scanner.language_detect import detect_language, is_likely_test
from codectx.scanner.models import FileRecord
from codectx.source.spans import line_count

IGNORED_DIR_NAMES: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".codectx",
        "node_modules",
        "target",
        "build",
        "out",
        "dist",
        ".venv",
        "venv",
        "__pycache__",
        ".gradle",
        ".idea",
        ".vscode",
    }
)

GENERATED_PATH_HINTS: Final[frozenset[str]] = frozenset(
    {"generated", "gen", "autogen", "auto-generated"}
)
VENDOR_PATH_HINTS: Final[frozenset[str]] = frozenset(
    {"vendor", "vendors", "third_party", "third-party", "external"}
)
IGNORE_FILE_NAMES: Final[frozenset[str]] = frozenset({".gitignore", ".ignore"})


@dataclass(frozen=True)
class ScanOptions:
    """Repository scan filtering controls."""

    include_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    force_include_patterns: tuple[str, ...] = ()
    use_ignore_files: bool = True


@dataclass(frozen=True)
class _IgnoreSpec:
    base_path: str
    spec: PathSpec


def scan_repository(
    repo_root: str | Path, options: ScanOptions | None = None
) -> list[FileRecord]:
    """Return source file records discovered under a repository root."""
    root = Path(repo_root)
    scan_options = options if options is not None else ScanOptions()
    filters = _ScanFilters.from_options(root, scan_options)
    records: list[FileRecord] = []

    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = _visible_directories(
            dirnames, prune_builtin_ignored=not scan_options.force_include_patterns
        )
        current_dir = Path(directory)

        for filename in sorted(filenames):
            path = current_dir / filename
            relative_path = path.relative_to(root).as_posix()
            language = detect_language(relative_path)
            if language is None:
                continue
            if not filters.should_include(relative_path):
                continue

            content = path.read_bytes()
            is_generated = _is_likely_generated(relative_path)
            is_vendor = _is_likely_vendor(relative_path)
            metadata: dict[str, object] = {}
            if is_vendor:
                metadata["is_vendor"] = True

            records.append(
                FileRecord(
                    path=relative_path,
                    language=language,
                    content_hash=content_sha256(content),
                    size_bytes=len(content),
                    line_count=line_count(content),
                    is_test=is_likely_test(relative_path),
                    is_generated=is_generated,
                    metadata=metadata,
                )
            )

    return records


@dataclass(frozen=True)
class _ScanFilters:
    include_spec: PathSpec | None
    exclude_spec: PathSpec | None
    force_include_spec: PathSpec | None
    ignore_specs: tuple[_IgnoreSpec, ...]

    @classmethod
    def from_options(cls, root: Path, options: ScanOptions) -> _ScanFilters:
        return cls(
            include_spec=_compile_patterns(options.include_patterns),
            exclude_spec=_compile_patterns(options.exclude_patterns),
            force_include_spec=_compile_patterns(options.force_include_patterns),
            ignore_specs=(
                _load_ignore_specs(
                    root,
                    include_builtin_ignored=bool(options.force_include_patterns),
                )
                if options.use_ignore_files
                else ()
            ),
        )

    def should_include(self, relative_path: str) -> bool:
        force_included = _matches_spec(self.force_include_spec, relative_path)
        if force_included:
            return True
        if _is_in_builtin_ignored_path(relative_path):
            return False
        if _matches_any_ignore_file(self.ignore_specs, relative_path):
            return False
        if _matches_spec(self.exclude_spec, relative_path):
            return False
        return self.include_spec is None or _matches_spec(
            self.include_spec, relative_path
        )


def _visible_directories(
    dirnames: list[str], *, prune_builtin_ignored: bool
) -> list[str]:
    if not prune_builtin_ignored:
        return sorted(dirnames)
    return sorted(name for name in dirnames if not _is_ignored_directory(name))


def _is_ignored_directory(name: str) -> bool:
    return name in IGNORED_DIR_NAMES or name.startswith("bazel-")


def _is_in_builtin_ignored_path(path: str) -> bool:
    return any(_is_ignored_directory(part) for part in Path(path).parts[:-1])


def _compile_patterns(patterns: tuple[str, ...]) -> PathSpec | None:
    if not patterns:
        return None
    return PathSpec.from_lines("gitwildmatch", patterns)


def _load_ignore_specs(
    root: Path, *, include_builtin_ignored: bool
) -> tuple[_IgnoreSpec, ...]:
    specs: list[_IgnoreSpec] = []
    for directory, dirnames, filenames in os.walk(root):
        if not include_builtin_ignored:
            dirnames[:] = _visible_directories(dirnames, prune_builtin_ignored=True)
        else:
            dirnames[:] = sorted(dirnames)
        current_dir = Path(directory)
        base_path = (
            "" if current_dir == root else current_dir.relative_to(root).as_posix()
        )
        for filename in sorted(name for name in filenames if name in IGNORE_FILE_NAMES):
            lines = (current_dir / filename).read_text(encoding="utf-8").splitlines()
            specs.append(
                _IgnoreSpec(base_path, PathSpec.from_lines("gitwildmatch", lines))
            )
    return tuple(specs)


def _matches_spec(spec: PathSpec | None, relative_path: str) -> bool:
    return spec is not None and spec.match_file(relative_path)


def _matches_any_ignore_file(
    ignore_specs: tuple[_IgnoreSpec, ...], relative_path: str
) -> bool:
    ignored = False
    for ignore_spec in ignore_specs:
        relative_to_ignore_file = _path_relative_to_ignore_file(
            ignore_spec, relative_path
        )
        if relative_to_ignore_file is None:
            continue
        for pattern in ignore_spec.spec.patterns:
            if pattern.match_file(relative_to_ignore_file) is not None:
                ignored = bool(pattern.include)
    return ignored


def _path_relative_to_ignore_file(
    ignore_spec: _IgnoreSpec, relative_path: str
) -> str | None:
    if not ignore_spec.base_path:
        return relative_path
    prefix = f"{ignore_spec.base_path}/"
    if not relative_path.startswith(prefix):
        return None
    return relative_path.removeprefix(prefix)


def _is_likely_generated(path: str) -> bool:
    parts = {part.lower() for part in Path(path).parts}
    name = Path(path).name.lower()
    return bool(parts & GENERATED_PATH_HINTS) or name.endswith(".generated.java")


def _is_likely_vendor(path: str) -> bool:
    parts = {part.lower() for part in Path(path).parts}
    return bool(parts & VENDOR_PATH_HINTS)
