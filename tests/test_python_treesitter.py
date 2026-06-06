from __future__ import annotations

from codectx.frontends.python_treesitter import PythonTreeSitterFrontend

PYTHON_SOURCE = b"""
import os, sys as system
from .helpers import load as load_helper, validate


class PaymentService(BaseService):
    gateway = None
    timeout: int = 30

    def authorize(self, request):
        validate(request)
        self.audit(request)
        return self.gateway.charge(request)

    async def audit(self, request):
        await emit(request)


async def create_service(config):
    return PaymentService(config)
"""


def test_python_frontend_extracts_definitions_imports_and_chunks() -> None:
    facts = PythonTreeSitterFrontend().extract("src/payments/service.py", PYTHON_SOURCE)

    symbols = {node.symbol_key for node in facts.nodes}
    assert "python:src/payments/service.py#PaymentService" in symbols
    assert (
        "python:src/payments/service.py#PaymentService.authorize(self,request)"
        in symbols
    )
    assert (
        "python:src/payments/service.py#PaymentService.audit(self,request)" in symbols
    )
    assert "python:src/payments/service.py#create_service(config)" in symbols
    assert "python:src/payments/service.py#PaymentService.gateway" in symbols
    assert "python:src/payments/service.py#PaymentService.timeout" in symbols
    assert any(node.name == "PaymentService" for node in facts.nodes)
    assert any(node.name == "authorize" for node in facts.nodes)
    assert any(node.name == "gateway" for node in facts.nodes)
    assert any(chunk.node_key in symbols for chunk in facts.chunks)
    assert not facts.diagnostics


def test_python_frontend_extracts_edges_and_occurrences() -> None:
    facts = PythonTreeSitterFrontend().extract("src/payments/service.py", PYTHON_SOURCE)

    import_edges = {
        edge.unresolved_dst for edge in facts.edges if edge.kind == "imports"
    }
    assert import_edges == {
        "os",
        "sys",
        ".helpers.load",
        ".helpers.validate",
    }
    contains_edges = {
        (edge.src_key, edge.dst_key) for edge in facts.edges if edge.kind == "contains"
    }
    assert (
        "python:src/payments/service.py#PaymentService",
        "python:src/payments/service.py#PaymentService.authorize(self,request)",
    ) in contains_edges
    assert any(
        edge.kind == "uses_type" and edge.unresolved_dst == "BaseService"
        for edge in facts.edges
    )

    calls = {
        occurrence.text: occurrence
        for occurrence in facts.occurrences
        if occurrence.role == "call"
    }
    assert calls["validate"].resolved_key is None
    assert (
        calls["self.audit"].resolved_key
        == "python:src/payments/service.py#PaymentService.audit(self,request)"
    )
    assert calls["self.gateway.charge"].resolved_key is None
    assert any(
        edge.kind == "uses_type"
        and edge.dst_key == "python:src/payments/service.py#PaymentService"
        for edge in facts.edges
    )


def test_python_frontend_records_parser_diagnostics() -> None:
    facts = PythonTreeSitterFrontend().extract("src/broken.py", b"def broken(:\n")

    assert facts.diagnostics
    assert facts.diagnostics[0].message.startswith("Python parse error")


def test_python_frontend_extracts_nested_classes_and_typed_parameters() -> None:
    facts = PythonTreeSitterFrontend().extract(
        "src/nested.py",
        b"""
class Outer:
    "documentation expression"
    settings.value = 1

    class Inner:
        def configure(self, mode: str, retries=3):
            other.run(mode)
""",
    )

    symbols = {node.symbol_key for node in facts.nodes}
    assert "python:src/nested.py#Outer" in symbols
    assert "python:src/nested.py#Outer.Inner" in symbols
    assert "python:src/nested.py#Outer.Inner.configure(self,mode,retries)" in symbols
    assert "python:src/nested.py#Outer.settings" not in symbols

    contains_edges = {
        (edge.src_key, edge.dst_key) for edge in facts.edges if edge.kind == "contains"
    }
    assert (
        "python:src/nested.py#Outer",
        "python:src/nested.py#Outer.Inner",
    ) in contains_edges
    assert (
        "python:src/nested.py#Outer.Inner",
        "python:src/nested.py#Outer.Inner.configure(self,mode,retries)",
    ) in contains_edges
    assert any(
        edge.kind == "calls" and edge.unresolved_dst == "other.run"
        for edge in facts.edges
    )


def test_python_frontend_handles_from_import_module_targets() -> None:
    facts = PythonTreeSitterFrontend().extract(
        "src/imports.py",
        b"from pkg.sub import thing\nfrom . import helpers\n",
    )

    import_edges = {
        edge.unresolved_dst for edge in facts.edges if edge.kind == "imports"
    }
    assert import_edges == {"pkg.sub.thing", ".helpers"}


def test_python_frontend_extracts_decorated_definitions_and_parameter_shapes() -> None:
    facts = PythonTreeSitterFrontend().extract(
        "src/decorated.py",
        b"""
from dataclasses import dataclass

@dataclass
class User:
    @property
    def name(self) -> str:
        return self._name

    @staticmethod
    def make(a: int = 1, *args, **kwargs):
        return helper(a, *args, **kwargs)

@fixture
def sample(a: int = 1, *args, **kwargs):
    return User()
""",
    )

    symbols = {node.symbol_key for node in facts.nodes}
    assert "python:src/decorated.py#User" in symbols
    assert "python:src/decorated.py#User.name(self)" in symbols
    assert "python:src/decorated.py#User.make(a,*args,**kwargs)" in symbols
    assert "python:src/decorated.py#sample(a,*args,**kwargs)" in symbols

    calls = {
        occurrence.text: occurrence
        for occurrence in facts.occurrences
        if occurrence.role == "call"
    }
    assert calls["helper"].metadata["argument_count"] == 3
    assert any(
        edge.kind == "uses_type" and edge.dst_key == "python:src/decorated.py#User"
        for edge in facts.edges
    )


def test_python_frontend_ignores_non_definition_statements() -> None:
    facts = PythonTreeSitterFrontend().extract(
        "src/module_code.py",
        b"""
VALUE = 1

class Marker:
    pass

def run():
    return (lambda value: value)(VALUE)
""",
    )

    symbols = {node.symbol_key for node in facts.nodes}
    assert "python:src/module_code.py#Marker" in symbols
    assert "python:src/module_code.py#run()" in symbols
    assert "python:src/module_code.py#VALUE" not in symbols
    assert all(edge.unresolved_dst != "(lambda value: value)" for edge in facts.edges)
