from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from codectx.source.spans import SourceSpan


@dataclass(frozen=True)
class NodeFact:
    kind: str
    language: str | None
    name: str | None
    qualified_name: str | None
    symbol_key: str | None
    file_path: str | None
    span: SourceSpan | None
    confidence: float
    extractor: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EdgeFact:
    kind: str
    src_key: str | None
    dst_key: str | None
    unresolved_src: str | None
    unresolved_dst: str | None
    file_path: str | None
    span: SourceSpan | None
    confidence: float
    extractor: str
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OccurrenceFact:
    file_path: str
    role: str
    text: str
    span: SourceSpan
    node_key: str | None
    resolved_key: str | None
    confidence: float
    extractor: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkFact:
    file_path: str
    node_key: str | None
    kind: str
    start_line: int
    end_line: int
    text: str
    token_estimate: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DiagnosticFact:
    file_path: str | None
    severity: str
    message: str
    extractor: str
    span: SourceSpan | None = None
    code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractedFacts:
    nodes: list[NodeFact] = field(default_factory=list)
    edges: list[EdgeFact] = field(default_factory=list)
    occurrences: list[OccurrenceFact] = field(default_factory=list)
    chunks: list[ChunkFact] = field(default_factory=list)
    diagnostics: list[DiagnosticFact] = field(default_factory=list)


class LanguageFrontend(Protocol):
    language: str

    def extract(self, file_path: str, source: bytes) -> ExtractedFacts:
        """Extract normalized graph facts from a source file."""
        ...
