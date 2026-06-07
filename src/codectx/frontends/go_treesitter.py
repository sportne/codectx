"""Go Tree-sitter frontend."""

from __future__ import annotations

from collections.abc import Iterator

import tree_sitter_go
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
    make_chunk,
    make_language,
    make_parser,
    node_span,
    node_text,
    parse_source,
    walk_named,
)
from codectx.source.spans import SourceSpan, byte_range_to_span

EXTRACTOR = "treesitter-go"


class GoTreeSitterFrontend:
    """Tree-sitter based Go frontend."""

    language = "go"

    def __init__(self, parser: Parser | None = None) -> None:
        """Create a Go frontend with an optional parser override."""
        self._parser = parser or make_parser(make_language(tree_sitter_go.language()))

    def extract(self, file_path: str, source: bytes) -> ExtractedFacts:
        """Extract Go graph facts from source."""
        parsed = parse_source(self._parser, source)
        diagnostics = _parser_diagnostics(file_path, source, parsed.root)
        package_name = _package_name(parsed.root, source)
        nodes: list[NodeFact] = []
        edges: list[EdgeFact] = []
        occurrences: list[OccurrenceFact] = []
        chunks: list[ChunkFact] = []
        callable_index = _callable_resolution_index(file_path, source, parsed.root)
        type_index = _type_resolution_index(file_path, source, parsed.root)

        if package_name is not None:
            _extract_package(
                file_path=file_path,
                source=source,
                root=parsed.root,
                package_name=package_name,
                nodes=nodes,
                occurrences=occurrences,
                chunks=chunks,
            )
        for child in parsed.root.named_children:
            if child.type == "import_declaration":
                _extract_imports(file_path, source, child, edges, occurrences)
            elif child.type == "type_declaration":
                _extract_type_declaration(
                    file_path=file_path,
                    source=source,
                    node=child,
                    package_name=package_name,
                    type_index=type_index,
                    nodes=nodes,
                    edges=edges,
                    occurrences=occurrences,
                    chunks=chunks,
                )
            elif child.type in {"function_declaration", "method_declaration"}:
                _extract_callable(
                    file_path=file_path,
                    source=source,
                    node=child,
                    package_name=package_name,
                    callable_index=callable_index,
                    type_index=type_index,
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
            message=f"Go parse error at {node.type}",
            extractor=EXTRACTOR,
            span=node_span(file_path, source, node),
            code=node.type,
        )
        for node in error_nodes(root)
    ]
    if diagnostics:
        return diagnostics
    return [  # pragma: no cover - defensive fallback when Tree-sitter reports only root errors
        DiagnosticFact(
            file_path=file_path,
            severity="error",
            message="Go parse error",
            extractor=EXTRACTOR,
            span=node_span(file_path, source, root),
            code="parse_error",
        )
    ]


def _package_name(root: Node, source: bytes) -> str | None:
    package = _first_named_child(root, {"package_clause"})
    if package is None:  # pragma: no cover - guarded by caller
        return None
    name_node = _first_named_child(package, {"package_identifier"})
    return None if name_node is None else node_text(source, name_node)


