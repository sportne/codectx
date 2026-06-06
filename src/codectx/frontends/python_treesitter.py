"""Python Tree-sitter frontend."""

from __future__ import annotations

from collections.abc import Iterator

import tree_sitter_python
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
    node_span,
    node_text,
    parse_source,
    walk_named,
)
from codectx.source.spans import SourceSpan

EXTRACTOR = "treesitter-python"


class PythonTreeSitterFrontend:
    """Tree-sitter based Python frontend."""

    language = "python"

    def __init__(self, parser: Parser | None = None) -> None:
        """Create a Python frontend with an optional parser override."""
        self._parser = parser or make_parser(
            make_language(tree_sitter_python.language())
        )

    def extract(self, file_path: str, source: bytes) -> ExtractedFacts:
        """Extract Python graph facts from source."""
        parsed = parse_source(self._parser, source)
        diagnostics = _parser_diagnostics(file_path, source, parsed.root)
        nodes: list[NodeFact] = []
        edges: list[EdgeFact] = []
        occurrences: list[OccurrenceFact] = []
        chunks: list[ChunkFact] = []
        callable_index = _callable_resolution_index(file_path, source, parsed.root)
        type_index = _type_resolution_index(file_path, source, parsed.root)

        for child in parsed.root.named_children:
            if child.type in {"import_statement", "import_from_statement"}:
                _extract_import(file_path, source, child, edges, occurrences)
                continue
            definition = _definition_node(child)
            if definition is None:
                continue
            if definition.type == "class_definition":
                _extract_class(
                    file_path=file_path,
                    source=source,
                    node=definition,
                    scope=(),
                    callable_index=callable_index,
                    type_index=type_index,
                    nodes=nodes,
                    edges=edges,
                    occurrences=occurrences,
                    chunks=chunks,
                )
            elif definition.type == "function_definition":
                _extract_callable(
                    file_path=file_path,
                    source=source,
                    node=definition,
                    scope=(),
                    owner_key=None,
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
            message=f"Python parse error at {node.type}",
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
            message="Python parse error",
            extractor=EXTRACTOR,
            span=node_span(file_path, source, root),
            code="parse_error",
        )
    ]


