from __future__ import annotations

from codectx.source.decoding import validate_source_bytes


def test_validate_source_bytes_accepts_utf8_bom() -> None:
    result = validate_source_bytes("src/Cafe.java", b"\xef\xbb\xbfclass Cafe {}\n")

    assert result.ok
    assert result.encoding == "utf-8-sig"


def test_validate_source_bytes_reports_invalid_utf8_offset() -> None:
    result = validate_source_bytes("src/Bad.java", b"class Bad {\xff}\n")

    assert not result.ok
    assert result.issues[0].code == "invalid_utf8"
    assert result.issues[0].byte_offset == 11
    assert "not valid UTF-8" in result.issues[0].message


def test_validate_source_bytes_reports_binary_content() -> None:
    result = validate_source_bytes("src/Binary.cpp", b"int main() {}\x00more")

    assert not result.ok
    assert result.issues[0].code == "binary_source"
    assert result.issues[0].byte_offset == 13
    assert "binary content" in result.issues[0].message
