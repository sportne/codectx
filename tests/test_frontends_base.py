from __future__ import annotations

from dataclasses import asdict

from codectx.frontends.base import (
    ChunkFact,
    DiagnosticFact,
    EdgeFact,
    ExtractedFacts,
    LanguageFrontend,
    NodeFact,
    OccurrenceFact,
)
from codectx.source.spans import SourceSpan


class DummyFrontend:
    language = "java"

    def extract(self, file_path: str, source: bytes) -> ExtractedFacts:
        text = source.decode("utf-8")
        span = SourceSpan(
            file_path=file_path,
            start_byte=0,
            end_byte=len(source),
            start_line=1,
            start_col=0,
            end_line=1,
            end_col=len(text),
        )
        return ExtractedFacts(
            nodes=[
                NodeFact(
                    kind="class",
                    language=self.language,
                    name="PaymentService",
                    qualified_name="acme.PaymentService",
                    symbol_key="java:acme.PaymentService",
                    file_path=file_path,
                    span=span,
                    confidence=1.0,
                    extractor="dummy",
                )
            ],
            edges=[
                EdgeFact(
                    kind="defines",
                    src_key="file:PaymentService.java",
                    dst_key="java:acme.PaymentService",
                    unresolved_src=None,
                    unresolved_dst=None,
                    file_path=file_path,
                    span=span,
                    confidence=1.0,
                    extractor="dummy",
                )
            ],
            occurrences=[
                OccurrenceFact(
                    file_path=file_path,
                    role="definition",
                    text="PaymentService",
                    span=span,
                    node_key="java:acme.PaymentService",
                    resolved_key="java:acme.PaymentService",
                    confidence=1.0,
                    extractor="dummy",
                )
            ],
            chunks=[
                ChunkFact(
                    file_path=file_path,
                    node_key="java:acme.PaymentService",
                    kind="class",
                    start_line=1,
                    end_line=1,
                    text=text,
                    token_estimate=4,
                )
            ],
            diagnostics=[
                DiagnosticFact(
                    file_path=file_path,
                    severity="info",
                    message="parsed",
                    extractor="dummy",
                    span=span,
                    code="DUMMY",
                )
            ],
        )


def test_language_frontend_protocol_extracts_normalized_facts() -> None:
    frontend: LanguageFrontend = DummyFrontend()

    facts = frontend.extract("PaymentService.java", b"class PaymentService {}")

    assert facts.nodes[0].qualified_name == "acme.PaymentService"
    assert facts.edges[0].weight == 1.0
    assert facts.occurrences[0].text == "PaymentService"
    assert facts.chunks[0].token_estimate == 4
    assert facts.diagnostics[0].code == "DUMMY"
    assert asdict(facts) == {
        "nodes": [
            {
                "kind": "class",
                "language": "java",
                "name": "PaymentService",
                "qualified_name": "acme.PaymentService",
                "symbol_key": "java:acme.PaymentService",
                "file_path": "PaymentService.java",
                "span": {
                    "file_path": "PaymentService.java",
                    "start_byte": 0,
                    "end_byte": 23,
                    "start_line": 1,
                    "start_col": 0,
                    "end_line": 1,
                    "end_col": 23,
                },
                "confidence": 1.0,
                "extractor": "dummy",
                "metadata": {},
            }
        ],
        "edges": [
            {
                "kind": "defines",
                "src_key": "file:PaymentService.java",
                "dst_key": "java:acme.PaymentService",
                "unresolved_src": None,
                "unresolved_dst": None,
                "file_path": "PaymentService.java",
                "span": {
                    "file_path": "PaymentService.java",
                    "start_byte": 0,
                    "end_byte": 23,
                    "start_line": 1,
                    "start_col": 0,
                    "end_line": 1,
                    "end_col": 23,
                },
                "confidence": 1.0,
                "extractor": "dummy",
                "weight": 1.0,
                "metadata": {},
            }
        ],
        "occurrences": [
            {
                "file_path": "PaymentService.java",
                "role": "definition",
                "text": "PaymentService",
                "span": {
                    "file_path": "PaymentService.java",
                    "start_byte": 0,
                    "end_byte": 23,
                    "start_line": 1,
                    "start_col": 0,
                    "end_line": 1,
                    "end_col": 23,
                },
                "node_key": "java:acme.PaymentService",
                "resolved_key": "java:acme.PaymentService",
                "confidence": 1.0,
                "extractor": "dummy",
                "metadata": {},
            }
        ],
        "chunks": [
            {
                "file_path": "PaymentService.java",
                "node_key": "java:acme.PaymentService",
                "kind": "class",
                "start_line": 1,
                "end_line": 1,
                "text": "class PaymentService {}",
                "token_estimate": 4,
                "metadata": {},
            }
        ],
        "diagnostics": [
            {
                "file_path": "PaymentService.java",
                "severity": "info",
                "message": "parsed",
                "extractor": "dummy",
                "span": {
                    "file_path": "PaymentService.java",
                    "start_byte": 0,
                    "end_byte": 23,
                    "start_line": 1,
                    "start_col": 0,
                    "end_line": 1,
                    "end_col": 23,
                },
                "code": "DUMMY",
                "metadata": {},
            }
        ],
    }
