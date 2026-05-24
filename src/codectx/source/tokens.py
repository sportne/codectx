"""Approximate token accounting helpers."""

from __future__ import annotations


def estimate_token_count(text: str) -> int:
    """Return a deterministic rough token estimate using ceil(chars / 4)."""
    if not text:
        return 0
    return (len(text) + 3) // 4
