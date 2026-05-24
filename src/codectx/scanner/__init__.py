"""Repository scanning and language detection support."""

from codectx.scanner.models import FileRecord
from codectx.scanner.repo import scan_repository

__all__ = ["FileRecord", "scan_repository"]
