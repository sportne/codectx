"""Java Tree-sitter frontend."""

from __future__ import annotations

from collections.abc import Iterator

import tree_sitter_java
from tree_sitter import Node, Parser

from codectx.frontends.base import (
    ChunkFact,
    DiagnosticFact,
    EdgeFact,
    ExtractedFacts,
    NodeFact,
    OccurrenceFact,
)
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
)
from codectx.source.spans import SourceSpan, byte_range_to_span

EXTRACTOR = "treesitter-java"


class JavaTreeSitterFrontend:
    """Tree-sitter based Java frontend."""

    language = "java"

    def __init__(self, parser: Parser | None = None) -> None:
        """Create a Java frontend with an optional parser override."""
        self._parser = parser or make_parser(make_language(tree_sitter_java.language()))

    def extract(self, file_path: str, source: bytes) -> ExtractedFacts:
        """Extract Java definition facts from source."""
        parsed = parse_source(self._parser, source)
        diagnostics = _parser_diagnostics(file_path, source, parsed.root)
        package_name = _package_name(parsed.root, source)
        nodes: list[NodeFact] = []
        edges: list[EdgeFact] = []
        occurrences: list[OccurrenceFact] = []
        chunks: list[ChunkFact] = []

        for import_node in named_children(parsed.root, type_name="import_declaration"):
            import_info = _import_info(file_path, import_node, source)
            if import_info is None:
                continue
            import_text, import_span = import_info
            span = node_span(file_path, source, import_node)
            is_static = any(child.type == "static" for child in import_node.children)
            edges.append(
                EdgeFact(
                    kind="imports",
                    src_key=None,
                    dst_key=None,
                    unresolved_src=file_path,
                    unresolved_dst=import_text,
                    file_path=file_path,
                    span=span,
                    confidence=0.8,
                    extractor=EXTRACTOR,
                    metadata={"static": is_static},
                )
            )
            occurrences.append(
                OccurrenceFact(
                    file_path=file_path,
                    role="import",
                    text=import_text,
                    span=import_span,
                    node_key=None,
                    resolved_key=None,
                    confidence=0.8,
                    extractor=EXTRACTOR,
                    metadata={"static": is_static},
                )
            )

        for type_node in _top_level_type_nodes(parsed.root):
            _extract_type(
                file_path=file_path,
                source=source,
                node=type_node,
                package_name=package_name,
                parents=(),
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
            )

        return ExtractedFacts(
            nodes=nodes,
            edges=edges,
            occurrences=occurrences,
            chunks=chunks,
            diagnostics=diagnostics,
        )


def _parser_diagnostics(
    file_path: str, source: bytes, root: Node
) -> list[DiagnosticFact]:
    if not root.has_error:
        return []
    diagnostics = [
        DiagnosticFact(
            file_path=file_path,
            severity="error",
            message=f"Java parse error at {node.type}",
            extractor=EXTRACTOR,
            span=node_span(file_path, source, node),
            code=node.type,
        )
        for node in error_nodes(root)
    ]
    if diagnostics:
        return diagnostics
    return [
        DiagnosticFact(
            file_path=file_path,
            severity="error",
            message="Java parse error",
            extractor=EXTRACTOR,
            span=node_span(file_path, source, root),
            code="parse_error",
        )
    ]


def _package_name(root: Node, source: bytes) -> str | None:
    package_node = next(named_children(root, type_name="package_declaration"), None)
    if package_node is None:
        return None
    for child in package_node.named_children:
        if child.type in {"identifier", "scoped_identifier"}:
            return node_text(source, child)
    return None


def _import_info(
    file_path: str, node: Node, source: bytes
) -> tuple[str, SourceSpan] | None:
    name_node: Node | None = None
    wildcard_node: Node | None = None
    wildcard = False
    for child in node.named_children:
        if child.type in {"identifier", "scoped_identifier"}:
            name_node = child
        elif child.type == "asterisk":
            wildcard_node = child
            wildcard = True
    if name_node is None:
        return None
    name = node_text(source, name_node)
    if not wildcard:
        return name, node_span(file_path, source, name_node)
    end_node = wildcard_node or name_node
    return (
        f"{name}.*",
        byte_range_to_span(file_path, source, name_node.start_byte, end_node.end_byte),
    )


def _top_level_type_nodes(root: Node) -> Iterator[Node]:
    for child in root.named_children:
        if _is_type_node(child):
            yield child


