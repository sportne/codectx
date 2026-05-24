from __future__ import annotations

import codectx.frontends.cpp_treesitter as cpp_treesitter
from codectx.frontends.base import LanguageFrontend
from codectx.frontends.cpp_treesitter import CppTreeSitterFrontend

CPP_SOURCE = b"""#include <vector>
#include "payment/gateway.h"

namespace acme::payments {
struct Receipt { int id; };

class PaymentService {
public:
    PaymentService();
    ~PaymentService();
    bool authorize(const std::string& user);
private:
    Gateway gateway_;
};

int helper(int count) { return count; }
}
"""
CPP_PATH = "src/payment.cpp"


def test_cpp_frontend_satisfies_language_frontend_protocol() -> None:
    frontend: LanguageFrontend = CppTreeSitterFrontend()

    assert frontend.language == "cpp"


def test_cpp_frontend_parses_valid_source_without_diagnostics() -> None:
    frontend = CppTreeSitterFrontend()

    facts = frontend.extract("src/foo.cpp", b"int main() { return 0; }\n")

    assert facts.diagnostics == []
    assert {node.symbol_key for node in facts.nodes} == {
        "cpp:src/foo.cpp#main()",
    }


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


def test_cpp_frontend_records_fallback_diagnostic_when_errors_are_not_located(
    monkeypatch,
) -> None:
    frontend = CppTreeSitterFrontend()
    monkeypatch.setattr(cpp_treesitter, "error_nodes", lambda _root: iter(()))

    facts = frontend.extract("src/foo.cpp", b"int main( {")

    assert len(facts.diagnostics) == 1
    assert facts.diagnostics[0].code == "parse_error"


def test_cpp_frontend_extracts_definition_nodes() -> None:
    frontend = CppTreeSitterFrontend()

    facts = frontend.extract(CPP_PATH, CPP_SOURCE)

    nodes = {node.symbol_key: node for node in facts.nodes}
    assert set(nodes) == {
        f"cpp:{CPP_PATH}#acme::payments",
        f"cpp:{CPP_PATH}#acme::payments::Receipt",
        f"cpp:{CPP_PATH}#acme::payments::Receipt::id",
        f"cpp:{CPP_PATH}#acme::payments::PaymentService",
        f"cpp:{CPP_PATH}#acme::payments::PaymentService::PaymentService()",
        f"cpp:{CPP_PATH}#acme::payments::PaymentService::~PaymentService()",
        f"cpp:{CPP_PATH}#acme::payments::PaymentService::authorize(conststd::string&)",
        f"cpp:{CPP_PATH}#acme::payments::PaymentService::gateway_",
        f"cpp:{CPP_PATH}#acme::payments::helper(int)",
    }
    namespace = nodes[f"cpp:{CPP_PATH}#acme::payments"]
    assert namespace.kind == "namespace"
    assert namespace.span is not None
    assert namespace.span.start_line == 4
    assert namespace.span.end_line == 17
    service = nodes[f"cpp:{CPP_PATH}#acme::payments::PaymentService"]
    assert service.kind == "type"
    assert service.metadata == {"declaration_kind": "class_specifier"}
    assert service.span.start_line == 7
    assert service.span.end_line == 14
    assert nodes[f"cpp:{CPP_PATH}#acme::payments::PaymentService::gateway_"].kind == (
        "field"
    )


def test_cpp_frontend_extracts_includes_and_containment_edges() -> None:
    frontend = CppTreeSitterFrontend()

    facts = frontend.extract(CPP_PATH, CPP_SOURCE)

    include_edges = [edge for edge in facts.edges if edge.kind == "includes"]
    assert [edge.unresolved_dst for edge in include_edges] == [
        "<vector>",
        "payment/gateway.h",
    ]
    include_occurrences = [
        occurrence for occurrence in facts.occurrences if occurrence.role == "include"
    ]
    assert [
        _span_text(CPP_SOURCE, occurrence.span) for occurrence in include_occurrences
    ] == ["<vector>", "payment/gateway.h"]

    contains_edges = [edge for edge in facts.edges if edge.kind == "contains"]
    assert {
        (edge.src_key, edge.dst_key)
        for edge in contains_edges
        if edge.dst_key is not None
    } >= {
        (
            f"cpp:{CPP_PATH}#acme::payments",
            f"cpp:{CPP_PATH}#acme::payments::Receipt",
        ),
        (
            f"cpp:{CPP_PATH}#acme::payments",
            f"cpp:{CPP_PATH}#acme::payments::PaymentService",
        ),
        (
            f"cpp:{CPP_PATH}#acme::payments::PaymentService",
            f"cpp:{CPP_PATH}#acme::payments::PaymentService::authorize(conststd::string&)",
        ),
        (
            f"cpp:{CPP_PATH}#acme::payments",
            f"cpp:{CPP_PATH}#acme::payments::helper(int)",
        ),
    }


