from __future__ import annotations

import codectx.frontends.java_treesitter as java_treesitter
from codectx.frontends.base import LanguageFrontend
from codectx.frontends.java_treesitter import JavaTreeSitterFrontend

JAVA_SOURCE = b"""package com.acme.payments;

import java.util.List;
import static java.util.Collections.emptyList;

public class PaymentService {
    private Gateway gateway;

    public PaymentService(Gateway gateway) {
        this.gateway = gateway;
    }

    public List<String> authorize(String user) {
        return emptyList();
    }
}
"""
JAVA_PATH = "src/main/java/com/acme/payments/PaymentService.java"


def test_java_frontend_satisfies_language_frontend_protocol() -> None:
    frontend: LanguageFrontend = JavaTreeSitterFrontend()

    assert frontend.language == "java"


def test_java_frontend_parses_valid_source_without_diagnostics() -> None:
    frontend = JavaTreeSitterFrontend()

    facts = frontend.extract("src/Foo.java", b"class Foo { void bar() {} }\n")

    assert facts.diagnostics == []
    assert {node.name for node in facts.nodes} == {"Foo", "bar"}
    assert {node.symbol_key for node in facts.nodes} == {
        "java:src/Foo.java#Foo",
        "java:src/Foo.java#Foo.bar()",
    }


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


def test_java_frontend_records_fallback_diagnostic_when_errors_are_not_located(
    monkeypatch,
) -> None:
    frontend = JavaTreeSitterFrontend()
    monkeypatch.setattr(java_treesitter, "error_nodes", lambda _root: iter(()))

    facts = frontend.extract("src/Foo.java", b"class Foo {")

    assert len(facts.diagnostics) == 1
    assert facts.diagnostics[0].code == "parse_error"


def test_java_frontend_extracts_definition_nodes() -> None:
    frontend = JavaTreeSitterFrontend()

    facts = frontend.extract(JAVA_PATH, JAVA_SOURCE)

    nodes = {node.symbol_key: node for node in facts.nodes}
    assert set(nodes) == {
        f"java:{JAVA_PATH}#PaymentService",
        f"java:{JAVA_PATH}#PaymentService.gateway",
        f"java:{JAVA_PATH}#PaymentService.<init>(Gateway)",
        f"java:{JAVA_PATH}#PaymentService.authorize(String)",
    }
    service = nodes[f"java:{JAVA_PATH}#PaymentService"]
    assert service.kind == "type"
    assert service.qualified_name == "com.acme.payments.PaymentService"
    assert service.span is not None
    assert service.span.start_line == 6
    assert service.span.end_line == 16
    assert service.metadata == {
        "declaration_kind": "class_declaration",
        "package": "com.acme.payments",
    }
    assert nodes[f"java:{JAVA_PATH}#PaymentService.gateway"].kind == "field"
    assert nodes[f"java:{JAVA_PATH}#PaymentService.<init>(Gateway)"].qualified_name == (
        "com.acme.payments.PaymentService.<init>(Gateway)"
    )
    assert (
        nodes[f"java:{JAVA_PATH}#PaymentService.authorize(String)"].span.start_line
        == 13
    )


def test_java_frontend_handles_single_segment_package_and_type_variants() -> None:
    frontend = JavaTreeSitterFrontend()
    source = b"""package acme;

public interface Gateway {
    Result authorize();

    enum Result { APPROVED }
}

record Receipt(String id) {}
"""

    facts = frontend.extract("src/Gateway.java", source)

    nodes = {node.symbol_key: node for node in facts.nodes}
    assert nodes["java:src/Gateway.java#Gateway"].qualified_name == "acme.Gateway"
    assert nodes["java:src/Gateway.java#Gateway.authorize()"].kind == "callable"
    assert nodes["java:src/Gateway.java#Gateway.Result"].metadata == {
        "declaration_kind": "enum_declaration",
        "package": "acme",
    }
    assert nodes["java:src/Gateway.java#Receipt"].metadata == {
        "declaration_kind": "record_declaration",
        "package": "acme",
    }
    assert (
        "java:src/Gateway.java#Gateway",
        "java:src/Gateway.java#Gateway.Result",
    ) in {
        (edge.src_key, edge.dst_key) for edge in facts.edges if edge.kind == "contains"
    }


