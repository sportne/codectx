"""C++ Tree-sitter frontend."""

from __future__ import annotations

from collections.abc import Iterator

import tree_sitter_cpp
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

EXTRACTOR = "treesitter-cpp"


class CppTreeSitterFrontend:
    """Tree-sitter based C++ frontend."""

    language = "cpp"

    def __init__(self, parser: Parser | None = None) -> None:
        """Create a C++ frontend with an optional parser override."""
        self._parser = parser or make_parser(make_language(tree_sitter_cpp.language()))

    def extract(self, file_path: str, source: bytes) -> ExtractedFacts:
        """Extract C++ definition facts from source."""
        parsed = parse_source(self._parser, source)
        diagnostics = _parser_diagnostics(file_path, source, parsed.root)
        nodes: list[NodeFact] = []
        edges: list[EdgeFact] = []
        occurrences: list[OccurrenceFact] = []
        chunks: list[ChunkFact] = []
        callable_index = _callable_resolution_index(parsed.root, source)

        _extract_children(
            file_path=file_path,
            source=source,
            parent=parsed.root,
            scope=(),
            callable_index=callable_index,
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
            message=f"C++ parse error at {node.type}",
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
            message="C++ parse error",
            extractor=EXTRACTOR,
            span=node_span(file_path, source, root),
            code="parse_error",
        )
    ]


