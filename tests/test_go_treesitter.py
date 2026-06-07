from __future__ import annotations

from codectx.frontends.go_treesitter import GoTreeSitterFrontend

GO_SOURCE = b"""
package payments

import (
    "context"
    gateway "acme/payments/gateway"
)

type PaymentService struct {
    Gateway gateway.Client
    Timeout int
}

type Authorizer interface {
    Authorize(ctx context.Context, request PaymentRequest) (Receipt, error)
}

type PaymentRequest struct {
    Amount int
}

type Receipt = gateway.Receipt

func NewPaymentService(gateway gateway.Client) *PaymentService {
    return &PaymentService{Gateway: gateway}
}

func (s *PaymentService) Authorize(ctx context.Context, request PaymentRequest) (Receipt, error) {
    if request.Amount <= 0 {
        return Receipt{}, errors.New("bad")
    }
    s.validate(request)
    return s.Gateway.Charge(ctx, request)
}

func (s *PaymentService) validate(request PaymentRequest) error {
    return nil
}
"""


def test_go_frontend_extracts_package_types_callables_fields_and_chunks() -> None:
    facts = GoTreeSitterFrontend().extract("service.go", GO_SOURCE)

    symbols = {node.symbol_key for node in facts.nodes}
    assert "go:service.go#payments" in symbols
    assert "go:service.go#PaymentService" in symbols
    assert "go:service.go#PaymentService.Gateway" in symbols
    assert "go:service.go#PaymentService.Timeout" in symbols
    assert "go:service.go#Authorizer" in symbols
    assert (
        "go:service.go#Authorizer.Authorize(context.Context,PaymentRequest)" in symbols
    )
    assert "go:service.go#PaymentRequest" in symbols
    assert "go:service.go#Receipt" in symbols
    assert "go:service.go#NewPaymentService(gateway.Client)" in symbols
    assert (
        "go:service.go#PaymentService.Authorize(context.Context,PaymentRequest)"
        in symbols
    )
    assert "go:service.go#PaymentService.validate(PaymentRequest)" in symbols
    assert any(chunk.node_key in symbols for chunk in facts.chunks)
    assert not facts.diagnostics


def test_go_frontend_extracts_edges_imports_calls_and_type_references() -> None:
    facts = GoTreeSitterFrontend().extract("service.go", GO_SOURCE)

    imports = {edge.unresolved_dst for edge in facts.edges if edge.kind == "imports"}
    assert imports == {"context", "acme/payments/gateway"}

    contains = {
        (edge.src_key, edge.dst_key) for edge in facts.edges if edge.kind == "contains"
    }
    assert ("go:service.go#payments", "go:service.go#PaymentService") in contains
    assert (
        "go:service.go#PaymentService",
        "go:service.go#PaymentService.Authorize(context.Context,PaymentRequest)",
    ) in contains

    calls = {
        occurrence.text: occurrence
        for occurrence in facts.occurrences
        if occurrence.role == "call"
    }
    assert (
        calls["s.validate"].resolved_key
        == "go:service.go#PaymentService.validate(PaymentRequest)"
    )
    assert calls["s.Gateway.Charge"].resolved_key is None
    assert calls["errors.New"].resolved_key is None
    assert any(
        edge.kind == "uses_type" and edge.dst_key == "go:service.go#PaymentRequest"
        for edge in facts.edges
    )
    assert any(
        edge.kind == "uses_type" and edge.unresolved_dst == "gateway.Client"
        for edge in facts.edges
    )


def test_go_frontend_handles_grouped_parameters_and_constructor_literals() -> None:
    facts = GoTreeSitterFrontend().extract(
        "factory.go",
        b"""
package payments

type Request struct {}

func newRequest(first, second string) Request {
    return Request{}
}
""",
    )

    symbols = {node.symbol_key for node in facts.nodes}
    assert "go:factory.go#newRequest(string,string)" in symbols
    assert any(
        edge.kind == "uses_type" and edge.dst_key == "go:factory.go#Request"
        for edge in facts.edges
    )


def test_go_frontend_handles_package_less_snippets_and_named_type_conversions() -> None:
    facts = GoTreeSitterFrontend().extract(
        "scratch.go",
        b"""
type Amount int

func helper() {}

func parse(raw int) Amount {
    helper()
    return Amount(raw)
}
""",
    )

    symbols = {node.symbol_key for node in facts.nodes}
    assert "go:scratch.go#Amount" in symbols
    assert "go:scratch.go#helper()" in symbols
    assert "go:scratch.go#parse(int)" in symbols
    assert "go:scratch.go#scratch" not in symbols

    calls = {
        occurrence.text: occurrence
        for occurrence in facts.occurrences
        if occurrence.role == "call"
    }
    assert calls["helper"].resolved_key == "go:scratch.go#helper()"
    assert calls["Amount"].resolved_key is None
    assert any(
        occurrence.role == "type_reference"
        and occurrence.text == "Amount"
        and occurrence.resolved_key == "go:scratch.go#Amount"
        and occurrence.metadata["reference_kind"] == "constructor_call"
        for occurrence in facts.occurrences
    )
    assert not any(edge.kind == "contains" for edge in facts.edges)


def test_go_frontend_extracts_unnamed_receivers_and_embedded_fields() -> None:
    facts = GoTreeSitterFrontend().extract(
        "embedded.go",
        b"""
package payments

type Base struct {}
type Logger struct {}

type Service struct {
    Base
    *Logger
    Named string
}

func (Service) Value() {}
func (*Service) Pointer() {}
""",
    )

    symbols = {node.symbol_key for node in facts.nodes}
    assert "go:embedded.go#Service.Base" in symbols
    assert "go:embedded.go#Service.Logger" in symbols
    assert "go:embedded.go#Service.Named" in symbols
    assert "go:embedded.go#Service.Value()" in symbols
    assert "go:embedded.go#Service.Pointer()" in symbols

    contains = {
        (edge.src_key, edge.dst_key) for edge in facts.edges if edge.kind == "contains"
    }
    assert ("go:embedded.go#Service", "go:embedded.go#Service.Value()") in contains
    assert ("go:embedded.go#Service", "go:embedded.go#Service.Pointer()") in contains


def test_go_frontend_records_parser_diagnostics() -> None:
    facts = GoTreeSitterFrontend().extract("broken.go", b"package broken\nfunc {\n")

    assert facts.diagnostics
    assert facts.diagnostics[0].message.startswith("Go parse error")
