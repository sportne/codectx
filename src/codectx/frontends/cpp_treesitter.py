"""C++ Tree-sitter frontend."""

from __future__ import annotations

import tree_sitter_cpp
from tree_sitter import Parser

from codectx.frontends.base import DiagnosticFact, ExtractedFacts
from codectx.frontends.treesitter_base import (
    error_nodes,
    make_language,
    make_parser,
    node_span,
    parse_source,
)

EXTRACTOR = "treesitter-cpp"


class CppTreeSitterFrontend:
    """Tree-sitter based C++ frontend."""

    language = "cpp"

    def __init__(self, parser: Parser | None = None) -> None:
        """Create a C++ frontend with an optional parser override."""
        self._parser = parser or make_parser(make_language(tree_sitter_cpp.language()))

    def extract(self, file_path: str, source: bytes) -> ExtractedFacts:
        """Parse C++ source and return parser diagnostics."""
        parsed = parse_source(self._parser, source)
        diagnostics: list[DiagnosticFact] = []
        if parsed.root.has_error:
            diagnostics = [
                DiagnosticFact(
                    file_path=file_path,
                    severity="error",
                    message=f"C++ parse error at {node.type}",
                    extractor=EXTRACTOR,
                    span=node_span(file_path, source, node),
                    code=node.type,
                )
                for node in error_nodes(parsed.root)
            ]
            if not diagnostics:
                diagnostics.append(
                    DiagnosticFact(
                        file_path=file_path,
                        severity="error",
                        message="C++ parse error",
                        extractor=EXTRACTOR,
                        span=node_span(file_path, source, parsed.root),
                        code="parse_error",
                    )
                )
        return ExtractedFacts(diagnostics=diagnostics)