def test_java_frontend_extracts_imports_and_containment_edges() -> None:
    frontend = JavaTreeSitterFrontend()

    facts = frontend.extract(JAVA_PATH, JAVA_SOURCE)

    import_edges = [edge for edge in facts.edges if edge.kind == "imports"]
    assert [(edge.unresolved_dst, edge.metadata) for edge in import_edges] == [
        ("java.util.List", {"static": False}),
        ("java.util.Collections.emptyList", {"static": True}),
    ]
    contains_edges = [edge for edge in facts.edges if edge.kind == "contains"]
    assert {(edge.src_key, edge.dst_key) for edge in contains_edges} == {
        (
            f"java:{JAVA_PATH}#PaymentService",
            f"java:{JAVA_PATH}#PaymentService.gateway",
        ),
        (
            f"java:{JAVA_PATH}#PaymentService",
            f"java:{JAVA_PATH}#PaymentService.<init>(Gateway)",
        ),
        (
            f"java:{JAVA_PATH}#PaymentService",
            f"java:{JAVA_PATH}#PaymentService.authorize(String)",
        ),
    }


def test_java_frontend_preserves_wildcard_import_text() -> None:
    frontend = JavaTreeSitterFrontend()

    facts = frontend.extract(
        "src/Foo.java",
        b"import static java.util.Collections.*;\nclass Foo {}\n",
    )

    import_edge = next(edge for edge in facts.edges if edge.kind == "imports")
    assert import_edge.unresolved_dst == "java.util.Collections.*"
    assert import_edge.metadata == {"static": True}
    import_occurrence = next(
        occurrence for occurrence in facts.occurrences if occurrence.role == "import"
    )
    assert (
        _span_text(
            b"import static java.util.Collections.*;\nclass Foo {}\n",
            import_occurrence.span,
        )
        == "java.util.Collections.*"
    )


def test_java_frontend_uses_signatures_for_overloaded_callables() -> None:
    frontend = JavaTreeSitterFrontend()

    facts = frontend.extract(
        "src/Foo.java",
        b"class Foo { void bar() {} void bar(String value) {} "
        b"void bar(int value) {} void bar(String... values) {} }\n",
    )

    assert {node.symbol_key for node in facts.nodes if node.kind == "callable"} == {
        "java:src/Foo.java#Foo.bar()",
        "java:src/Foo.java#Foo.bar(String)",
        "java:src/Foo.java#Foo.bar(int)",
        "java:src/Foo.java#Foo.bar(String...)",
    }


def test_java_frontend_extracts_occurrences_and_chunks() -> None:
    frontend = JavaTreeSitterFrontend()

    facts = frontend.extract(JAVA_PATH, JAVA_SOURCE)

    definition_occurrences = [
        occurrence
        for occurrence in facts.occurrences
        if occurrence.role == "definition"
    ]
    assert {
        (occurrence.text, occurrence.span.start_line)
        for occurrence in definition_occurrences
    } == {
        ("PaymentService", 6),
        ("gateway", 7),
        ("PaymentService", 9),
        ("authorize", 13),
    }
    import_occurrences = [
        occurrence for occurrence in facts.occurrences if occurrence.role == "import"
    ]
    assert [occurrence.text for occurrence in import_occurrences] == [
        "java.util.List",
        "java.util.Collections.emptyList",
    ]

    chunks = {chunk.node_key: chunk for chunk in facts.chunks}
    service_chunk = chunks[f"java:{JAVA_PATH}#PaymentService"]
    assert service_chunk.start_line == 6
    assert service_chunk.end_line == 16
    assert service_chunk.text.startswith("public class PaymentService")
    method_chunk = chunks[f"java:{JAVA_PATH}#PaymentService.authorize(String)"]
    assert method_chunk.start_line == 13
    assert method_chunk.end_line == 15
    assert "public List<String> authorize" in method_chunk.text


