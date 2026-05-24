from __future__ import annotations

from codectx.frontends.base import LanguageFrontend
from codectx.frontends.java_treesitter import JavaTreeSitterFrontend


def test_java_frontend_satisfies_language_frontend_protocol() -> None:
    frontend: LanguageFrontend = JavaTreeSitterFrontend()

    assert frontend.language == "java"


def test_java_frontend_parses_valid_source_without_diagnostics() -> None:
    frontend = JavaTreeSitterFrontend()

    facts = frontend.extract("src/Foo.java", b"class Foo { void bar() {} }\n")

    assert facts.nodes == []
    assert facts.edges == []
    assert facts.occurrences == []
    assert facts.chunks == []
    assert facts.diagnostics == []


def test_java_frontend_records_diagnostics_for_invalid_source() -> None:
    frontend = JavaTreeSitterFrontend()

    facts = frontend.extract("src/Foo.java", b"class Foo {")

    assert facts.diagnostics
    diagnostic = facts.diagnostics[0]
    assert diagnostic.file_path == "src/Foo.java"
    assert diagnostic.severity == "error"
    assert diagnostic.extractor == "treesitter-java"
    assert "Java parse error" in diagnostic.message
    assert diagnostic.span is not None
    assert diagnostic.span.file_path == "src/Foo.java"