def _extract_import(
    file_path: str,
    source: bytes,
    node: Node,
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
) -> None:
    for import_text, import_span, alias in _import_targets(file_path, source, node):
        edges.append(
            EdgeFact(
                kind="imports",
                src_key=None,
                dst_key=None,
                unresolved_src=file_path,
                unresolved_dst=import_text,
                file_path=file_path,
                span=node_span(file_path, source, node),
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


def _import_targets(
    file_path: str, source: bytes, node: Node
) -> Iterator[tuple[str, SourceSpan, str | None]]:
    if node.type == "import_statement":
        for child in node.named_children:
            if child.type == "dotted_name":
                yield (
                    node_text(source, child),
                    node_span(file_path, source, child),
                    None,
                )
            elif child.type == "aliased_import":
                target = _first_named_child(child, {"dotted_name"})
                alias = _last_identifier_text(source, child)
                if target is not None:
                    yield (
                        node_text(source, target),
                        node_span(file_path, source, target),
                        alias,
                    )
        return

    if node.type != "import_from_statement":
        return
    module_node = _first_named_child(node, {"dotted_name", "relative_import"})
    module = "" if module_node is None else node_text(source, module_node)
    import_seen = False
    for child in node.named_children:
        if child == module_node:
            continue
        if child.type in {"dotted_name", "aliased_import"}:
            import_seen = True
            imported_node = (
                _first_named_child(child, {"dotted_name"})
                if child.type == "aliased_import"
                else child
            )
            if imported_node is None:
                continue
            imported = node_text(source, imported_node)
            alias = (
                _last_identifier_text(source, child)
                if child.type == "aliased_import"
                else None
            )
            yield (
                _join_import(module, imported),
                node_span(file_path, source, imported_node),
                alias,
            )
    if not import_seen and module_node is not None:
        yield module, node_span(file_path, source, module_node), None


def _extract_class(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    scope: tuple[str, ...],
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    type_index: dict[str, str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    name_node = first_child_by_field_name(node, "name") or _first_identifier(node)
    if name_node is None:  # pragma: no cover - defensive for malformed classes
        return
    name = node_text(source, name_node)
    local_parts = (*scope, name)
    local_name = ".".join(local_parts)
    key = _symbol_key(file_path, local_name)
    nodes.append(
        NodeFact(
            kind="type",
            language="python",
            name=name,
            qualified_name=local_name,
            symbol_key=key,
            file_path=file_path,
            span=node_span(file_path, source, node),
            confidence=1.0,
            extractor=EXTRACTOR,
            metadata={"declaration_kind": "class_definition"},
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
        edges.append(_contains_edge(file_path, source, scope, local_name, node))

    _extract_base_type_references(
        file_path=file_path,
        source=source,
        class_node=node,
        owner_key=key,
        type_index=type_index,
        edges=edges,
        occurrences=occurrences,
    )

    body = first_child_by_field_name(node, "body")
    if body is None:
        return
    for child in body.named_children:
        definition = _definition_node(child)
        if definition is None:
            if child.type == "expression_statement":
                _extract_class_field(
                    file_path=file_path,
                    source=source,
                    node=child,
                    owner_parts=local_parts,
                    owner_key=key,
                    nodes=nodes,
                    edges=edges,
                    occurrences=occurrences,
                    chunks=chunks,
                )
            continue
        if definition.type == "function_definition":
            _extract_callable(
                file_path=file_path,
                source=source,
                node=definition,
                scope=local_parts,
                owner_key=key,
                callable_index=callable_index,
                type_index=type_index,
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
            )
        elif definition.type == "class_definition":
            _extract_class(
                file_path=file_path,
                source=source,
                node=definition,
                scope=local_parts,
                callable_index=callable_index,
                type_index=type_index,
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
    scope: tuple[str, ...],
    owner_key: str | None,
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    type_index: dict[str, str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    name_node = first_child_by_field_name(node, "name") or _first_identifier(node)
    if name_node is None:  # pragma: no cover - defensive for malformed callables
        return
    name = node_text(source, name_node)
    signature = _callable_signature(node, source)
    local_name = ".".join((*scope, f"{name}{signature}"))
    key = _symbol_key(file_path, local_name)
    callable_kind = "async_function" if _is_async(node) else "function"
    nodes.append(
        NodeFact(
            kind="callable",
            language="python",
            name=name,
            qualified_name=local_name,
            symbol_key=key,
            file_path=file_path,
            span=node_span(file_path, source, node),
            confidence=1.0,
            extractor=EXTRACTOR,
            metadata={"callable_kind": callable_kind},
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
    if owner_key is not None:
        edges.append(_contains_edge(file_path, source, scope, local_name, node))
    _extract_call_like_occurrences(
        file_path=file_path,
        source=source,
        node=node,
        source_key=key,
        scope=scope,
        callable_index=callable_index,
        type_index=type_index,
        edges=edges,
        occurrences=occurrences,
    )


def _extract_class_field(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    owner_parts: tuple[str, ...],
    owner_key: str,
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    assignment = _first_named_child(node, {"assignment"})
    if assignment is None or not assignment.named_children:
        return
    name_node = assignment.named_children[0]
    if name_node.type != "identifier":
        return
    name = node_text(source, name_node)
    local_name = ".".join((*owner_parts, name))
    key = _symbol_key(file_path, local_name)
    nodes.append(
        NodeFact(
            kind="field",
            language="python",
            name=name,
            qualified_name=local_name,
            symbol_key=key,
            file_path=file_path,
            span=node_span(file_path, source, assignment),
            confidence=0.9,
            extractor=EXTRACTOR,
            metadata={"declaration_kind": "class_assignment"},
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
        EdgeFact(
            kind="contains",
            src_key=owner_key,
            dst_key=key,
            unresolved_src=None,
            unresolved_dst=None,
            file_path=file_path,
            span=node_span(file_path, source, assignment),
            confidence=1.0,
            extractor=EXTRACTOR,
        )
    )


def _extract_base_type_references(
    *,
    file_path: str,
    source: bytes,
    class_node: Node,
    owner_key: str,
    type_index: dict[str, str],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
) -> None:
    bases = _first_named_child(class_node, {"argument_list"})
    if bases is None:
        return
    for base in bases.named_children:
        text = node_text(source, base)
        resolved_key = type_index.get(text)
        confidence = 0.7 if resolved_key is not None else 0.5
        occurrences.append(
            OccurrenceFact(
                file_path=file_path,
                role="type_reference",
                text=text,
                span=node_span(file_path, source, base),
                node_key=owner_key,
                resolved_key=resolved_key,
                confidence=confidence,
                extractor=EXTRACTOR,
                metadata={"reference_kind": "base_class"},
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
                span=node_span(file_path, source, base),
                confidence=confidence,
                extractor=EXTRACTOR,
                metadata={"reference_kind": "base_class"},
            )
        )


def _extract_call_like_occurrences(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    source_key: str,
    scope: tuple[str, ...],
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    type_index: dict[str, str],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
) -> None:
    for call in _call_like_nodes(node):
        call_info = _call_info(file_path, source, call)
        if call_info is None:  # pragma: no cover - defensive for malformed calls
            continue
        text, text_span, argument_count, simple_name, receiver = call_info
        resolved_key = _resolve_call(
            scope=scope,
            simple_name=simple_name,
            argument_count=argument_count,
            receiver=receiver,
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
                metadata={"argument_count": argument_count, "call_kind": "call"},
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
                    "call_kind": "call",
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


def _call_like_nodes(node: Node) -> Iterator[Node]:
    for child in node.named_children:
        if child.type == "call":
            yield child
            continue
        if child.type in {"class_definition", "function_definition"}:
            continue
        yield from _call_like_nodes(child)


def _call_info(
    file_path: str, source: bytes, node: Node
) -> tuple[str, SourceSpan, int, str, str | None] | None:
    target = node.named_children[0] if node.named_children else None
    arguments = next(
        (child for child in node.named_children if child.type == "argument_list"),
        None,
    )
    if target is None or arguments is None:
        return None
    if target.type not in {"identifier", "attribute"}:
        return None
    simple_name = _last_identifier_text(source, target)
    if simple_name is None:
        return None
    text = node_text(source, target)
    receiver = _attribute_receiver_text(source, target)
    return (
        text,
        node_span(file_path, source, target),
        _argument_count(arguments),
        simple_name,
        receiver,
    )


def _resolve_call(
    *,
    scope: tuple[str, ...],
    simple_name: str,
    argument_count: int,
    receiver: str | None,
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
) -> str | None:
    if receiver == "self" and scope:
        return callable_index.get((scope, simple_name, argument_count + 1))
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

    def visit(parent: Node, scope: tuple[str, ...]) -> None:
        for child in parent.named_children:
            definition = _definition_node(child)
            if definition is None:
                continue
            if definition.type == "class_definition":
                name_node = first_child_by_field_name(
                    definition, "name"
                ) or _first_identifier(definition)
                if name_node is None:
                    continue
                body = first_child_by_field_name(definition, "body")
                if body is not None:
                    visit(body, (*scope, node_text(source, name_node)))
            elif definition.type == "function_definition":
                name_node = first_child_by_field_name(
                    definition, "name"
                ) or _first_identifier(definition)
                if name_node is None:
                    continue
                name = node_text(source, name_node)
                local_name = ".".join(
                    (*scope, f"{name}{_callable_signature(definition, source)}")
                )
                candidates.setdefault(
                    (scope, name, _parameter_count(definition)), []
                ).append(_symbol_key(file_path, local_name))

    visit(root, ())
    return {key: keys[0] for key, keys in candidates.items() if len(keys) == 1}


def _type_resolution_index(file_path: str, source: bytes, root: Node) -> dict[str, str]:
    candidates: dict[str, list[str]] = {}

    def visit(parent: Node, scope: tuple[str, ...]) -> None:
        for child in parent.named_children:
            definition = _definition_node(child)
            if definition is None or definition.type != "class_definition":
                continue
            name_node = first_child_by_field_name(
                definition, "name"
            ) or _first_identifier(definition)
            if name_node is None:
                continue
            name = node_text(source, name_node)
            local_name = ".".join((*scope, name))
            candidates.setdefault(name, []).append(_symbol_key(file_path, local_name))
            body = first_child_by_field_name(definition, "body")
            if body is not None:
                visit(body, (*scope, name))

    visit(root, ())
    return {name: keys[0] for name, keys in candidates.items() if len(keys) == 1}


def _callable_signature(node: Node, source: bytes) -> str:
    parameters = _first_named_child(node, {"parameters"})
    if parameters is None:
        return "()"
    return f"({','.join(_parameter_names(parameters, source))})"


def _parameter_count(node: Node) -> int:
    parameters = _first_named_child(node, {"parameters"})
    return 0 if parameters is None else len(list(_parameter_names(parameters, b"")))


def _parameter_names(parameters: Node, source: bytes) -> Iterator[str]:
    for child in parameters.named_children:
        if child.type == "identifier":
            yield node_text(source, child) if source else ""
        elif child.type in {
            "typed_parameter",
            "default_parameter",
            "typed_default_parameter",
        }:
            name = _first_identifier(child)
            if name is not None:
                yield node_text(source, name) if source else ""
        elif child.type in {"list_splat_pattern", "dictionary_splat_pattern"}:
            name = _first_identifier(child)
            if name is not None:
                prefix = "**" if child.type == "dictionary_splat_pattern" else "*"
                yield f"{prefix}{node_text(source, name)}" if source else ""


def _argument_count(arguments: Node) -> int:
    return len(arguments.named_children)


def _is_async(node: Node) -> bool:
    return any(child.type == "async" for child in node.children)


def _first_identifier(node: Node) -> Node | None:
    return _first_named_child(node, {"identifier"})


def _definition_node(node: Node) -> Node | None:
    if node.type in {"class_definition", "function_definition"}:
        return node
    if node.type != "decorated_definition":
        return None
    return _first_named_child(node, {"class_definition", "function_definition"})


def _first_named_child(node: Node, types: set[str]) -> Node | None:
    return next((child for child in node.named_children if child.type in types), None)


def _last_identifier_text(source: bytes, node: Node) -> str | None:
    identifiers = [child for child in walk_named(node) if child.type == "identifier"]
    if not identifiers:
        return None
    return node_text(source, identifiers[-1])


def _attribute_receiver_text(source: bytes, node: Node) -> str | None:
    if node.type != "attribute" or not node.named_children:
        return None
    receiver = node.named_children[0]
    return node_text(source, receiver)


def _join_import(module: str, imported: str) -> str:
    if not module:
        return imported
    if module.endswith("."):
        return f"{module}{imported}"
    return f"{module}.{imported}"


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


def _symbol_key(file_path: str, local_name: str) -> str:
    return f"python:{file_path}#{local_name}"
