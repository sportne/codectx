from __future__ import annotations

from dataclasses import asdict

from codectx.scanner import FileRecord


def test_file_record_defaults_and_serialization() -> None:
    record = FileRecord(
        path="src/main/java/acme/PaymentService.java",
        language="java",
        content_hash="abc123",
        size_bytes=2048,
        line_count=80,
    )

    assert record.is_test is False
    assert record.is_generated is False
    assert record.metadata == {}
    assert asdict(record) == {
        "path": "src/main/java/acme/PaymentService.java",
        "language": "java",
        "content_hash": "abc123",
        "size_bytes": 2048,
        "line_count": 80,
        "is_test": False,
        "is_generated": False,
        "metadata": {},
    }


def test_file_record_metadata_is_not_shared_between_instances() -> None:
    first = FileRecord(
        path="src/Foo.java",
        language="java",
        content_hash="hash-one",
        size_bytes=10,
        line_count=1,
    )
    second = FileRecord(
        path="src/Bar.cpp",
        language="cpp",
        content_hash="hash-two",
        size_bytes=20,
        line_count=2,
    )

    first.metadata["role"] = "fixture"

    assert first.metadata == {"role": "fixture"}
    assert second.metadata == {}