def _extract_type(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    package_name: str | None,
    parents: tuple[str, ...],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    name_node = first_child_by_field_name(node, "name")
    if name_node is None:
        return
    name = node_text(source, name_node)
    local_parts = (*parents, name)
    local_name = ".".join(local_parts)
    qualified_name = f"{package_name}.{local_name}" if package_name else local_name
    key = _symbol_key(file_path, local_name)
    span = node_span(file_path, source, node)
    nodes.append(
        NodeFact(
            kind="type",
            language="java",
            name=name,
            qualified_name=qualified_name,
            symbol_key=key,
            file_path=file_path,
            span=span,
            confidence=1.0,
            extractor=EXTRACTOR,
            metadata={"declaration_kind": node.type, "package": package_name},
        )
    )
    occurrences.append(
        _definition_occurrence(file_path, source, name_node, key, "type")
    )
    chunks.append(
        make_chunk(
            file_path=file_path,
            node_key=key,
            kind="definition",
            source=source,
            node=node,
            metadata={"node_kind": "type"},
        )
    )
    if parents:
        edges.append(_contains_edge(file_path, source, parents, local_name, node))

    body = first_child_by_field_name(node, "body")
    if body is None:
        return
    for child in body.named_children:
        if child.type in {"method_declaration", "constructor_declaration"}:
            _extract_callable(
                file_path=file_path,
                source=source,
                node=child,
                owner_local_name=local_name,
                owner_qualified_name=qualified_name,
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
            )
        elif child.type == "field_declaration":
            _extract_fields(
                file_path=file_path,
                source=source,
                node=child,
                owner_local_name=local_name,
                owner_qualified_name=qualified_name,
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
            )
        elif _is_type_node(child):
            _extract_type(
                file_path=file_path,
                source=source,
                node=child,
                package_name=package_name,
                parents=local_parts,
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
            )


def _extract_callable(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    owner_local_name: str,
    owner_qualified_name: str,
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    name_node = first_child_by_field_name(node, "name")
    if name_node is None:
        return
    name = node_text(source, name_node)
    callable_name = "<init>" if node.type == "constructor_declaration" else name
    signature = _callable_signature(node, source)
    local_name = f"{owner_local_name}.{callable_name}{signature}"
    key = _symbol_key(file_path, local_name)
    nodes.append(
        NodeFact(
            kind="callable",
            language="java",
            name=name,
            qualified_name=f"{owner_qualified_name}.{callable_name}{signature}",
            symbol_key=key,
            file_path=file_path,
            span=node_span(file_path, source, node),
            confidence=1.0,
            extractor=EXTRACTOR,
            metadata={"callable_kind": node.type},
        )
    )
    occurrences.append(
        _definition_occurrence(file_path, source, name_node, key, "callable")
    )
    chunks.append(
        make_chunk(
            file_path=file_path,
            node_key=key,
            kind="definition",
            source=source,
            node=node,
            metadata={"node_kind": "callable"},
        )
    )
    edges.append(
        _contains_edge(file_path, source, (owner_local_name,), local_name, node)
    )


def _callable_signature(node: Node, source: bytes) -> str:
    parameters = next(
        (child for child in node.named_children if child.type == "formal_parameters"),
        None,
    )
    if parameters is None:
        return "()"
    parameter_types = [
        _parameter_type(parameter, source)
        for parameter in parameters.named_children
        if parameter.type in {"formal_parameter", "spread_parameter"}
    ]
    return f"({','.join(parameter_types)})"


def _parameter_type(node: Node, source: bytes) -> str:
    type_node = first_child_by_field_name(node, "type")
    if type_node is None and node.named_children:
        type_node = node.named_children[0]
    if type_node is None:
        return "unknown"
    suffix = "..." if node.type == "spread_parameter" else ""
    return "".join(node_text(source, type_node).split()) + suffix


def _extract_fields(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    owner_local_name: str,
    owner_qualified_name: str,
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    for declarator in _field_declarators(node):
        name_node = first_child_by_field_name(declarator, "name")
        if name_node is None:
            continue
        name = node_text(source, name_node)
        local_name = f"{owner_local_name}.{name}"
        key = _symbol_key(file_path, local_name)
        nodes.append(
            NodeFact(
                kind="field",
                language="java",
                name=name,
                qualified_name=f"{owner_qualified_name}.{name}",
                symbol_key=key,
                file_path=file_path,
                span=node_span(file_path, source, declarator),
                confidence=1.0,
                extractor=EXTRACTOR,
                metadata={"declaration_kind": "field_declaration"},
            )
        )
        occurrences.append(
            _definition_occurrence(file_path, source, name_node, key, "field")
        )
        chunks.append(
            make_chunk(
                file_path=file_path,
                node_key=key,
                kind="definition",
                source=source,
                node=node,
                metadata={"node_kind": "field"},
            )
        )
        edges.append(
            _contains_edge(
                file_path, source, (owner_local_name,), local_name, declarator
            )
        )


def _field_declarators(node: Node) -> Iterator[Node]:
    for child in node.named_children:
        if child.type in {"variable_declarator", "identifier"}:
            yield child


def _definition_occurrence(
    file_path: str, source: bytes, name_node: Node, key: str, role: str
) -> OccurrenceFact:
    return OccurrenceFact(
        file_path=file_path,
        role="definition",
        text=node_text(source, name_node),
        span=node_span(file_path, source, name_node),
        node_key=key,
        resolved_key=key,
        confidence=1.0,
        extractor=EXTRACTOR,
        metadata={"node_kind": role},
    )


def _contains_edge(
    file_path: str,
    source: bytes,
    parent_parts: tuple[str, ...],
    child_local_name: str,
    node: Node,
) -> EdgeFact:
    return EdgeFact(
        kind="contains",
        src_key=_symbol_key(file_path, ".".join(parent_parts)),
        dst_key=_symbol_key(file_path, child_local_name),
        unresolved_src=None,
        unresolved_dst=None,
        file_path=file_path,
        span=node_span(file_path, source, node),
        confidence=1.0,
        extractor=EXTRACTOR,
    )


def _is_type_node(node: Node) -> bool:
    return node.type in {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
    }


def _symbol_key(file_path: str, local_name: str) -> str:
    return f"java:{file_path}#{local_name}"
