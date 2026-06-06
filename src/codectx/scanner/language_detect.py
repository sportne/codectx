"""Source language and test-file detection helpers."""

from __future__ import annotations

from pathlib import Path

JAVA_EXTENSIONS = {".java"}
CPP_EXTENSIONS = {".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hh", ".hxx", ".h++", ".h"}
PYTHON_EXTENSIONS = {".py", ".pyi"}
MATLAB_EXTENSIONS = {".m"}


def detect_language(path: str | Path) -> str | None:
    """Detect the source language for a path by extension."""
    suffix = Path(path).suffix.lower()
    if suffix in JAVA_EXTENSIONS:
        return "java"
    if suffix in CPP_EXTENSIONS:
        return "cpp"
    if suffix in PYTHON_EXTENSIONS:
        return "python"
    if suffix in MATLAB_EXTENSIONS:
        return "matlab"
    return None


def is_likely_test(path: str | Path) -> bool:
    """Return whether a path looks like a test source file."""
    p = Path(path).as_posix().lower()
    name = Path(path).name.lower()
    return (
        "/test/" in p
        or "/tests/" in p
        or name.endswith("test.java")
        or name.endswith("tests.java")
        or name.endswith("_test.cpp")
        or name.endswith("test.cpp")
        or name.endswith("_test.py")
        or name.startswith("test_")
    )
