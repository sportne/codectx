from __future__ import annotations

import hashlib
from pathlib import Path

from codectx.scanner.repo import scan_repository


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
