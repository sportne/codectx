from __future__ import annotations

import hashlib
from pathlib import Path

from codectx.scanner.hashing import content_sha256, file_sha256


def test_content_sha256_returns_hex_digest() -> None:
    content = b"class Foo {}\n"

    assert content_sha256(content) == hashlib.sha256(content).hexdigest()


def test_file_sha256_reads_file_bytes(tmp_path: Path) -> None:
    source_path = tmp_path / "Cafe.java"
    content = 'class Cafe { String name = "caf\u00e9"; }\n'.encode()
    source_path.write_bytes(content)

    assert file_sha256(source_path) == hashlib.sha256(content).hexdigest()
