from __future__ import annotations

import importlib.metadata as metadata

from codectx.frontends.cpp_treesitter import CppTreeSitterFrontend
from codectx.frontends.java_treesitter import JavaTreeSitterFrontend
from codectx.frontends.matlab_treesitter import MatlabTreeSitterFrontend
from codectx.frontends.python_treesitter import PythonTreeSitterFrontend


def test_runtime_dependency_versions_are_in_supported_ranges() -> None:
    assert _version_tuple("pathspec")[:2] >= (0, 12)
    assert _version_tuple("pathspec")[0] == 0
    assert _version_tuple("tree-sitter")[:2] == (0, 25)
    assert _version_tuple("tree-sitter-java")[:2] == (0, 23)
    assert _version_tuple("tree-sitter-cpp")[:2] == (0, 23)
    assert _version_tuple("tree-sitter-python")[:2] == (0, 23)
    assert _version_tuple("tree-sitter-matlab")[:2] == (1, 3)


def test_tree_sitter_runtime_packages_parse_minimal_sources() -> None:
    java_facts = JavaTreeSitterFrontend().extract(
        "src/Foo.java", b"class Foo { void run() {} }\n"
    )
    cpp_facts = CppTreeSitterFrontend().extract(
        "src/foo.cpp", b"namespace acme { int run() { return 1; } }\n"
    )
    python_facts = PythonTreeSitterFrontend().extract(
        "src/service.py", b"class Service:\n    def run(self):\n        return 1\n"
    )
    matlab_facts = MatlabTreeSitterFrontend().extract(
        "src/run.m", b"function out = run()\nout = 1;\nend\n"
    )

    assert not java_facts.diagnostics
    assert any(node.name == "Foo" for node in java_facts.nodes)
    assert not cpp_facts.diagnostics
    assert any(node.name == "run" for node in cpp_facts.nodes)
    assert not python_facts.diagnostics
    assert any(node.name == "Service" for node in python_facts.nodes)
    assert not matlab_facts.diagnostics
    assert any(node.name == "run" for node in matlab_facts.nodes)


def _version_tuple(distribution: str) -> tuple[int, ...]:
    return tuple(int(part) for part in metadata.version(distribution).split(".")[:3])