def _extract_children(
    *,
    file_path: str,
    source: bytes,
    parent: Node,
    scope: tuple[str, ...],
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    for child in parent.named_children:
        if child.type == "preproc_include":
            _extract_include(file_path, source, child, edges, occurrences)
        elif child.type == "namespace_definition":
            _extract_namespace(
                file_path=file_path,
                source=source,
                node=child,
                scope=scope,
                callable_index=callable_index,
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
                scope=scope,
                callable_index=callable_index,
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
            )
        elif child.type in {"declaration", "function_definition"}:
            _extract_callable(
                file_path=file_path,
                source=source,
                node=child,
                scope=scope,
                callable_index=callable_index,
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
            )


def _extract_include(
    file_path: str,
    source: bytes,
    node: Node,
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
) -> None:
    include_info = _include_info(file_path, source, node)
    if include_info is None:  # pragma: no cover - defensive for malformed includes
        return
    include_text, include_span = include_info
    span = node_span(file_path, source, node)
    edges.append(
        EdgeFact(
            kind="includes",
            src_key=None,
            dst_key=None,
            unresolved_src=file_path,
            unresolved_dst=include_text,
            file_path=file_path,
            span=span,
            confidence=0.8,
            extractor=EXTRACTOR,
        )
    )
    occurrences.append(
        OccurrenceFact(
            file_path=file_path,
            role="include",
            text=include_text,
            span=include_span,
            node_key=None,
            resolved_key=None,
            confidence=0.8,
            extractor=EXTRACTOR,
        )
    )


def _include_info(
    file_path: str, source: bytes, node: Node
) -> tuple[str, SourceSpan] | None:
    for child in node.named_children:
        if child.type == "system_lib_string":
            return node_text(source, child), node_span(file_path, source, child)
        if child.type == "string_literal":
            content = next(named_children(child, type_name="string_content"), None)
            if content is not None:
                return node_text(source, content), node_span(file_path, source, content)
            return (  # pragma: no cover - string_literal normally has string_content
                node_text(source, child).strip('"'),
                byte_range_to_span(
                    file_path, source, child.start_byte + 1, child.end_byte - 1
                ),
            )
    return None  # pragma: no cover - defensive for malformed includes


def _extract_namespace(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    scope: tuple[str, ...],
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    name_node = _namespace_name_node(node)
    if name_node is None:  # pragma: no cover - defensive for malformed namespaces
        return
    name = node_text(source, name_node)
    scope_name = _join_scope((*scope, name))
    key = _symbol_key(file_path, scope_name)
    nodes.append(
        NodeFact(
            kind="namespace",
            language="cpp",
            name=name,
            qualified_name=scope_name,
            symbol_key=key,
            file_path=file_path,
            span=node_span(file_path, source, node),
            confidence=1.0,
            extractor=EXTRACTOR,
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
            node=node,
            metadata={"node_kind": "namespace"},
        )
    )
    if scope:
        edges.append(_contains_edge(file_path, source, scope, scope_name, node))
    body = first_child_by_field_name(node, "body")
    if body is not None:
        _extract_children(
            file_path=file_path,
            source=source,
            parent=body,
            scope=(*scope, name),
            callable_index=callable_index,
            nodes=nodes,
            edges=edges,
            occurrences=occurrences,
            chunks=chunks,
        )


def _extract_type(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    scope: tuple[str, ...],
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    name_node = _type_name_node(node)
    if name_node is None:  # pragma: no cover - defensive for malformed type nodes
        return
    name = node_text(source, name_node)
    qualified_name = _join_scope((*scope, name))
    key = _symbol_key(file_path, qualified_name)
    nodes.append(
        NodeFact(
            kind="type",
            language="cpp",
            name=name,
            qualified_name=qualified_name,
            symbol_key=key,
            file_path=file_path,
            span=node_span(file_path, source, node),
            confidence=1.0,
            extractor=EXTRACTOR,
            metadata={"declaration_kind": node.type},
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
    if scope:
        edges.append(_contains_edge(file_path, source, scope, qualified_name, node))
    body = first_child_by_field_name(node, "body")
    if body is not None:
        _extract_type_members(
            file_path=file_path,
            source=source,
            parent=body,
            scope=(*scope, name),
            callable_index=callable_index,
            nodes=nodes,
            edges=edges,
            occurrences=occurrences,
            chunks=chunks,
        )


def _extract_type_members(
    *,
    file_path: str,
    source: bytes,
    parent: Node,
    scope: tuple[str, ...],
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    for child in parent.named_children:
        if _is_type_node(child):
            _extract_type(
                file_path=file_path,
                source=source,
                node=child,
                scope=scope,
                callable_index=callable_index,
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
            )
        elif child.type == "function_definition":
            _extract_callable(
                file_path=file_path,
                source=source,
                node=child,
                scope=scope,
                callable_index=callable_index,
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
            )
        elif child.type in {"declaration", "field_declaration"}:
            declarator = _function_declarator(child)
            if declarator is not None:
                _extract_callable(
                    file_path=file_path,
                    source=source,
                    node=child,
                    scope=scope,
                    callable_index=callable_index,
                    nodes=nodes,
                    edges=edges,
                    occurrences=occurrences,
                    chunks=chunks,
                    declarator=declarator,
                )
            elif child.type == "field_declaration":
                _extract_fields(
                    file_path, source, child, scope, nodes, edges, occurrences, chunks
                )


def _extract_callable(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    scope: tuple[str, ...],
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
    declarator: Node | None = None,
) -> None:
    declarator = declarator or _function_declarator(node)
    if declarator is None:  # pragma: no cover - guarded by callers for known nodes
        return
    name_node = _declarator_name_node(declarator)
    if name_node is None:  # pragma: no cover - defensive for malformed declarators
        return
    name = node_text(source, name_node)
    signature = _callable_signature(declarator, source)
    qualified_name = _qualified_callable_name(scope, name, signature)
    key = _symbol_key(file_path, qualified_name)
    if not _has_node(nodes, key):
        nodes.append(
            NodeFact(
                kind="callable",
                language="cpp",
                name=name,
                qualified_name=qualified_name,
                symbol_key=key,
                file_path=file_path,
                span=node_span(file_path, source, node),
                confidence=1.0,
                extractor=EXTRACTOR,
                metadata={"declaration_kind": node.type},
            )
        )
    elif node.type != "function_definition":
        return
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
    if scope:
        edges.append(_contains_edge(file_path, source, scope, qualified_name, node))
    _extract_call_like_occurrences(
        file_path=file_path,
        source=source,
        node=node,
        scope=scope,
        source_key=key,
        callable_index=callable_index,
        shadowed_names=_call_shadow_names(node, declarator, source),
        edges=edges,
        occurrences=occurrences,
    )


def _callable_resolution_index(
    root: Node, source: bytes
) -> dict[tuple[tuple[str, ...], str, int], str]:
    candidates: dict[tuple[tuple[str, ...], str, int], list[str]] = {}
    _collect_callable_candidates(root, source, (), candidates)
    return {key: keys[0] for key, keys in candidates.items() if len(keys) == 1}


def _collect_callable_candidates(
    parent: Node,
    source: bytes,
    scope: tuple[str, ...],
    candidates: dict[tuple[tuple[str, ...], str, int], list[str]],
) -> None:
    for child in parent.named_children:
        if child.type == "namespace_definition":
            name_node = _namespace_name_node(child)
            child_scope = (
                (*scope, node_text(source, name_node))
                if name_node is not None
                else scope
            )
            body = first_child_by_field_name(child, "body")
            if body is not None:
                _collect_callable_candidates(body, source, child_scope, candidates)
        elif _is_type_node(child):
            name_node = _type_name_node(child)
            child_scope = (
                (*scope, node_text(source, name_node))
                if name_node is not None
                else scope
            )
            body = first_child_by_field_name(child, "body")
            if body is not None:
                _collect_callable_candidates(body, source, child_scope, candidates)
        elif child.type in {"declaration", "function_definition"}:
            declarator = _function_declarator(child)
            if declarator is None:
                continue
            name_node = _declarator_name_node(declarator)
            if name_node is None:
                continue
            name = node_text(source, name_node)
            signature = _callable_signature(declarator, source)
            qualified_name = _qualified_callable_name(scope, name, signature)
            simple_name = name.split("::")[-1]
            candidates.setdefault(
                (scope, simple_name, _argument_count_for_parameters(declarator)),
                [],
            ).append(_symbol_key("", qualified_name))


def _extract_call_like_occurrences(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    scope: tuple[str, ...],
    source_key: str,
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    shadowed_names: set[str],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
) -> None:
    if node.type != "function_definition":
        return
    for call in _call_like_nodes(node):
        call_info = _call_info(file_path, source, call)
        if call_info is None:  # pragma: no cover - defensive for malformed calls
            continue
        text, text_span, argument_count, simple_name, is_simple = call_info
        resolved_key = (
            _resolve_call_key(
                file_path, callable_index, scope, simple_name, argument_count
            )
            if is_simple and simple_name not in shadowed_names
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
        if child.type == "call_expression":
            yield child
            continue
        if _is_type_node(child):
            continue
        yield from _call_like_nodes(child)


def _call_info(
    file_path: str, source: bytes, node: Node
) -> tuple[str, SourceSpan, int, str, bool] | None:
    function_node = first_child_by_field_name(node, "function")
    arguments = first_child_by_field_name(node, "arguments")
    if function_node is None or arguments is None:  # pragma: no cover - defensive
        return None
    text = node_text(source, function_node)
    simple_name = text.split("::")[-1].split(".")[-1].split("->")[-1]
    return (
        text,
        node_span(file_path, source, function_node),
        _argument_count(arguments),
        simple_name,
        function_node.type == "identifier",
    )


def _resolve_call_key(
    file_path: str,
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    scope: tuple[str, ...],
    simple_name: str,
    argument_count: int,
) -> str | None:
    for candidate_scope in _scope_resolution_order(scope):
        key = callable_index.get((candidate_scope, simple_name, argument_count))
        if key is not None:
            return _replace_symbol_key_file(key, file_path)
    return None


def _scope_resolution_order(scope: tuple[str, ...]) -> Iterator[tuple[str, ...]]:
    current = scope
    while True:
        yield current
        if not current:
            break
        current = current[:-1]


def _argument_count(arguments: Node) -> int:
    return len(arguments.named_children)


def _argument_count_for_parameters(declarator: Node) -> int:
    parameters = next(
        (
            child
            for child in declarator.named_children
            if child.type == "parameter_list"
        ),
        None,
    )
    if parameters is None:  # pragma: no cover - defensive for malformed callables
        return 0
    return sum(
        1
        for parameter in parameters.named_children
        if parameter.type == "parameter_declaration"
    )


def _call_shadow_names(node: Node, declarator: Node, source: bytes) -> set[str]:
    return {
        *_parameter_names(declarator, source),
        *_local_declaration_names(node, source),
    }


def _parameter_names(declarator: Node, source: bytes) -> set[str]:
    parameters = next(
        (
            child
            for child in declarator.named_children
            if child.type == "parameter_list"
        ),
        None,
    )
    if parameters is None:
        return set()
    names: set[str] = set()
    for parameter in parameters.named_children:
        if parameter.type != "parameter_declaration":
            continue
        name_node = _last_identifier(parameter)
        if name_node is not None:
            names.add(node_text(source, name_node).split("::")[-1])
    return names


def _local_declaration_names(node: Node, source: bytes) -> set[str]:
    names: set[str] = set()
    for child in node.named_children:
        if child.type == "declaration" and _function_declarator(child) is None:
            names.update(
                node_text(source, name_node).split("::")[-1]
                for name_node in _identifier_nodes(child)
            )
            continue
        if child.type in {"function_definition", "lambda_expression"}:
            continue
        names.update(_local_declaration_names(child, source))
    return names


def _last_identifier(node: Node) -> Node | None:
    identifiers = list(_identifier_nodes(node))
    if not identifiers:
        return None
    return identifiers[-1]


def _identifier_nodes(node: Node) -> Iterator[Node]:
    for child in node.named_children:
        if child.type in {"identifier", "field_identifier"}:
            yield child
        else:
            yield from _identifier_nodes(child)


def _replace_symbol_key_file(symbol_key: str, file_path: str) -> str:
    _, qualified_name = symbol_key.split("#", 1)
    return _symbol_key(file_path, qualified_name)


def _extract_fields(
    file_path: str,
    source: bytes,
    node: Node,
    scope: tuple[str, ...],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    for name_node in named_children(node, type_name="field_identifier"):
        name = node_text(source, name_node)
        qualified_name = _join_scope((*scope, name))
        key = _symbol_key(file_path, qualified_name)
        nodes.append(
            NodeFact(
                kind="field",
                language="cpp",
                name=name,
                qualified_name=qualified_name,
                symbol_key=key,
                file_path=file_path,
                span=node_span(file_path, source, name_node),
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
            _contains_edge(file_path, source, scope, qualified_name, name_node)
        )


def _namespace_name_node(node: Node) -> Node | None:
    for child in node.named_children:
        if child.type in {"namespace_identifier", "nested_namespace_specifier"}:
            return child
    return None  # pragma: no cover - defensive for malformed namespaces


def _type_name_node(node: Node) -> Node | None:
    for child in node.named_children:
        if child.type in {"type_identifier", "identifier"}:
            return child
    return None  # pragma: no cover - defensive for malformed type nodes


def _function_declarator(node: Node) -> Node | None:
    if node.type == "function_declarator":
        return node
    for child in node.named_children:
        result = _function_declarator(child)
        if result is not None:
            return result
    return None  # pragma: no cover - absence is covered through callers


def _declarator_name_node(node: Node) -> Node | None:
    for child in node.named_children:
        if child.type in {
            "identifier",
            "field_identifier",
            "qualified_identifier",
            "destructor_name",
        }:
            return child
    return None  # pragma: no cover - defensive for malformed declarators


def _callable_signature(declarator: Node, source: bytes) -> str:
    parameters = next(
        (
            child
            for child in declarator.named_children
            if child.type == "parameter_list"
        ),
        None,
    )
    if parameters is None:  # pragma: no cover - defensive for malformed callables
        return "()"
    parameter_types = [
        _parameter_type(parameter, source)
        for parameter in parameters.named_children
        if parameter.type == "parameter_declaration"
    ]
    return f"({','.join(parameter_types)})"


def _parameter_type(node: Node, source: bytes) -> str:
    if not node.named_children:  # pragma: no cover - defensive for malformed params
        return "unknown"
    parts: list[str] = []
    for child in node.named_children:
        if child.type in {
            "primitive_type",
            "type_identifier",
            "qualified_identifier",
            "type_qualifier",
            "sized_type_specifier",
        }:
            parts.append(node_text(source, child))
        elif child.type in {
            "reference_declarator",
            "pointer_declarator",
            "abstract_reference_declarator",
            "abstract_pointer_declarator",
        }:
            parts.append(_declarator_prefix(child, source))
    if not parts:  # pragma: no cover - defensive for unusual parameter nodes
        parts = [node_text(source, node.named_children[0])]
    return "".join(parts).replace(" ", "")


def _declarator_prefix(node: Node, source: bytes) -> str:
    if not node.named_children:
        return node_text(source, node)
    first_named = node.named_children[0]
    return source[node.start_byte : first_named.start_byte].decode("utf-8").strip()


def _qualified_callable_name(scope: tuple[str, ...], name: str, signature: str) -> str:
    if "::" in name and scope:
        namespace_prefix = (
            "::".join(scope[:-1])
            if scope[-1] in name.split("::")
            else _join_scope(scope)
        )
        return (
            f"{namespace_prefix}::{name}{signature}"
            if namespace_prefix
            else f"{name}{signature}"
        )
    return _join_scope((*scope, f"{name}{signature}"))


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
    parent_scope: tuple[str, ...],
    child_qualified_name: str,
    node: Node,
) -> EdgeFact:
    return EdgeFact(
        kind="contains",
        src_key=_symbol_key(file_path, _join_scope(parent_scope)),
        dst_key=_symbol_key(file_path, child_qualified_name),
        unresolved_src=None,
        unresolved_dst=None,
        file_path=file_path,
        span=node_span(file_path, source, node),
        confidence=1.0,
        extractor=EXTRACTOR,
    )


def _is_type_node(node: Node) -> bool:
    return node.type in {"class_specifier", "struct_specifier", "enum_specifier"}


def _has_node(nodes: list[NodeFact], key: str) -> bool:
    return any(node.symbol_key == key for node in nodes)


def _join_scope(parts: tuple[str, ...]) -> str:
    return "::".join(part for part in parts if part)


def _symbol_key(file_path: str, local_name: str) -> str:
    return f"cpp:{file_path}#{local_name}"
