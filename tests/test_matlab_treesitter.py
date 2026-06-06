from __future__ import annotations

from codectx.frontends.matlab_treesitter import MatlabTreeSitterFrontend

MATLAB_CLASS_SOURCE = b"""
classdef PaymentService < handle
    properties
        Gateway
        Timeout = 30
    end
    methods
        function obj = PaymentService(gateway)
            obj.Gateway = gateway;
        end
        function ok = authorize(obj, request)
            validate(request);
            ok = obj.Gateway.charge(request);
        end
        function validate(obj, request)
            if isempty(request)
                error("request");
            end
        end
    end
end
"""


def test_matlab_frontend_extracts_class_methods_properties_and_chunks() -> None:
    facts = MatlabTreeSitterFrontend().extract(
        "src/PaymentService.m", MATLAB_CLASS_SOURCE
    )

    symbols = {node.symbol_key for node in facts.nodes}
    assert "matlab:src/PaymentService.m#PaymentService" in symbols
    assert "matlab:src/PaymentService.m#PaymentService.Gateway" in symbols
    assert "matlab:src/PaymentService.m#PaymentService.Timeout" in symbols
    assert (
        "matlab:src/PaymentService.m#PaymentService.authorize(obj,request)" in symbols
    )
    assert "matlab:src/PaymentService.m#PaymentService.validate(obj,request)" in symbols
    assert any(chunk.node_key in symbols for chunk in facts.chunks)
    assert not facts.diagnostics


def test_matlab_frontend_extracts_edges_and_calls() -> None:
    facts = MatlabTreeSitterFrontend().extract(
        "src/PaymentService.m", MATLAB_CLASS_SOURCE
    )

    contains_edges = {
        (edge.src_key, edge.dst_key) for edge in facts.edges if edge.kind == "contains"
    }
    assert (
        "matlab:src/PaymentService.m#PaymentService",
        "matlab:src/PaymentService.m#PaymentService.authorize(obj,request)",
    ) in contains_edges
    assert any(
        edge.kind == "uses_type" and edge.unresolved_dst == "handle"
        for edge in facts.edges
    )
    calls = {
        occurrence.text: occurrence
        for occurrence in facts.occurrences
        if occurrence.role == "call"
    }
    assert (
        calls["validate"].resolved_key
        == "matlab:src/PaymentService.m#PaymentService.validate(obj,request)"
    )
    assert calls["obj.Gateway.charge"].resolved_key is None
    assert calls["isempty"].resolved_key is None


def test_matlab_frontend_extracts_top_level_functions() -> None:
    facts = MatlabTreeSitterFrontend().extract(
        "src/authorize.m",
        b"""
function ok = authorize(request, gateway)
validate(request);
ok = gateway.charge(request);
end

function validate(request)
ok = isempty(request);
end
""",
    )

    symbols = {node.symbol_key for node in facts.nodes}
    assert "matlab:src/authorize.m#authorize(request,gateway)" in symbols
    assert "matlab:src/authorize.m#validate(request)" in symbols
    calls = {
        occurrence.text: occurrence
        for occurrence in facts.occurrences
        if occurrence.role == "call"
    }
    assert calls["validate"].resolved_key == "matlab:src/authorize.m#validate(request)"


def test_matlab_frontend_records_constructor_type_references() -> None:
    facts = MatlabTreeSitterFrontend().extract(
        "src/makeRequest.m",
        b"""
classdef PaymentRequest
end

function request = makeRequest()
request = PaymentRequest();
end
""",
    )

    symbols = {node.symbol_key for node in facts.nodes}
    assert "matlab:src/makeRequest.m#PaymentRequest" in symbols
    assert "matlab:src/makeRequest.m#makeRequest()" in symbols
    assert any(
        edge.kind == "uses_type"
        and edge.dst_key == "matlab:src/makeRequest.m#PaymentRequest"
        for edge in facts.edges
    )


def test_matlab_frontend_emits_source_chunk_for_symbol_poor_scripts() -> None:
    facts = MatlabTreeSitterFrontend().extract(
        "scripts/run_payment.m",
        b"""
gateway = PaymentGateway();
request = PaymentRequest("u1", 42);
ok = authorize(request, gateway);
disp(ok);
""",
    )

    assert facts.nodes == []
    assert len(facts.chunks) == 1
    assert facts.chunks[0].kind == "source"
    assert "authorize(request, gateway)" in facts.chunks[0].text
    assert {edge.unresolved_dst for edge in facts.edges if edge.kind == "calls"} == {
        "PaymentGateway",
        "PaymentRequest",
        "authorize",
        "disp",
    }


def test_matlab_frontend_extracts_import_commands() -> None:
    facts = MatlabTreeSitterFrontend().extract(
        "scripts/run_imported.m",
        b"""
import finance.PaymentGateway
gateway = PaymentGateway();
disp(gateway);
""",
    )

    import_edges = {
        edge.unresolved_dst for edge in facts.edges if edge.kind == "imports"
    }
    assert import_edges == {"finance.PaymentGateway"}
    assert any(
        occurrence.role == "import" and occurrence.text == "finance.PaymentGateway"
        for occurrence in facts.occurrences
    )


def test_matlab_frontend_preserves_script_context_with_local_functions() -> None:
    facts = MatlabTreeSitterFrontend().extract(
        "scripts/run_payment.m",
        b"""
gateway = PaymentGateway();
result = runPayment(gateway);

function result = runPayment(gateway)
result = disp(gateway);
end
""",
    )

    symbols = {node.symbol_key for node in facts.nodes}
    assert "matlab:scripts/run_payment.m#runPayment(gateway)" in symbols
    source_chunks = [chunk for chunk in facts.chunks if chunk.kind == "source"]
    assert len(source_chunks) == 1
    assert "PaymentGateway()" in source_chunks[0].text
    assert "function result = runPayment" not in source_chunks[0].text
    assert any(
        edge.kind == "calls" and edge.unresolved_dst == "PaymentGateway"
        for edge in facts.edges
    )


def test_matlab_frontend_records_parser_diagnostics() -> None:
    facts = MatlabTreeSitterFrontend().extract(
        "src/broken.m", b"function x = broken(\n"
    )

    assert facts.diagnostics
    assert facts.diagnostics[0].message.startswith("MATLAB parse error")
