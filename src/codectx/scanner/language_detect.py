from __future__ import annotations

from pathlib import Path

JAVA_EXTENSIONS = {".java"}
CPP_EXTENSIONS = {".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hh", ".hxx", ".h++", ".h"}


def detect_language(path: str | Path) -> str | None:
    suffix = Path(path).suffix.lower()
    if suffix in JAVA_EXTENSIONS:
        return "java"
    if suffix in CPP_EXTENSIONS:
        return "cpp"
    return None


def is_likely_test(path: str | Path) -> bool:
    p = Path(path).as_posix().lower()
    name = Path(path).name.lower()
    return (
        "/test/" in p
        or "/tests/" in p
        or name.endswith("test.java")
        or name.endswith("tests.java")
        or name.endswith("_test.cpp")
        or name.endswith("test.cpp")
        or name.startswith("test_")
    )
