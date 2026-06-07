from __future__ import annotations

from codectx.frontends.rust_treesitter import RustTreeSitterFrontend

RUST_SOURCE = b"""
pub mod gateway;
use crate::gateway::{Gateway, Receipt};
use std::fmt::Debug;

pub struct PaymentService {
    gateway: Gateway,
    retries: u32,
}

pub enum PaymentError {
    Declined(String),
    Timeout,
}

pub trait Authorizer {
    fn authorize(&self, request: PaymentRequest) -> Result<Receipt, PaymentError>;
}

pub struct PaymentRequest {
    amount: u32,
}

type PaymentResult = Result<Receipt, PaymentError>;

impl PaymentService {
    pub fn new(gateway: Gateway) -> Self {
        Self { gateway, retries: 3 }
    }

    pub fn authorize(&self, request: PaymentRequest) -> PaymentResult {
        self.validate(&request);
        charge_gateway(&self.gateway, request)
    }

    fn validate(&self, request: &PaymentRequest) {
        log::debug!("validating");
    }
}

fn charge_gateway(gateway: &Gateway, request: PaymentRequest) -> PaymentResult {
    todo!()
}
"""


def test_rust_frontend_extracts_modules_types_callables_fields_and_chunks() -> None:
    facts = RustTreeSitterFrontend().extract("src/lib.rs", RUST_SOURCE)

    symbols = {node.symbol_key for node in facts.nodes}
    assert "rust:src/lib.rs#gateway" in symbols
    assert "rust:src/lib.rs#PaymentService" in symbols
    assert "rust:src/lib.rs#PaymentService.gateway" in symbols
    assert "rust:src/lib.rs#PaymentService.retries" in symbols
    assert "rust:src/lib.rs#PaymentError" in symbols
    assert "rust:src/lib.rs#PaymentError.Declined" in symbols
    assert "rust:src/lib.rs#PaymentError.Timeout" in symbols
    assert "rust:src/lib.rs#Authorizer" in symbols
    assert "rust:src/lib.rs#Authorizer.authorize(&self,PaymentRequest)" in symbols
    assert "rust:src/lib.rs#PaymentRequest" in symbols
    assert "rust:src/lib.rs#PaymentResult" in symbols
    assert "rust:src/lib.rs#PaymentService.new(Gateway)" in symbols
    assert "rust:src/lib.rs#PaymentService.authorize(&self,PaymentRequest)" in symbols
    assert "rust:src/lib.rs#PaymentService.validate(&self,&PaymentRequest)" in symbols
    assert "rust:src/lib.rs#charge_gateway(&Gateway,PaymentRequest)" in symbols
    assert any(chunk.node_key in symbols for chunk in facts.chunks)
    assert not facts.diagnostics


def test_rust_frontend_extracts_edges_imports_calls_macros_and_type_references() -> (
    None
):
    facts = RustTreeSitterFrontend().extract("src/lib.rs", RUST_SOURCE)

    imports = {edge.unresolved_dst for edge in facts.edges if edge.kind == "imports"}
    assert imports == {"crate::gateway::{Gateway, Receipt}", "std::fmt::Debug"}

    contains = {
        (edge.src_key, edge.dst_key) for edge in facts.edges if edge.kind == "contains"
    }
    assert (
        "rust:src/lib.rs#PaymentService",
        "rust:src/lib.rs#PaymentService.authorize(&self,PaymentRequest)",
    ) in contains
    assert (
        "rust:src/lib.rs#Authorizer",
        "rust:src/lib.rs#Authorizer.authorize(&self,PaymentRequest)",
    ) in contains

    calls = {
        occurrence.text: occurrence
        for occurrence in facts.occurrences
        if occurrence.role == "call"
    }
    assert (
        calls["self.validate"].resolved_key
        == "rust:src/lib.rs#PaymentService.validate(&self,&PaymentRequest)"
    )
    assert (
        calls["charge_gateway"].resolved_key
        == "rust:src/lib.rs#charge_gateway(&Gateway,PaymentRequest)"
    )
    assert calls["log::debug"].resolved_key is None
    assert calls["log::debug"].metadata["call_kind"] == "macro_invocation"
    assert calls["todo"].metadata["call_kind"] == "macro_invocation"
    assert any(
        edge.kind == "uses_type" and edge.dst_key == "rust:src/lib.rs#PaymentRequest"
        for edge in facts.edges
    )
    assert any(
        edge.kind == "uses_type" and edge.unresolved_dst == "Receipt"
        for edge in facts.edges
    )


def test_rust_frontend_handles_free_functions_and_macro_heavy_code() -> None:
    facts = RustTreeSitterFrontend().extract(
        "src/macros.rs",
        b"""
fn helper() {}

fn run() {
    helper();
    println!("running");
}
""",
    )

    calls = {
        occurrence.text: occurrence
        for occurrence in facts.occurrences
        if occurrence.role == "call"
    }
    assert calls["helper"].resolved_key == "rust:src/macros.rs#helper()"
    assert calls["println"].resolved_key is None
    assert calls["println"].confidence == 0.35


def test_rust_frontend_handles_trait_impls_inline_modules_and_tuple_structs() -> None:
    facts = RustTreeSitterFrontend().extract(
        "src/payments.rs",
        b"""
mod nested {
    pub struct NestedService;

    fn helper() {}
}

pub struct UserId(String, u64);
pub struct Service;

trait Authorizer {
    fn authorize(&self);
}

impl Authorizer for Service {
    fn authorize(&self) {}
}
""",
    )

    symbols = {node.symbol_key for node in facts.nodes}
    assert "rust:src/payments.rs#nested" in symbols
    assert "rust:src/payments.rs#NestedService" in symbols
    assert "rust:src/payments.rs#helper()" in symbols
    assert "rust:src/payments.rs#UserId" in symbols
    assert "rust:src/payments.rs#UserId.0" in symbols
    assert "rust:src/payments.rs#UserId.1" in symbols
    assert "rust:src/payments.rs#Authorizer.authorize(&self)" in symbols
    assert "rust:src/payments.rs#Service.authorize(&self)" in symbols

    contains = {
        (edge.src_key, edge.dst_key) for edge in facts.edges if edge.kind == "contains"
    }
    assert (
        "rust:src/payments.rs#Service",
        "rust:src/payments.rs#Service.authorize(&self)",
    ) in contains


def test_rust_frontend_records_parser_diagnostics() -> None:
    facts = RustTreeSitterFrontend().extract("src/broken.rs", b"fn broken( {\n")

    assert facts.diagnostics
    assert facts.diagnostics[0].message.startswith("Rust parse error")