def test_java_frontend_extracts_call_like_occurrences_and_edges() -> None:
    frontend = JavaTreeSitterFrontend()
    source = b"""class PaymentService {
    boolean authorize(User user) {
        validate(user);
        this.audit();
        new Receipt();
        return gateway.charge(user);
    }

    void validate(User user) {}
    void audit() {}
}
class Receipt {}
"""

    facts = frontend.extract("src/PaymentService.java", source)

    call_occurrences = [
        occurrence for occurrence in facts.occurrences if occurrence.role == "call"
    ]
    assert [
        (occurrence.text, occurrence.resolved_key) for occurrence in call_occurrences
    ] == [
        (
            "validate",
            "java:src/PaymentService.java#PaymentService.validate(User)",
        ),
        ("audit", "java:src/PaymentService.java#PaymentService.audit()"),
        ("Receipt", None),
        ("gateway.charge", None),
    ]
    assert {
        (occurrence.node_key, occurrence.span.start_line)
        for occurrence in call_occurrences
    } == {
        ("java:src/PaymentService.java#PaymentService.authorize(User)", 3),
        ("java:src/PaymentService.java#PaymentService.authorize(User)", 4),
        ("java:src/PaymentService.java#PaymentService.authorize(User)", 5),
        ("java:src/PaymentService.java#PaymentService.authorize(User)", 6),
    }

    call_edges = [edge for edge in facts.edges if edge.kind == "calls"]
    assert [(edge.dst_key, edge.unresolved_dst) for edge in call_edges] == [
        ("java:src/PaymentService.java#PaymentService.validate(User)", None),
        ("java:src/PaymentService.java#PaymentService.audit()", None),
        (None, "Receipt"),
        (None, "gateway.charge"),
    ]
    assert [edge.metadata["argument_count"] for edge in call_edges] == [1, 0, 0, 1]


def test_java_frontend_leaves_ambiguous_same_class_calls_unresolved() -> None:
    frontend = JavaTreeSitterFrontend()
    source = b"""class Foo {
    void target() {
        overloaded(value);
    }
    void overloaded(String value) {}
    void overloaded(Integer value) {}
}
"""

    facts = frontend.extract("src/Foo.java", source)

    call_edge = next(edge for edge in facts.edges if edge.kind == "calls")
    assert call_edge.dst_key is None
    assert call_edge.unresolved_dst == "overloaded"
    assert call_edge.confidence == 0.45

    call_occurrence = next(
        occurrence for occurrence in facts.occurrences if occurrence.role == "call"
    )
    assert call_occurrence.resolved_key is None
    assert call_occurrence.metadata == {
        "argument_count": 1,
        "call_kind": "method_invocation",
    }


def test_java_frontend_extracts_type_and_field_references() -> None:
    frontend = JavaTreeSitterFrontend()
    source = b"""class PaymentService {
    private Gateway gateway;
    Receipt authorize(User user) {
        this.gateway = gateway;
        return new Receipt();
    }
}
class Gateway {}
class Receipt {}
class User {}
"""

    facts = frontend.extract("src/PaymentService.java", source)

    type_occurrences = [
        occurrence
        for occurrence in facts.occurrences
        if occurrence.role == "type_reference"
    ]
    assert [
        (occurrence.text, occurrence.node_key, occurrence.span.start_line)
        for occurrence in type_occurrences
    ] == [
        ("Gateway", "java:src/PaymentService.java#PaymentService.gateway", 2),
        ("Receipt", "java:src/PaymentService.java#PaymentService.authorize(User)", 3),
        ("User", "java:src/PaymentService.java#PaymentService.authorize(User)", 3),
        ("Receipt", "java:src/PaymentService.java#PaymentService.authorize(User)", 5),
    ]

    field_occurrence = next(
        occurrence
        for occurrence in facts.occurrences
        if occurrence.role == "field_reference"
    )
    assert field_occurrence.text == "gateway"
    assert field_occurrence.resolved_key == (
        "java:src/PaymentService.java#PaymentService.gateway"
    )

    assert {
        (edge.kind, edge.dst_key, edge.unresolved_dst)
        for edge in facts.edges
        if edge.kind in {"references", "uses_type"}
    } >= {
        ("uses_type", None, "Gateway"),
        ("uses_type", None, "Receipt"),
        ("uses_type", None, "User"),
        (
            "references",
            "java:src/PaymentService.java#PaymentService.gateway",
            None,
        ),
    }


def test_java_frontend_does_not_resolve_qualified_field_receiver_as_this() -> None:
    frontend = JavaTreeSitterFrontend()
    source = b"""class PaymentService {
    private Gateway gateway;
    void copy(PaymentService other) {
        other.gateway.connect();
        this.gateway.connect();
    }
}
class Gateway { void connect() {} }
"""

    facts = frontend.extract("src/PaymentService.java", source)

    field_occurrences = [
        occurrence
        for occurrence in facts.occurrences
        if occurrence.role == "field_reference"
    ]
    assert [
        (occurrence.text, occurrence.resolved_key) for occurrence in field_occurrences
    ] == [
        ("gateway", None),
        ("gateway", "java:src/PaymentService.java#PaymentService.gateway"),
    ]


def _span_text(source: bytes, span) -> str:
    return source[span.start_byte : span.end_byte].decode("utf-8")
