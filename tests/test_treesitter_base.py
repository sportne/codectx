from __future__ import annotations

import tree_sitter_cpp
import tree_sitter_java
from tree_sitter import Language

from codectx.frontends.treesitter_base import (
    error_nodes,
    first_child_by_field_name,
    make_chunk,
    make_language,
    make_parser,
    named_children,
    node_span,
    node_text,
    parse_source,
    walk_named,
)


def test_parse_minimal_java_source() -> None:
    language = make_language(tree_sitter_java.language())
    parser = make_parser(language)

    result = parse_source(parser, b"class Foo {}\n")

    assert isinstance(language, Language)
    assert result.root.type == "program"
    assert result.root.has_error is False
    assert [child.type for child in named_children(result.root)] == [
        "class_declaration"
    ]


def test_parse_minimal_cpp_source() -> None:
    parser = make_parser(make_language(tree_sitter_cpp.language()))

    result = parse_source(parser, b"int main() { return 0; }\n")

    assert result.root.type == "translation_unit"
    assert result.root.has_error is False
    assert [child.type for child in named_children(result.root)] == [
        "function_definition"
    ]


def test_node_text_span_and_field_helpers() -> None:
    source = b"class Foo { void bar() {} }\n"
    parser = make_parser(make_language(tree_sitter_java.language()))
    result = parse_source(parser, source)
    class_node = next(named_children(result.root, type_name="class_declaration"))
    name_node = first_child_by_field_name(class_node, "name")

    assert name_node is not None
    assert node_text(source, name_node) == "Foo"
    assert node_span("src/Foo.java", source, name_node).start_line == 1
    assert node_span("src/Foo.java", source, name_node).start_col == 6
    assert list(named_children(result.root, type_name="missing")) == []


def test_node_span_end_line_is_inclusive_for_exclusive_range() -> None:
    source = b"class Foo {}\n"
    parser = make_parser(make_language(tree_sitter_java.language()))
    result = parse_source(parser, source)

    span = node_span("src/Foo.java", source, result.root)

    assert span.start_line == 1
    assert span.end_line == 1
    assert span.end_col == len("class Foo {}\n")
    assert not span.contains_line(2)


def test_walk_named_yields_named_descendants_depth_first() -> None:
    parser = make_parser(make_language(tree_sitter_java.language()))
    result = parse_source(parser, b"class Foo { void bar() {} }\n")

    node_types = [node.type for node in walk_named(result.root)]

    assert node_types[:3] == ["program", "class_declaration", "identifier"]


def test_error_nodes_finds_parse_errors() -> None:
    parser = make_parser(make_language(tree_sitter_java.language()))
    result = parse_source(parser, b"class Foo {")

    assert result.root.has_error is True
    assert [node.type for node in error_nodes(result.root)]


def test_make_chunk_uses_node_lines_and_token_estimate() -> None:
    source = b"class Foo {}\n"
    parser = make_parser(make_language(tree_sitter_java.language()))
    result = parse_source(parser, source)
    class_node = next(named_children(result.root, type_name="class_declaration"))

    chunk = make_chunk(
        file_path="src/Foo.java",
        node_key="java:src/Foo.java#Foo",
        kind="definition",
        source=source,
        node=class_node,
        metadata={"role": "type"},
    )

    assert chunk.file_path == "src/Foo.java"
    assert chunk.node_key == "java:src/Foo.java#Foo"
    assert chunk.kind == "definition"
    assert chunk.start_line == 1
    assert chunk.end_line == 1
    assert chunk.text == "class Foo {}"
    assert chunk.token_estimate == 3
    assert chunk.metadata == {"role": "type"}


def test_make_chunk_defaults_metadata_to_empty_dict() -> None:
    source = b"class Foo {}\n"
    parser = make_parser(make_language(tree_sitter_java.language()))
    result = parse_source(parser, source)
    class_node = next(named_children(result.root, type_name="class_declaration"))

    chunk = make_chunk(
        file_path="src/Foo.java",
        node_key=None,
        kind="definition",
        source=source,
        node=class_node,
    )

    assert chunk.metadata == {}