def _extract_package(
    *,
    file_path: str,
    source: bytes,
    root: Node,
    package_name: str,
    nodes: list[NodeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    package = _first_named_child(root, {"package_clause"})
    if package is None:
        return
    name_node = _first_named_child(package, {"package_identifier"})
    if name_node is None:  # pragma: no cover - malformed package clause
        return
    key = _symbol_key(file_path, package_name)
    nodes.append(
        NodeFact(
            kind="namespace",
            language="go",
            name=package_name,
            qualified_name=package_name,
            symbol_key=key,
            file_path=file_path,
            span=node_span(file_path, source, package),
            confidence=1.0,
            extractor=EXTRACTOR,
            metadata={"declaration_kind": "package_clause"},
        )
    )
    occurrences.append(
        _definition_occurrence(file_path, source, name_node, key, "namespace")
    )
    chunks.append(
        make_chunk(
            file_path=file_path,
            node_key=key,
            kind="definition",
            source=source,
            node=package,
            metadata={"node_kind": "namespace"},
        )
    )


def _extract_imports(
    file_path: str,
    source: bytes,
    node: Node,
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
) -> None:
    for spec in _descendants_of_type(node, "import_spec"):
        literal = _first_named_child(
            spec, {"interpreted_string_literal", "raw_string_literal"}
        )
        if literal is None:  # pragma: no cover - malformed import spec
            continue
        import_text, import_span = _import_text(file_path, source, literal)
        alias_node = _first_named_child(
            spec, {"package_identifier", "dot", "blank_identifier"}
        )
        alias = None if alias_node is None else node_text(source, alias_node)
        edges.append(
            EdgeFact(
                kind="imports",
                src_key=None,
                dst_key=None,
                unresolved_src=file_path,
                unresolved_dst=import_text,
                file_path=file_path,
                span=node_span(file_path, source, spec),
                confidence=0.8,
                extractor=EXTRACTOR,
                metadata={"alias": alias},
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
                metadata={"alias": alias},
            )
        )


def _import_text(
    file_path: str, source: bytes, literal: Node
) -> tuple[str, SourceSpan]:
    content = _first_named_child(
        literal, {"interpreted_string_literal_content", "raw_string_literal_content"}
    )
    if content is not None:
        return node_text(source, content), node_span(file_path, source, content)
    text = node_text(source, literal).strip(
        '"`'
    )  # pragma: no cover - malformed literal fallback
    return (
        text,
        byte_range_to_span(
            file_path, source, literal.start_byte + 1, literal.end_byte - 1
        ),
    )


def _extract_type_declaration(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    package_name: str | None,
    type_index: dict[str, str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    for spec in node.named_children:
        if spec.type not in {
            "type_spec",
            "type_alias",
        }:  # pragma: no cover - parser grammar guard
            continue
        name_node = _first_named_child(spec, {"type_identifier"})
        if name_node is None:  # pragma: no cover - malformed type declaration
            continue
        name = node_text(source, name_node)
        key = _symbol_key(file_path, name)
        declaration_kind = _type_declaration_kind(spec)
        nodes.append(
            NodeFact(
                kind="type",
                language="go",
                name=name,
                qualified_name=_qualified(package_name, name),
                symbol_key=key,
                file_path=file_path,
                span=node_span(file_path, source, spec),
                confidence=1.0,
                extractor=EXTRACTOR,
                metadata={"declaration_kind": declaration_kind},
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
                node=spec,
                metadata={"node_kind": "type"},
            )
        )
        if package_name is not None:
            edges.append(_contains_edge(file_path, source, package_name, name, spec))
        if declaration_kind == "struct_type":
            _extract_struct_fields(
                file_path=file_path,
                source=source,
                node=spec,
                owner_name=name,
                owner_key=key,
                package_name=package_name,
                type_index=type_index,
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
            )
        elif declaration_kind == "interface_type":
            _extract_interface_methods(
                file_path=file_path,
                source=source,
                node=spec,
                owner_name=name,
                owner_key=key,
                package_name=package_name,
                type_index=type_index,
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
            )
        _extract_type_references(
            file_path=file_path,
            source=source,
            owner_key=key,
            nodes=_type_reference_nodes(spec),
            type_index=type_index,
            edges=edges,
            occurrences=occurrences,
            reference_kind="type_declaration",
            skip_name=name,
        )


def _extract_struct_fields(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    owner_name: str,
    owner_key: str,
    package_name: str | None,
    type_index: dict[str, str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    for field in _descendants_of_type(node, "field_declaration"):
        names = [
            child for child in field.named_children if child.type == "field_identifier"
        ]
        field_names = (
            [(node_text(source, name_node), name_node) for name_node in names]
            if names
            else _embedded_field_names(source, field)
        )
        for name, name_node in field_names:
            local_name = f"{owner_name}.{name}"
            key = _symbol_key(file_path, local_name)
            nodes.append(
                NodeFact(
                    kind="field",
                    language="go",
                    name=name,
                    qualified_name=_qualified(package_name, local_name),
                    symbol_key=key,
                    file_path=file_path,
                    span=node_span(file_path, source, field),
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
                    node=field,
                    metadata={"node_kind": "field"},
                )
            )
            edges.append(
                _contains_edge(file_path, source, owner_name, local_name, field)
            )
        _extract_type_references(
            file_path=file_path,
            source=source,
            owner_key=owner_key,
            nodes=_type_reference_nodes(field),
            type_index=type_index,
            edges=edges,
            occurrences=occurrences,
            reference_kind="field_type",
        )


def _extract_interface_methods(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    owner_name: str,
    owner_key: str,
    package_name: str | None,
    type_index: dict[str, str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    for method in _descendants_of_type(node, "method_elem"):
        name_node = _first_named_child(method, {"field_identifier"})
        if name_node is None:  # pragma: no cover - malformed interface method
            continue
        name = node_text(source, name_node)
        signature = _callable_signature(method, source)
        local_name = f"{owner_name}.{name}{signature}"
        key = _symbol_key(file_path, local_name)
        nodes.append(
            NodeFact(
                kind="callable",
                language="go",
                name=name,
                qualified_name=_qualified(package_name, local_name),
                symbol_key=key,
                file_path=file_path,
                span=node_span(file_path, source, method),
                confidence=1.0,
                extractor=EXTRACTOR,
                metadata={"callable_kind": "interface_method"},
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
                node=method,
                metadata={"node_kind": "callable"},
            )
        )
        edges.append(_contains_edge(file_path, source, owner_name, local_name, method))
        _extract_type_references(
            file_path=file_path,
            source=source,
            owner_key=key,
            nodes=_type_reference_nodes(method),
            type_index=type_index,
            edges=edges,
            occurrences=occurrences,
            reference_kind="signature",
        )


def _extract_callable(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    package_name: str | None,
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    type_index: dict[str, str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    name_node = _callable_name_node(node)
    if name_node is None:  # pragma: no cover - malformed callable declaration
        return
    name = node_text(source, name_node)
    receiver = _receiver_info(node, source)
    scope = () if receiver is None else (receiver[1],)
    signature = _callable_signature(node, source)
    local_name = ".".join((*scope, f"{name}{signature}"))
    key = _symbol_key(file_path, local_name)
    nodes.append(
        NodeFact(
            kind="callable",
            language="go",
            name=name,
            qualified_name=_qualified(package_name, local_name),
            symbol_key=key,
            file_path=file_path,
            span=node_span(file_path, source, node),
            confidence=1.0,
            extractor=EXTRACTOR,
            metadata={
                "callable_kind": node.type,
                "receiver": None if receiver is None else receiver[1],
            },
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
    if receiver is not None:
        edges.append(_contains_edge(file_path, source, receiver[1], local_name, node))
    elif package_name is not None:
        edges.append(_contains_edge(file_path, source, package_name, local_name, node))
    _extract_type_references(
        file_path=file_path,
        source=source,
        owner_key=key,
        nodes=_type_reference_nodes(node),
        type_index=type_index,
        edges=edges,
        occurrences=occurrences,
        reference_kind="signature_or_body",
    )
    _extract_call_like_occurrences(
        file_path=file_path,
        source=source,
        node=node,
        source_key=key,
        scope=scope,
        receiver_name=None if receiver is None else receiver[0],
        callable_index=callable_index,
        type_index=type_index,
        edges=edges,
        occurrences=occurrences,
    )


def _extract_call_like_occurrences(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    source_key: str,
    scope: tuple[str, ...],
    receiver_name: str | None,
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    type_index: dict[str, str],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
) -> None:
    for call in _call_like_nodes(node):
        call_info = _call_info(file_path, source, call)
        if call_info is None:
            continue
        text, text_span, argument_count, simple_name, receiver = call_info
        resolved_key = _resolve_call(
            scope=scope,
            simple_name=simple_name,
            argument_count=argument_count,
            receiver=receiver,
            receiver_name=receiver_name,
            callable_index=callable_index,
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
                    "call_kind": "call_expression",
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
                    "call_kind": "call_expression",
                    "call_text": text,
                },
            )
        )
        if receiver is None and simple_name in type_index:
            _record_constructor_type_reference(
                file_path=file_path,
                source=source,
                source_key=source_key,
                name=simple_name,
                name_span=text_span,
                call=call,
                type_key=type_index[simple_name],
                edges=edges,
                occurrences=occurrences,
            )


def _record_constructor_type_reference(
    *,
    file_path: str,
    source: bytes,
    source_key: str,
    name: str,
    name_span: SourceSpan,
    call: Node,
    type_key: str,
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
) -> None:
    occurrences.append(
        OccurrenceFact(
            file_path=file_path,
            role="type_reference",
            text=name,
            span=name_span,
            node_key=source_key,
            resolved_key=type_key,
            confidence=0.6,
            extractor=EXTRACTOR,
            metadata={"reference_kind": "constructor_call"},
        )
    )
    edges.append(
        EdgeFact(
            kind="uses_type",
            src_key=source_key,
            dst_key=type_key,
            unresolved_src=None,
            unresolved_dst=None,
            file_path=file_path,
            span=node_span(file_path, source, call),
            confidence=0.6,
            extractor=EXTRACTOR,
            metadata={"reference_kind": "constructor_call"},
        )
    )


def _extract_type_references(
    *,
    file_path: str,
    source: bytes,
    owner_key: str,
    nodes: Iterator[Node],
    type_index: dict[str, str],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    reference_kind: str,
    skip_name: str | None = None,
) -> None:
    seen: set[tuple[int, int]] = set()
    for type_node in nodes:
        text = _type_text(source, type_node)
        if (
            not text
            or text == skip_name
            or text in _GO_BUILTIN_TYPES
            or (type_node.start_byte, type_node.end_byte) in seen
        ):
            continue
        seen.add((type_node.start_byte, type_node.end_byte))
        simple_name = text.split(".")[-1].lstrip("*[]")
        resolved_key = type_index.get(simple_name)
        confidence = 0.7 if resolved_key is not None else 0.5
        span = node_span(file_path, source, type_node)
        occurrences.append(
            OccurrenceFact(
                file_path=file_path,
                role="type_reference",
                text=text,
                span=span,
                node_key=owner_key,
                resolved_key=resolved_key,
                confidence=confidence,
                extractor=EXTRACTOR,
                metadata={"reference_kind": reference_kind},
            )
        )
        edges.append(
            EdgeFact(
                kind="uses_type",
                src_key=owner_key,
                dst_key=resolved_key,
                unresolved_src=None,
                unresolved_dst=None if resolved_key is not None else text,
                file_path=file_path,
                span=span,
                confidence=confidence,
                extractor=EXTRACTOR,
                metadata={"reference_kind": reference_kind},
            )
        )


def _call_like_nodes(node: Node) -> Iterator[Node]:
    for child in node.named_children:
        if child.type == "call_expression":
            yield child
            continue
        if child.type in {
            "function_declaration",
            "method_declaration",
        }:  # pragma: no cover
            continue
        yield from _call_like_nodes(child)


def _call_info(
    file_path: str, source: bytes, node: Node
) -> tuple[str, SourceSpan, int, str, str | None] | None:
    if not node.named_children:  # pragma: no cover - malformed call expression
        return None
    target = node.named_children[0]
    arguments = _first_named_child(node, {"argument_list"})
    simple_name = _last_identifier_text(source, target)
    if (
        simple_name is None
    ):  # pragma: no cover - function-literal calls have no stable target
        return None
    text = node_text(source, target)
    receiver = _selector_receiver_text(source, target)
    return (
        text,
        node_span(file_path, source, target),
        0 if arguments is None else len(arguments.named_children),
        simple_name,
        receiver,
    )


def _resolve_call(
    *,
    scope: tuple[str, ...],
    simple_name: str,
    argument_count: int,
    receiver: str | None,
    receiver_name: str | None,
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
) -> str | None:
    if receiver is not None and receiver != receiver_name:
        return None
    if receiver == receiver_name and scope:
        key = callable_index.get((scope, simple_name, argument_count))
        if key is not None:
            return key
    if receiver is not None:
        return None
    for candidate_scope in (scope, ()):
        key = callable_index.get((candidate_scope, simple_name, argument_count))
        if key is not None:
            return key
    return None


def _callable_resolution_index(
    file_path: str, source: bytes, root: Node
) -> dict[tuple[tuple[str, ...], str, int], str]:
    candidates: dict[tuple[tuple[str, ...], str, int], list[str]] = {}
    for child in root.named_children:
        if child.type not in {"function_declaration", "method_declaration"}:
            continue
        name_node = _callable_name_node(child)
        if name_node is None:  # pragma: no cover - malformed callable declaration
            continue
        name = node_text(source, name_node)
        receiver = _receiver_info(child, source)
        scope = () if receiver is None else (receiver[1],)
        local_name = ".".join((*scope, f"{name}{_callable_signature(child, source)}"))
        candidates.setdefault((scope, name, _parameter_count(child)), []).append(
            _symbol_key(file_path, local_name)
        )
    return {key: keys[0] for key, keys in candidates.items() if len(keys) == 1}


def _type_resolution_index(file_path: str, source: bytes, root: Node) -> dict[str, str]:
    candidates: dict[str, list[str]] = {}
    for type_declaration in _descendants_of_type(root, "type_declaration"):
        for spec in type_declaration.named_children:
            if spec.type not in {
                "type_spec",
                "type_alias",
            }:  # pragma: no cover - parser grammar guard
                continue
            name_node = _first_named_child(spec, {"type_identifier"})
            if name_node is None:  # pragma: no cover - malformed type declaration
                continue
            name = node_text(source, name_node)
            candidates.setdefault(name, []).append(_symbol_key(file_path, name))
    return {name: keys[0] for name, keys in candidates.items() if len(keys) == 1}


def _type_reference_nodes(node: Node) -> Iterator[Node]:
    for child in node.named_children:
        if child.type in _GO_TYPE_NODE_TYPES:
            yield child
            continue
        if child.type in {"package_clause", "import_declaration"}:  # pragma: no cover
            continue
        yield from _type_reference_nodes(child)


def _type_text(source: bytes, node: Node) -> str:
    text = node_text(source, node)
    return "".join(text.split())


def _type_declaration_kind(node: Node) -> str:
    type_node = _first_named_child(node, {"struct_type", "interface_type"})
    if type_node is not None:
        return type_node.type
    return node.type


def _callable_name_node(node: Node) -> Node | None:
    for child in node.named_children:
        if child.type in {"identifier", "field_identifier"}:
            return child
    return None  # pragma: no cover - malformed callable declaration


def _receiver_info(node: Node, source: bytes) -> tuple[str | None, str] | None:
    if node.type != "method_declaration":
        return None
    receiver = _first_named_child(node, {"parameter_list"})
    if receiver is None:  # pragma: no cover - malformed method declaration
        return None
    parameter = _first_named_child(receiver, {"parameter_declaration"})
    if parameter is None:  # pragma: no cover - malformed method declaration
        return None
    name_node = _first_named_child(parameter, {"identifier"})
    type_node = next(
        (
            child
            for child in parameter.named_children
            if child.type in _GO_TYPE_NODE_TYPES
        ),
        None,
    )
    if type_node is None:
        return None
    return (
        None if name_node is None else node_text(source, name_node),
        _receiver_type_name(source, type_node),
    )


def _receiver_type_name(source: bytes, node: Node) -> str:
    text = _type_text(source, node).lstrip("*")
    return text.split(".")[-1]


def _callable_signature(node: Node, source: bytes) -> str:
    parameters = _callable_parameter_list(node)
    if parameters is None:
        return "()"
    types = [
        type_text
        for parameter in _parameter_declarations(parameters)
        for type_text in _parameter_type_texts(parameter, source)
    ]
    return f"({','.join(types)})"


def _parameter_count(node: Node) -> int:
    parameters = _callable_parameter_list(node)
    if parameters is None:
        return 0
    return sum(
        _parameter_count_from_declaration(parameter)
        for parameter in _parameter_declarations(parameters)
    )


def _callable_parameter_list(node: Node) -> Node | None:
    parameter_lists = [
        child for child in node.named_children if child.type == "parameter_list"
    ]
    if node.type == "method_declaration" and len(parameter_lists) > 1:
        return parameter_lists[1]
    return parameter_lists[0] if parameter_lists else None


def _parameter_declarations(parameters: Node) -> Iterator[Node]:
    yield from (
        child
        for child in parameters.named_children
        if child.type == "parameter_declaration"
    )


def _parameter_type_texts(parameter: Node, source: bytes) -> Iterator[str]:
    type_node = _parameter_type_node(parameter)
    if type_node is None:  # pragma: no cover - malformed parameter declaration
        return
    repeat = _parameter_count_from_declaration(parameter)
    text = _type_text(source, type_node)
    for _ in range(repeat):
        yield text


def _parameter_type_node(parameter: Node) -> Node | None:
    named = parameter.named_children
    for child in reversed(named):
        if child.type in _GO_TYPE_NODE_TYPES:
            return child
    return None  # pragma: no cover - malformed parameter declaration


def _parameter_count_from_declaration(parameter: Node) -> int:
    names = [
        child
        for child in parameter.named_children
        if child.type in {"identifier", "field_identifier"}
    ]
    return max(1, len(names))


def _embedded_field_names(source: bytes, field: Node) -> list[tuple[str, Node]]:
    type_node = _parameter_type_node(field)
    if type_node is None:
        return []
    name = _last_identifier_text(source, type_node)
    if name is None:
        return []
    return [(name, type_node)]


def _contains_edge(
    file_path: str,
    source: bytes,
    parent_local_name: str,
    child_local_name: str,
    node: Node,
) -> EdgeFact:
    return EdgeFact(
        kind="contains",
        src_key=_symbol_key(file_path, parent_local_name),
        dst_key=_symbol_key(file_path, child_local_name),
        unresolved_src=None,
        unresolved_dst=None,
        file_path=file_path,
        span=node_span(file_path, source, node),
        confidence=1.0,
        extractor=EXTRACTOR,
    )


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


def _qualified(package_name: str | None, local_name: str) -> str:
    return local_name if package_name is None else f"{package_name}.{local_name}"


def _first_named_child(node: Node, types: set[str]) -> Node | None:
    return next((child for child in node.named_children if child.type in types), None)


def _descendants_of_type(node: Node, type_name: str) -> Iterator[Node]:
    for child in node.named_children:
        if child.type == type_name:
            yield child
        yield from _descendants_of_type(child, type_name)


def _last_identifier_text(source: bytes, node: Node) -> str | None:
    identifiers = [
        child
        for child in walk_named(node)
        if child.type in {"identifier", "field_identifier", "type_identifier"}
    ]
    if not identifiers:  # pragma: no cover - unsupported expression target
        return None
    return node_text(source, identifiers[-1])


def _selector_receiver_text(source: bytes, node: Node) -> str | None:
    if node.type != "selector_expression" or not node.named_children:
        return None
    receiver = node.named_children[0]
    return node_text(source, receiver)


def _symbol_key(file_path: str, local_name: str) -> str:
    return f"go:{file_path}#{local_name}"


_GO_TYPE_NODE_TYPES = {
    "type_identifier",
    "qualified_type",
    "pointer_type",
    "slice_type",
    "array_type",
    "map_type",
    "channel_type",
    "generic_type",
}

_GO_BUILTIN_TYPES = {
    "any",
    "bool",
    "byte",
    "complex64",
    "complex128",
    "error",
    "float32",
    "float64",
    "int",
    "int8",
    "int16",
    "int32",
    "int64",
    "rune",
    "string",
    "uint",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
    "uintptr",
}
