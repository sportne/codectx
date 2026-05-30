from __future__ import annotations

import hashlib
from pathlib import Path

from codectx.scanner.repo import ScanOptions, scan_repository


def test_scan_repository_finds_java_and_cpp_sources(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "main" / "java" / "acme" / "PaymentService.java", "a\nb")
    _write(tmp_path / "src" / "native" / "payment.cpp", "int main() {}\n")
    _write(tmp_path / "include" / "payment.hpp", "#pragma once\n")
    _write(tmp_path / "README.md", "# ignored\n")

    records = scan_repository(tmp_path)

    assert [record.path for record in records] == [
        "include/payment.hpp",
        "src/main/java/acme/PaymentService.java",
        "src/native/payment.cpp",
    ]
    assert [record.language for record in records] == ["cpp", "java", "cpp"]


def test_scan_repository_skips_builtin_ignored_directories(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "Foo.java", "class Foo {}\n")
    for ignored_dir in (
        ".git",
        ".codectx",
        "node_modules",
        "target",
        "build",
        "bazel-out",
        "out",
        "dist",
        ".venv",
        "venv",
        "__pycache__",
        ".gradle",
        ".idea",
        ".vscode",
    ):
        _write(tmp_path / ignored_dir / "Ignored.java", "class Ignored {}\n")

    records = scan_repository(tmp_path)

    assert [record.path for record in records] == ["src/Foo.java"]


def test_scan_repository_respects_root_ignore_files(tmp_path: Path) -> None:
    _write(tmp_path / ".gitignore", "ignored/\n")
    _write(tmp_path / ".ignore", "scratch.cpp\n")
    _write(tmp_path / "src" / "Foo.java", "class Foo {}\n")
    _write(tmp_path / "ignored" / "Ignored.java", "class Ignored {}\n")
    _write(tmp_path / "scratch.cpp", "int scratch();\n")

    records = scan_repository(tmp_path)

    assert [record.path for record in records] == ["src/Foo.java"]


def test_scan_repository_respects_nested_ignore_files(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "Keep.java", "class Keep {}\n")
    _write(tmp_path / "src" / "generated" / ".gitignore", "*.java\n")
    _write(tmp_path / "src" / "generated" / "Ignored.java", "class Ignored {}\n")
    _write(tmp_path / "other" / "Generated.java", "class Generated {}\n")

    records = scan_repository(tmp_path)

    assert [record.path for record in records] == [
        "other/Generated.java",
        "src/Keep.java",
    ]


def test_scan_repository_allows_nested_ignore_file_negation(tmp_path: Path) -> None:
    _write(tmp_path / ".gitignore", "*.java\n")
    _write(tmp_path / "src" / "generated" / ".gitignore", "!Keep.java\n")
    _write(tmp_path / "src" / "generated" / "Keep.java", "class Keep {}\n")
    _write(tmp_path / "src" / "generated" / "Drop.java", "class Drop {}\n")

    records = scan_repository(tmp_path)

    assert [record.path for record in records] == ["src/generated/Keep.java"]


def test_scan_repository_does_not_read_ignore_files_in_builtin_ignored_directories(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "src" / "Foo.java", "class Foo {}\n")
    gitignore = tmp_path / "build" / ".gitignore"
    gitignore.parent.mkdir(parents=True, exist_ok=True)
    gitignore.write_bytes(b"\xff")

    records = scan_repository(tmp_path)

    assert [record.path for record in records] == ["src/Foo.java"]


def test_scan_repository_supports_include_patterns(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "main" / "Foo.java", "class Foo {}\n")
    _write(tmp_path / "src" / "test" / "FooTest.java", "class FooTest {}\n")

    records = scan_repository(tmp_path, ScanOptions(include_patterns=("src/main/**",)))

    assert [record.path for record in records] == ["src/main/Foo.java"]


def test_scan_repository_supports_explicit_excludes(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "Foo.java", "class Foo {}\n")
    _write(tmp_path / "src" / "Generated.java", "class Generated {}\n")

    records = scan_repository(
        tmp_path, ScanOptions(exclude_patterns=("**/Generated.java",))
    )

    assert [record.path for record in records] == ["src/Foo.java"]


def test_scan_repository_force_include_wins_over_ignores_and_excludes(
    tmp_path: Path,
) -> None:
    _write(tmp_path / ".gitignore", "build/\n")
    _write(tmp_path / "build" / "Forced.java", "class Forced {}\n")
    _write(tmp_path / "build" / "notes.txt", "unsupported\n")

    records = scan_repository(
        tmp_path,
        ScanOptions(
            exclude_patterns=("build/**",),
            force_include_patterns=("build/**",),
        ),
    )

    assert [record.path for record in records] == ["build/Forced.java"]


def test_scan_repository_can_disable_ignore_files(tmp_path: Path) -> None:
    _write(tmp_path / ".gitignore", "ignored/\n")
    _write(tmp_path / "ignored" / "Included.java", "class Included {}\n")
    _write(tmp_path / "build" / "StillIgnored.java", "class StillIgnored {}\n")

    records = scan_repository(tmp_path, ScanOptions(use_ignore_files=False))

    assert [record.path for record in records] == ["ignored/Included.java"]


def test_scan_repository_filters_relative_to_subdirectory_root(tmp_path: Path) -> None:
    module = tmp_path / "repo" / "module"
    _write(module / ".gitignore", "ignored/\n")
    _write(module / "src" / "Foo.java", "class Foo {}\n")
    _write(module / "ignored" / "Ignored.java", "class Ignored {}\n")

    records = scan_repository(module, ScanOptions(include_patterns=("src/**",)))

    assert [record.path for record in records] == ["src/Foo.java"]


def test_scan_repository_populates_file_metadata(tmp_path: Path) -> None:
    source = 'class Foo {\n  String name = "cafe";\n}\n'
    _write(tmp_path / "src" / "test" / "java" / "FooTest.java", source)
    _write(tmp_path / "generated" / "proto" / "Message.java", "class Message {}\n")
    _write(tmp_path / "vendor" / "lib" / "Vendor.cpp", "int vendor();\n")

    records = {record.path: record for record in scan_repository(tmp_path)}

    test_record = records["src/test/java/FooTest.java"]
    assert test_record.content_hash == hashlib.sha256(source.encode()).hexdigest()
    assert test_record.size_bytes == len(source.encode())
    assert test_record.line_count == 3
    assert test_record.is_test is True
    assert test_record.is_generated is False

    assert records["generated/proto/Message.java"].is_generated is True
    assert records["vendor/lib/Vendor.cpp"].metadata == {"is_vendor": True}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
