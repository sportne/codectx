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
    callable_index = _callable_resolution_index(body, file_path, source, local_name)
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
                callable_index=callable_index,
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
    callable_index: dict[tuple[str, int], str],
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
    _extract_call_like_occurrences(
        file_path=file_path,
        source=source,
        node=node,
        source_key=key,
        callable_index=callable_index,
        edges=edges,
        occurrences=occurrences,
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
        if name_node is None:  # pragma: no cover - defensive for malformed callables
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


def _callable_resolution_index(
    body: Node, file_path: str, source: bytes, owner_local_name: str
) -> dict[tuple[str, int], str]:
    candidates: dict[tuple[str, int], list[str]] = {}
    for child in body.named_children:
        if child.type not in {"method_declaration", "constructor_declaration"}:
            continue
        name_node = first_child_by_field_name(child, "name")
        if name_node is None:
            continue
        name = node_text(source, name_node)
        callable_name = "<init>" if child.type == "constructor_declaration" else name
        signature = _callable_signature(child, source)
        local_name = f"{owner_local_name}.{callable_name}{signature}"
        candidates.setdefault((name, _parameter_count(child)), []).append(
            _symbol_key(file_path, local_name)
        )
    return {key: keys[0] for key, keys in candidates.items() if len(keys) == 1}


def _extract_call_like_occurrences(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    source_key: str,
    callable_index: dict[tuple[str, int], str],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
) -> None:
    for call in _call_like_nodes(node):
        call_info = _call_info(file_path, source, call)
        if call_info is None:  # pragma: no cover - defensive for malformed calls
            continue
        text, text_span, argument_count, simple_name, is_simple_or_this = call_info
        resolved_key = (
            callable_index.get((simple_name, argument_count))
            if is_simple_or_this
            else None
        )
        confidence = 0.75 if resolved_key is not None else 0.45
        occurrences.append(
            OccurrenceFact(
                file_path=file_path,
                role="call",
                text=text,
                span=text_span,
                node_key=source_key,
                resolved_key=resolved_key,
                confidence=confidence,
                extractor=EXTRACTOR,
                metadata={
                    "argument_count": argument_count,
                    "call_kind": call.type,
                },
            )
        )
        edges.append(
            EdgeFact(
                kind="calls",
                src_key=source_key,
                dst_key=resolved_key,
                unresolved_src=None,
                unresolved_dst=None if resolved_key is not None else text,
                file_path=file_path,
                span=node_span(file_path, source, call),
                confidence=confidence,
                extractor=EXTRACTOR,
                metadata={
                    "argument_count": argument_count,
                    "call_kind": call.type,
                    "call_text": text,
                },
            )
        )


def _call_like_nodes(node: Node) -> Iterator[Node]:
    for child in node.named_children:
        if child.type in {"method_invocation", "object_creation_expression"}:
            yield child
            continue
        if _is_type_node(child):
            continue
        yield from _call_like_nodes(child)


def _call_info(
    file_path: str, source: bytes, node: Node
) -> tuple[str, SourceSpan, int, str, bool] | None:
    if node.type == "method_invocation":
        name_node = first_child_by_field_name(node, "name")
        arguments = first_child_by_field_name(node, "arguments")
        if name_node is None or arguments is None:  # pragma: no cover - defensive
            return None
        object_node = first_child_by_field_name(node, "object")
        simple_name = node_text(source, name_node)
        is_simple_or_this = object_node is None or object_node.type == "this"
        start_byte = (
            name_node.start_byte
            if is_simple_or_this or object_node is None
            else object_node.start_byte
        )
        return (
            source[start_byte : name_node.end_byte].decode("utf-8"),
            byte_range_to_span(file_path, source, start_byte, name_node.end_byte),
            _argument_count(arguments),
            simple_name,
            is_simple_or_this,
        )
    if node.type == "object_creation_expression":
        type_node = first_child_by_field_name(node, "type")
        arguments = first_child_by_field_name(node, "arguments")
        if type_node is None or arguments is None:  # pragma: no cover - defensive
            return None
        text = node_text(source, type_node)
        return (
            text,
            node_span(file_path, source, type_node),
            _argument_count(arguments),
            text,
            False,
        )
    return None  # pragma: no cover - guarded by callers


def _parameter_count(node: Node) -> int:
    parameters = next(
        (child for child in node.named_children if child.type == "formal_parameters"),
        None,
    )
    if parameters is None:  # pragma: no cover - defensive for malformed callables
        return 0
    return sum(
        1
        for parameter in parameters.named_children
        if parameter.type in {"formal_parameter", "spread_parameter"}
    )


def _argument_count(arguments: Node) -> int:
    return len(arguments.named_children)


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
