"""Shared Tree-sitter frontend utilities."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from tree_sitter import Language, Node, Parser, Tree

from codectx.frontends.base import ChunkFact
from codectx.source.spans import SourceSpan, byte_range_to_span
from codectx.source.tokens import estimate_token_count


@dataclass(frozen=True)
class ParseResult:
    """A parsed source tree and its original bytes."""

    source: bytes
    tree: Tree

    @property
    def root(self) -> Node:
        """Return the root Tree-sitter node."""
        return self.tree.root_node


def make_language(language_capsule: object) -> Language:
    """Create a Tree-sitter Language from a grammar capsule."""
    return Language(language_capsule)


def make_parser(language: Language) -> Parser:
    """Create a Tree-sitter parser for a language."""
    return Parser(language)


def parse_source(parser: Parser, source: bytes) -> ParseResult:
    """Parse source bytes with a configured parser."""
    return ParseResult(source=source, tree=parser.parse(source))


def node_text(source: bytes, node: Node) -> str:
    """Decode the exact source text for a Tree-sitter node."""
    return source[node.start_byte : node.end_byte].decode("utf-8")


def node_span(file_path: str, source: bytes, node: Node) -> SourceSpan:
    """Convert a Tree-sitter node range to a SourceSpan."""
    return byte_range_to_span(file_path, source, node.start_byte, node.end_byte)


def named_children(node: Node, *, type_name: str | None = None) -> Iterator[Node]:
    """Yield named children, optionally filtered by node type."""
    for child in node.named_children:
        if type_name is None or child.type == type_name:
            yield child


def walk_named(node: Node) -> Iterator[Node]:
    """Yield a Tree-sitter node and all named descendants depth-first."""
    if node.is_named:
        yield node
    for child in node.named_children:
        yield from walk_named(child)


def error_nodes(node: Node) -> Iterator[Node]:
    """Yield parse error or missing nodes under a node."""
    if node.is_error or node.is_missing:
        yield node
    for child in node.children:
        yield from error_nodes(child)


def first_child_by_field_name(node: Node, field_name: str) -> Node | None:
    """Return a child by field name."""
    return node.child_by_field_name(field_name)


def make_chunk(
    *,
    file_path: str,
    node_key: str | None,
    kind: str,
    source: bytes,
    node: Node,
    metadata: dict[str, object] | None = None,
) -> ChunkFact:
    """Create a ChunkFact from a Tree-sitter node."""
    span = node_span(file_path, source, node)
    text = node_text(source, node)
    return ChunkFact(
        file_path=file_path,
        node_key=node_key,
        kind=kind,
        start_line=span.start_line,
        end_line=span.end_line,
        text=text,
        token_estimate=estimate_token_count(text),
        metadata={} if metadata is None else metadata,
    )
