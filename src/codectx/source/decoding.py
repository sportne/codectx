"""Source byte validation before parser extraction."""

from __future__ import annotations

from dataclasses import dataclass

UTF8_BOM = b"\xef\xbb\xbf"
TEXT_CONTROL_BYTES = frozenset({0x09, 0x0A, 0x0C, 0x0D})


@dataclass(frozen=True)
class SourceDecodeIssue:
    """Actionable source decoding or binary-content issue."""

    code: str
    message: str
    byte_offset: int | None = None


@dataclass(frozen=True)
class SourceValidation:
    """Validation result for raw source bytes."""

    encoding: str
    issues: tuple[SourceDecodeIssue, ...] = ()

    @property
    def ok(self) -> bool:
        """Return whether the source can be parsed as text."""
        return not self.issues


def validate_source_bytes(file_path: str, content: bytes) -> SourceValidation:
    """Validate supported source bytes before language-specific extraction."""
    binary_offset = _binary_like_offset(content)
    if binary_offset is not None:
        return SourceValidation(
            encoding="binary",
            issues=(
                SourceDecodeIssue(
                    code="binary_source",
                    message=(
                        f"Skipped {file_path}: file appears to contain binary "
                        "content. Exclude it or replace it with UTF-8 source text."
                    ),
                    byte_offset=binary_offset,
                ),
            ),
        )

    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        return SourceValidation(
            encoding="unknown",
            issues=(
                SourceDecodeIssue(
                    code="invalid_utf8",
                    message=(
                        f"Skipped {file_path}: source is not valid UTF-8 at byte "
                        f"{exc.start}. Re-save it as UTF-8 or exclude it."
                    ),
                    byte_offset=exc.start,
                ),
            ),
        )

    return SourceValidation(
        encoding="utf-8-sig" if content.startswith(UTF8_BOM) else "utf-8"
    )


def _binary_like_offset(content: bytes) -> int | None:
    for offset, byte in enumerate(content):
        if byte == 0:
            return offset
        if byte < 0x20 and byte not in TEXT_CONTROL_BYTES:
            return offset
    return None
