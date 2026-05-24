"""Repository walking and source file classification."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Final

from codectx.scanner.language_detect import detect_language, is_likely_test
from codectx.scanner.models import FileRecord

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


def scan_repository(repo_root: str | Path) -> list[FileRecord]:
    """Return source file records discovered under a repository root."""
    root = Path(repo_root)
    records: list[FileRecord] = []

    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = _visible_directories(dirnames)
        current_dir = Path(directory)

        for filename in sorted(filenames):
            path = current_dir / filename
            relative_path = path.relative_to(root).as_posix()
            language = detect_language(relative_path)
            if language is None:
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
                    content_hash=hashlib.sha256(content).hexdigest(),
                    size_bytes=len(content),
                    line_count=_count_lines(content),
                    is_test=is_likely_test(relative_path),
                    is_generated=is_generated,
                    metadata=metadata,
                )
            )

    return records


def _visible_directories(dirnames: list[str]) -> list[str]:
    return sorted(name for name in dirnames if not _is_ignored_directory(name))


def _is_ignored_directory(name: str) -> bool:
    return name in IGNORED_DIR_NAMES or name.startswith("bazel-")


def _count_lines(content: bytes) -> int:
    if not content:
        return 0
    line_count = content.count(b"\n")
    if not content.endswith(b"\n"):
        line_count += 1
    return line_count


def _is_likely_generated(path: str) -> bool:
    parts = {part.lower() for part in Path(path).parts}
    name = Path(path).name.lower()
    return bool(parts & GENERATED_PATH_HINTS) or name.endswith(".generated.java")


def _is_likely_vendor(path: str) -> bool:
    parts = {part.lower() for part in Path(path).parts}
    return bool(parts & VENDOR_PATH_HINTS)