def test_cpp_frontend_extracts_occurrences_and_chunks() -> None:
    frontend = CppTreeSitterFrontend()

    facts = frontend.extract(CPP_PATH, CPP_SOURCE)

    definition_occurrences = [
        occurrence
        for occurrence in facts.occurrences
        if occurrence.role == "definition"
    ]
    assert {
        (occurrence.text, occurrence.span.start_line)
        for occurrence in definition_occurrences
    } >= {
        ("acme::payments", 4),
        ("Receipt", 5),
        ("id", 5),
        ("PaymentService", 7),
        ("authorize", 11),
        ("gateway_", 13),
        ("helper", 16),
    }

    chunks = {chunk.node_key: chunk for chunk in facts.chunks}
    service_chunk = chunks[f"cpp:{CPP_PATH}#acme::payments::PaymentService"]
    assert service_chunk.start_line == 7
    assert service_chunk.end_line == 14
    assert service_chunk.text.startswith("class PaymentService")
    helper_chunk = chunks[f"cpp:{CPP_PATH}#acme::payments::helper(int)"]
    assert helper_chunk.start_line == 16
    assert helper_chunk.end_line == 16
    assert "int helper(int count)" in helper_chunk.text


def test_cpp_frontend_uses_signatures_for_overloaded_callables() -> None:
    frontend = CppTreeSitterFrontend()

    facts = frontend.extract(
        "src/foo.cpp",
        b"class Foo { void bar(); void bar(const std::string& value); "
        b"void bar(int* value); };\n",
    )

    assert {node.symbol_key for node in facts.nodes if node.kind == "callable"} == {
        "cpp:src/foo.cpp#Foo::bar()",
        "cpp:src/foo.cpp#Foo::bar(conststd::string&)",
        "cpp:src/foo.cpp#Foo::bar(int*)",
    }


def test_cpp_frontend_extracts_nested_namespaces_enums_and_out_of_line_methods() -> (
    None
):
    frontend = CppTreeSitterFrontend()

    facts = frontend.extract(
        "src/extra.cpp",
        b"void header_decl(int count);\n"
        b"namespace acme {\n"
        b"void namespace_decl();\n"
        b"namespace detail { enum Color { Red }; }\n"
        b"class Service { void run(); void ptr(int*); void inline_run() {} };\n"
        b"void Service::run() {}\n"
        b"}\n",
    )

    nodes = {node.symbol_key: node for node in facts.nodes}
    assert set(nodes) == {
        "cpp:src/extra.cpp#header_decl(int)",
        "cpp:src/extra.cpp#acme",
        "cpp:src/extra.cpp#acme::namespace_decl()",
        "cpp:src/extra.cpp#acme::detail",
        "cpp:src/extra.cpp#acme::detail::Color",
        "cpp:src/extra.cpp#acme::Service",
        "cpp:src/extra.cpp#acme::Service::run()",
        "cpp:src/extra.cpp#acme::Service::ptr(int*)",
        "cpp:src/extra.cpp#acme::Service::inline_run()",
    }
    assert nodes["cpp:src/extra.cpp#acme::detail::Color"].metadata == {
        "declaration_kind": "enum_specifier"
    }
    assert {
        (edge.src_key, edge.dst_key) for edge in facts.edges if edge.kind == "contains"
    } >= {
        ("cpp:src/extra.cpp#acme", "cpp:src/extra.cpp#acme::detail"),
        (
            "cpp:src/extra.cpp#acme::detail",
            "cpp:src/extra.cpp#acme::detail::Color",
        ),
    }
    run_chunks = [
        chunk
        for chunk in facts.chunks
        if chunk.node_key == "cpp:src/extra.cpp#acme::Service::run()"
    ]
    assert len(run_chunks) == 2
    assert any("void run();" in chunk.text for chunk in run_chunks)
    assert any("void Service::run() {}" in chunk.text for chunk in run_chunks)


def _span_text(source: bytes, span) -> str:
    return source[span.start_byte : span.end_byte].decode("utf-8")
