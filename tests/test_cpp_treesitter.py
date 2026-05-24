from __future__ import annotations

from codectx.frontends.base import LanguageFrontend
from codectx.frontends.cpp_treesitter import CppTreeSitterFrontend


def test_cpp_frontend_satisfies_language_frontend_protocol() -> None:
    frontend: LanguageFrontend = CppTreeSitterFrontend()

    assert frontend.language == "cpp"


def test_cpp_frontend_parses_valid_source_without_diagnostics() -> None:
    frontend = CppTreeSitterFrontend()

    facts = frontend.extract("src/foo.cpp", b"int main() { return 0; }\n")

    assert facts.nodes == []
    assert facts.edges == []
    assert facts.occurrences == []
    assert facts.chunks == []
    assert facts.diagnostics == []


def test_cpp_frontend_records_diagnostics_for_invalid_source() -> None:
    frontend = CppTreeSitterFrontend()

    facts = frontend.extract("src/foo.cpp", b"int main( {")

    assert facts.diagnostics
    diagnostic = facts.diagnostics[0]
    assert diagnostic.file_path == "src/foo.cpp"
    assert diagnostic.severity == "error"
    assert diagnostic.extractor == "treesitter-cpp"
    assert "C++ parse error" in diagnostic.message
    assert diagnostic.span is not None
    assert diagnostic.span.file_path == "src/foo.cpp"
