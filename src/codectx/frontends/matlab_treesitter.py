"""MATLAB Tree-sitter frontend."""

from __future__ import annotations

from collections.abc import Iterator

import tree_sitter_matlab
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
)
from codectx.source.spans import SourceSpan, byte_range_to_span
from codectx.source.tokens import estimate_token_count

EXTRACTOR = "treesitter-matlab"


class MatlabTreeSitterFrontend:
    """Tree-sitter based MATLAB frontend."""

    language = "matlab"

    def __init__(self, parser: Parser | None = None) -> None:
        """Create a MATLAB frontend with an optional parser override."""
        self._parser = parser or make_parser(
            make_language(tree_sitter_matlab.language())
        )

    def extract(self, file_path: str, source: bytes) -> ExtractedFacts:
        """Extract MATLAB graph facts from source."""
        parsed = parse_source(self._parser, source)
        diagnostics = _parser_diagnostics(file_path, source, parsed.root)
        nodes: list[NodeFact] = []
        edges: list[EdgeFact] = []
        occurrences: list[OccurrenceFact] = []
        chunks: list[ChunkFact] = []
        callable_index = _callable_resolution_index(file_path, source, parsed.root)
        type_index = _type_resolution_index(file_path, source, parsed.root)

        for child in parsed.root.named_children:
            if _is_import_command(child, source):
                _extract_import(file_path, source, child, edges, occurrences)
            elif child.type == "class_definition":
                _extract_class(
                    file_path=file_path,
                    source=source,
                    node=child,
                    callable_index=callable_index,
                    type_index=type_index,
                    nodes=nodes,
                    edges=edges,
                    occurrences=occurrences,
                    chunks=chunks,
                )
            elif child.type == "function_definition":
                _extract_function(
                    file_path=file_path,
                    source=source,
                    node=child,
                    scope=(),
                    owner_key=None,
                    callable_index=callable_index,
                    type_index=type_index,
                    nodes=nodes,
                    edges=edges,
                    occurrences=occurrences,
                    chunks=chunks,
                )

        script_nodes = _script_nodes(parsed.root, source)
        if script_nodes:
            chunks.append(
                _source_chunk_for_nodes(
                    file_path=file_path,
                    source=source,
                    nodes=script_nodes,
                )
            )
            _extract_script_calls(
                file_path=file_path,
                source=source,
                node=parsed.root,
                edges=edges,
                occurrences=occurrences,
            )
        elif not chunks:
            chunks.append(
                _source_chunk(file_path=file_path, source=source, node=parsed.root)
            )
            _extract_script_calls(
                file_path=file_path,
                source=source,
                node=parsed.root,
                edges=edges,
                occurrences=occurrences,
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
            message=f"MATLAB parse error at {node.type}",
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
            message="MATLAB parse error",
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
    target_node = _first_named_child(node, {"command_argument"})
    if target_node is None:
        return
    target = node_text(source, target_node)
    edges.append(
        EdgeFact(
            kind="imports",
            src_key=None,
            dst_key=None,
            unresolved_src=file_path,
            unresolved_dst=target,
            file_path=file_path,
            span=node_span(file_path, source, node),
            confidence=0.7,
            extractor=EXTRACTOR,
        )
    )
    occurrences.append(
        OccurrenceFact(
            file_path=file_path,
            role="import",
            text=target,
            span=node_span(file_path, source, target_node),
            node_key=None,
            resolved_key=None,
            confidence=0.7,
            extractor=EXTRACTOR,
        )
    )


def _extract_class(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    type_index: dict[str, str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    name_node = _first_identifier(node)
    if name_node is None:  # pragma: no cover - defensive for malformed classes
        return
    name = node_text(source, name_node)
    key = _symbol_key(file_path, name)
    nodes.append(
        NodeFact(
            kind="type",
            language="matlab",
            name=name,
            qualified_name=name,
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
    _extract_superclasses(
        file_path=file_path,
        source=source,
        class_node=node,
        owner_key=key,
        type_index=type_index,
        edges=edges,
        occurrences=occurrences,
    )

    for child in node.named_children:
        if child.type == "properties":
            _extract_properties(
                file_path=file_path,
                source=source,
                node=child,
                owner_name=name,
                owner_key=key,
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
            )
        elif child.type == "methods":
            for method in child.named_children:
                if method.type == "function_definition":
                    _extract_function(
                        file_path=file_path,
                        source=source,
                        node=method,
                        scope=(name,),
                        owner_key=key,
                        callable_index=callable_index,
                        type_index=type_index,
                        nodes=nodes,
                        edges=edges,
                        occurrences=occurrences,
                        chunks=chunks,
                    )


def _extract_properties(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    owner_name: str,
    owner_key: str,
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    for property_node in node.named_children:
        if property_node.type != "property":
            continue
        name_node = _first_identifier(property_node)
        if name_node is None:
            continue
        name = node_text(source, name_node)
        local_name = f"{owner_name}.{name}"
        key = _symbol_key(file_path, local_name)
        nodes.append(
            NodeFact(
                kind="field",
                language="matlab",
                name=name,
                qualified_name=local_name,
                symbol_key=key,
                file_path=file_path,
                span=node_span(file_path, source, property_node),
                confidence=1.0,
                extractor=EXTRACTOR,
                metadata={"declaration_kind": "property"},
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
                node=property_node,
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
                span=node_span(file_path, source, property_node),
                confidence=1.0,
                extractor=EXTRACTOR,
            )
        )


def _extract_function(
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
    name_node = _function_name_node(node)
    if name_node is None:  # pragma: no cover - defensive for malformed functions
        return
    name = node_text(source, name_node)
    signature = _function_signature(node, source)
    local_name = ".".join((*scope, f"{name}{signature}"))
    key = _symbol_key(file_path, local_name)
    nodes.append(
        NodeFact(
            kind="callable",
            language="matlab",
            name=name,
            qualified_name=local_name,
            symbol_key=key,
            file_path=file_path,
            span=node_span(file_path, source, node),
            confidence=1.0,
            extractor=EXTRACTOR,
            metadata={"callable_kind": "function_definition"},
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
        edges.append(
            EdgeFact(
                kind="contains",
                src_key=owner_key,
                dst_key=key,
                unresolved_src=None,
                unresolved_dst=None,
                file_path=file_path,
                span=node_span(file_path, source, node),
                confidence=1.0,
                extractor=EXTRACTOR,
            )
        )
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


def _extract_superclasses(
    *,
    file_path: str,
    source: bytes,
    class_node: Node,
    owner_key: str,
    type_index: dict[str, str],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
) -> None:
    superclasses = _first_named_child(class_node, {"superclasses"})
    if superclasses is None:
        return
    for property_name in _descendants_of_type(superclasses, "property_name"):
        text = node_text(source, property_name)
        resolved_key = type_index.get(text)
        confidence = 0.7 if resolved_key is not None else 0.5
        occurrences.append(
            OccurrenceFact(
                file_path=file_path,
                role="type_reference",
                text=text,
                span=node_span(file_path, source, property_name),
                node_key=owner_key,
                resolved_key=resolved_key,
                confidence=confidence,
                extractor=EXTRACTOR,
                metadata={"reference_kind": "superclass"},
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
                span=node_span(file_path, source, property_name),
                confidence=confidence,
                extractor=EXTRACTOR,
                metadata={"reference_kind": "superclass"},
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
                metadata={
                    "argument_count": argument_count,
                    "call_kind": "function_call",
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
                    "call_kind": "function_call",
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


def _extract_script_calls(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
) -> None:
    for call in _call_like_nodes(node):
        call_info = _call_info(file_path, source, call)
        if call_info is None:
            continue
        text, text_span, argument_count, _, _ = call_info
        occurrences.append(
            OccurrenceFact(
                file_path=file_path,
                role="call",
                text=text,
                span=text_span,
                node_key=None,
                resolved_key=None,
                confidence=0.35,
                extractor=EXTRACTOR,
                metadata={
                    "argument_count": argument_count,
                    "call_kind": "function_call",
                },
            )
        )
        edges.append(
            EdgeFact(
                kind="calls",
                src_key=None,
                dst_key=None,
                unresolved_src=file_path,
                unresolved_dst=text,
                file_path=file_path,
                span=node_span(file_path, source, call),
                confidence=0.35,
                extractor=EXTRACTOR,
                metadata={
                    "argument_count": argument_count,
                    "call_kind": "function_call",
                    "call_text": text,
                },
            )
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
        if child.type == "function_call":
            yield child
            continue
        if child.type in {"class_definition", "function_definition"}:
            continue
        yield from _call_like_nodes(child)


def _source_chunk(*, file_path: str, source: bytes, node: Node) -> ChunkFact:
    return make_chunk(
        file_path=file_path,
        node_key=None,
        kind="source",
        source=source,
        node=node,
        metadata={"node_kind": "source_file", "fallback": True},
    )


def _source_chunk_for_nodes(
    *, file_path: str, source: bytes, nodes: list[Node]
) -> ChunkFact:
    start_byte = min(node.start_byte for node in nodes)
    end_byte = max(node.end_byte for node in nodes)
    span = byte_range_to_span(file_path, source, start_byte, end_byte)
    text = source[start_byte:end_byte].decode("utf-8")
    return ChunkFact(
        file_path=file_path,
        node_key=None,
        kind="source",
        start_line=span.start_line,
        end_line=span.end_line,
        text=text,
        token_estimate=estimate_token_count(text),
        metadata={"node_kind": "script", "fallback": True},
    )


def _script_nodes(root: Node, source: bytes) -> list[Node]:
    return [
        child
        for child in root.named_children
        if child.type
        not in {
            "class_definition",
            "function_definition",
        }
        and not _is_import_command(child, source)
    ]


def _is_import_command(node: Node, source: bytes) -> bool:
    if node.type != "command":
        return False
    name_node = _first_named_child(node, {"command_name"})
    if name_node is None:
        return False
    return source[name_node.start_byte : name_node.end_byte].decode("utf-8") == "import"


def _call_info(
    file_path: str, source: bytes, node: Node
) -> tuple[str, SourceSpan, int, str, str | None] | None:
    name_node = _first_identifier(node)
    arguments = _first_named_child(node, {"arguments"})
    if name_node is None:
        return None
    simple_name = node_text(source, name_node)
    text_node = node
    receiver = None
    parent = node.parent
    if parent is not None and parent.type == "field_expression":
        text_node = parent
        text = node_text(source, parent)
        receiver = text.rsplit(f".{simple_name}", 1)[0]
        text = text.split("(", 1)[0]
    else:
        text = simple_name
    return (
        text,
        node_span(file_path, source, text_node),
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
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
) -> str | None:
    if receiver is not None:
        return None
    if scope:
        key = callable_index.get((scope, simple_name, argument_count + 1))
        if key is not None:
            return key
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
        if child.type == "class_definition":
            class_name_node = _first_identifier(child)
            if class_name_node is None:
                continue
            class_name = node_text(source, class_name_node)
            for method in _class_methods(child):
                _record_callable_candidate(
                    file_path=file_path,
                    source=source,
                    node=method,
                    scope=(class_name,),
                    candidates=candidates,
                )
        elif child.type == "function_definition":
            _record_callable_candidate(
                file_path=file_path,
                source=source,
                node=child,
                scope=(),
                candidates=candidates,
            )
    return {key: keys[0] for key, keys in candidates.items() if len(keys) == 1}


def _record_callable_candidate(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    scope: tuple[str, ...],
    candidates: dict[tuple[tuple[str, ...], str, int], list[str]],
) -> None:
    name_node = _function_name_node(node)
    if name_node is None:
        return
    name = node_text(source, name_node)
    local_name = ".".join((*scope, f"{name}{_function_signature(node, source)}"))
    candidates.setdefault(
        (scope, name, _argument_count_from_definition(node)), []
    ).append(_symbol_key(file_path, local_name))


def _type_resolution_index(file_path: str, source: bytes, root: Node) -> dict[str, str]:
    candidates: dict[str, list[str]] = {}
    for child in root.named_children:
        if child.type != "class_definition":
            continue
        name_node = _first_identifier(child)
        if name_node is None:
            continue
        name = node_text(source, name_node)
        candidates.setdefault(name, []).append(_symbol_key(file_path, name))
    return {name: keys[0] for name, keys in candidates.items() if len(keys) == 1}


def _class_methods(node: Node) -> Iterator[Node]:
    for child in node.named_children:
        if child.type != "methods":
            continue
        for method in child.named_children:
            if method.type == "function_definition":
                yield method


def _function_name_node(node: Node) -> Node | None:
    children = [child for child in node.named_children if child.type == "identifier"]
    if len(children) == 1:
        return children[0]
    if len(children) > 1:
        return children[1]
    return None


def _function_signature(node: Node, source: bytes) -> str:
    arguments = _first_named_child(node, {"function_arguments"})
    if arguments is None:
        return "()"
    return (
        f"({','.join(node_text(source, child) for child in arguments.named_children)})"
    )


def _argument_count_from_definition(node: Node) -> int:
    arguments = _first_named_child(node, {"function_arguments"})
    return 0 if arguments is None else len(arguments.named_children)


def _first_identifier(node: Node) -> Node | None:
    return _first_named_child(node, {"identifier"})


def _first_named_child(node: Node, types: set[str]) -> Node | None:
    return next((child for child in node.named_children if child.type in types), None)


def _descendants_of_type(node: Node, type_name: str) -> Iterator[Node]:
    for child in node.named_children:
        if child.type == type_name:
            yield child
        yield from _descendants_of_type(child, type_name)


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


def _symbol_key(file_path: str, local_name: str) -> str:
    return f"matlab:{file_path}#{local_name}"
