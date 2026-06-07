"""Rust Tree-sitter frontend."""

from __future__ import annotations

from collections.abc import Iterator

import tree_sitter_rust
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
from codectx.source.spans import SourceSpan

EXTRACTOR = "treesitter-rust"


class RustTreeSitterFrontend:
    """Tree-sitter based Rust frontend."""

    language = "rust"

    def __init__(self, parser: Parser | None = None) -> None:
        """Create a Rust frontend with an optional parser override."""
        self._parser = parser or make_parser(make_language(tree_sitter_rust.language()))

    def extract(self, file_path: str, source: bytes) -> ExtractedFacts:
        """Extract Rust graph facts from source."""
        parsed = parse_source(self._parser, source)
        diagnostics = _parser_diagnostics(file_path, source, parsed.root)
        nodes: list[NodeFact] = []
        edges: list[EdgeFact] = []
        occurrences: list[OccurrenceFact] = []
        chunks: list[ChunkFact] = []
        type_index = _type_resolution_index(file_path, source, parsed.root)
        callable_index = _callable_resolution_index(file_path, source, parsed.root)

        _extract_items(
            file_path=file_path,
            source=source,
            items=parsed.root.named_children,
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


def _extract_items(
    *,
    file_path: str,
    source: bytes,
    items: list[Node],
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    type_index: dict[str, str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    for item in items:
        if item.type == "mod_item":
            _extract_module(
                file_path=file_path,
                source=source,
                node=item,
                callable_index=callable_index,
                type_index=type_index,
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
            )
        elif item.type == "use_declaration":
            _extract_use(file_path, source, item, edges, occurrences)
        elif item.type in _RUST_TYPE_ITEM_TYPES:
            _extract_type_item(
                file_path=file_path,
                source=source,
                node=item,
                type_index=type_index,
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
            )
        elif item.type == "function_item":
            _extract_callable(
                file_path=file_path,
                source=source,
                node=item,
                owner_name=None,
                callable_index=callable_index,
                type_index=type_index,
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
            )
        elif item.type == "impl_item":
            _extract_impl_item(
                file_path=file_path,
                source=source,
                node=item,
                callable_index=callable_index,
                type_index=type_index,
                nodes=nodes,
                edges=edges,
                occurrences=occurrences,
                chunks=chunks,
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
            message=f"Rust parse error at {node.type}",
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
            message="Rust parse error",
            extractor=EXTRACTOR,
            span=node_span(file_path, source, root),
            code="parse_error",
        )
    ]


def _extract_module(
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
    name_node = _first_named_child(node, {"identifier"})
    if name_node is None:  # pragma: no cover - malformed module item
        return
    name = node_text(source, name_node)
    key = _symbol_key(file_path, name)
    nodes.append(
        NodeFact(
            kind="namespace",
            language="rust",
            name=name,
            qualified_name=name,
            symbol_key=key,
            file_path=file_path,
            span=node_span(file_path, source, node),
            confidence=1.0,
            extractor=EXTRACTOR,
            metadata={"declaration_kind": "mod_item"},
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
    declaration_list = _first_named_child(node, {"declaration_list"})
    if declaration_list is not None:
        _extract_items(
            file_path=file_path,
            source=source,
            items=declaration_list.named_children,
            callable_index=callable_index,
            type_index=type_index,
            nodes=nodes,
            edges=edges,
            occurrences=occurrences,
            chunks=chunks,
        )


def _extract_use(
    file_path: str,
    source: bytes,
    node: Node,
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
) -> None:
    target = _use_target_text(source, node)
    edges.append(
        EdgeFact(
            kind="imports",
            src_key=None,
            dst_key=None,
            unresolved_src=file_path,
            unresolved_dst=target,
            file_path=file_path,
            span=node_span(file_path, source, node),
            confidence=0.8,
            extractor=EXTRACTOR,
        )
    )
    occurrences.append(
        OccurrenceFact(
            file_path=file_path,
            role="import",
            text=target,
            span=node_span(file_path, source, node),
            node_key=None,
            resolved_key=None,
            confidence=0.8,
            extractor=EXTRACTOR,
        )
    )


def _extract_type_item(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    type_index: dict[str, str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    name_node = _first_named_child(node, {"type_identifier"})
    if name_node is None:  # pragma: no cover - malformed type item
        return
    name = node_text(source, name_node)
    key = _symbol_key(file_path, name)
    nodes.append(
        NodeFact(
            kind="type",
            language="rust",
            name=name,
            qualified_name=name,
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
    if node.type == "struct_item":
        _extract_struct_fields(
            file_path=file_path,
            source=source,
            node=node,
            owner_name=name,
            owner_key=key,
            type_index=type_index,
            nodes=nodes,
            edges=edges,
            occurrences=occurrences,
            chunks=chunks,
        )
    elif node.type == "enum_item":
        _extract_enum_variants(
            file_path=file_path,
            source=source,
            node=node,
            owner_name=name,
            owner_key=key,
            type_index=type_index,
            nodes=nodes,
            edges=edges,
            occurrences=occurrences,
            chunks=chunks,
        )
    elif node.type == "trait_item":
        _extract_trait_signatures(
            file_path=file_path,
            source=source,
            node=node,
            owner_name=name,
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
        nodes=_type_reference_nodes(node),
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
    type_index: dict[str, str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    for field in _descendants_of_type(node, "field_declaration"):
        name_node = _first_named_child(field, {"field_identifier"})
        if name_node is None:
            continue
        _record_field(
            file_path=file_path,
            source=source,
            node=field,
            name_node=name_node,
            owner_name=owner_name,
            nodes=nodes,
            edges=edges,
            occurrences=occurrences,
            chunks=chunks,
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
    for index, field in enumerate(_tuple_struct_fields(node)):
        _record_field(
            file_path=file_path,
            source=source,
            node=field,
            name_node=field,
            owner_name=owner_name,
            nodes=nodes,
            edges=edges,
            occurrences=occurrences,
            chunks=chunks,
            field_name=str(index),
        )
        _extract_type_references(
            file_path=file_path,
            source=source,
            owner_key=owner_key,
            nodes=iter((field,)),
            type_index=type_index,
            edges=edges,
            occurrences=occurrences,
            reference_kind="field_type",
        )


def _extract_enum_variants(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    owner_name: str,
    owner_key: str,
    type_index: dict[str, str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    for variant in _descendants_of_type(node, "enum_variant"):
        name_node = _first_named_child(variant, {"identifier"})
        if name_node is None:  # pragma: no cover - malformed enum variant
            continue
        _record_field(
            file_path=file_path,
            source=source,
            node=variant,
            name_node=name_node,
            owner_name=owner_name,
            nodes=nodes,
            edges=edges,
            occurrences=occurrences,
            chunks=chunks,
        )
        _extract_type_references(
            file_path=file_path,
            source=source,
            owner_key=owner_key,
            nodes=_type_reference_nodes(variant),
            type_index=type_index,
            edges=edges,
            occurrences=occurrences,
            reference_kind="variant_payload",
        )


def _record_field(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    name_node: Node,
    owner_name: str,
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
    field_name: str | None = None,
) -> None:
    name = field_name or node_text(source, name_node)
    local_name = f"{owner_name}.{name}"
    key = _symbol_key(file_path, local_name)
    nodes.append(
        NodeFact(
            kind="field",
            language="rust",
            name=name,
            qualified_name=local_name,
            symbol_key=key,
            file_path=file_path,
            span=node_span(file_path, source, node),
            confidence=1.0,
            extractor=EXTRACTOR,
            metadata={"declaration_kind": node.type},
        )
    )
    occurrences.append(
        _field_definition_occurrence(file_path, source, name_node, key, name)
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
    edges.append(_contains_edge(file_path, source, owner_name, local_name, node))


def _extract_trait_signatures(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    owner_name: str,
    type_index: dict[str, str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
) -> None:
    for signature in _descendants_of_type(node, "function_signature_item"):
        _extract_callable(
            file_path=file_path,
            source=source,
            node=signature,
            owner_name=owner_name,
            callable_index={},
            type_index=type_index,
            nodes=nodes,
            edges=edges,
            occurrences=occurrences,
            chunks=chunks,
            callable_kind="trait_method",
        )


def _extract_impl_item(
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
    owner_name = _impl_owner_name(source, node)
    for function in node.named_children:
        if function.type == "declaration_list":
            for item in function.named_children:
                if item.type == "function_item":
                    _extract_callable(
                        file_path=file_path,
                        source=source,
                        node=item,
                        owner_name=owner_name,
                        callable_index=callable_index,
                        type_index=type_index,
                        nodes=nodes,
                        edges=edges,
                        occurrences=occurrences,
                        chunks=chunks,
                        callable_kind="impl_method",
                    )


def _extract_callable(
    *,
    file_path: str,
    source: bytes,
    node: Node,
    owner_name: str | None,
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    type_index: dict[str, str],
    nodes: list[NodeFact],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
    chunks: list[ChunkFact],
    callable_kind: str | None = None,
) -> None:
    name_node = _first_named_child(node, {"identifier"})
    if name_node is None:  # pragma: no cover - malformed callable item
        return
    name = node_text(source, name_node)
    signature = _callable_signature(node, source)
    local_name = (
        f"{owner_name}.{name}{signature}" if owner_name else f"{name}{signature}"
    )
    key = _symbol_key(file_path, local_name)
    nodes.append(
        NodeFact(
            kind="callable",
            language="rust",
            name=name,
            qualified_name=local_name,
            symbol_key=key,
            file_path=file_path,
            span=node_span(file_path, source, node),
            confidence=1.0,
            extractor=EXTRACTOR,
            metadata={"callable_kind": callable_kind or node.type, "owner": owner_name},
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
    if owner_name is not None:
        edges.append(_contains_edge(file_path, source, owner_name, local_name, node))
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
        scope=() if owner_name is None else (owner_name,),
        callable_index=callable_index,
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
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
    edges: list[EdgeFact],
    occurrences: list[OccurrenceFact],
) -> None:
    for call in _call_like_nodes(node):
        call_info = _call_info(file_path, source, call)
        if call_info is None:
            continue
        text, text_span, argument_count, simple_name, receiver, call_kind = call_info
        resolved_key = _resolve_call(
            scope=scope,
            simple_name=simple_name,
            argument_count=argument_count,
            receiver=receiver,
            callable_index=callable_index,
        )
        confidence = _call_confidence(resolved_key, call_kind)
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
                metadata={"argument_count": argument_count, "call_kind": call_kind},
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
                    "call_kind": call_kind,
                    "call_text": text,
                },
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
        simple_name = _last_identifier_text(source, type_node) or text
        if (
            not text
            or text == skip_name
            or simple_name == skip_name
            or simple_name in _RUST_BUILTIN_TYPES
            or (type_node.start_byte, type_node.end_byte) in seen
        ):
            continue
        seen.add((type_node.start_byte, type_node.end_byte))
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
        if child.type in {"call_expression", "macro_invocation"}:
            yield child
            continue
        if child.type in {
            "function_item",
            "function_signature_item",
        }:  # pragma: no cover
            continue
        yield from _call_like_nodes(child)


def _call_info(
    file_path: str, source: bytes, node: Node
) -> tuple[str, SourceSpan, int, str, str | None, str] | None:
    if not node.named_children:  # pragma: no cover - malformed call expression
        return None
    target = node.named_children[0]
    simple_name = _last_identifier_text(source, target)
    if simple_name is None:  # pragma: no cover - unsupported expression target
        return None
    text = node_text(source, target)
    receiver = _field_receiver_text(source, target)
    argument_count = _argument_count(node)
    return (
        text,
        node_span(file_path, source, target),
        argument_count,
        simple_name,
        receiver,
        node.type,
    )


def _resolve_call(
    *,
    scope: tuple[str, ...],
    simple_name: str,
    argument_count: int,
    receiver: str | None,
    callable_index: dict[tuple[tuple[str, ...], str, int], str],
) -> str | None:
    if receiver is not None and receiver != "self":
        return None
    if receiver == "self" and scope:
        key = callable_index.get((scope, simple_name, argument_count + 1))
        if key is not None:
            return key
        return None
    for candidate_scope in (scope, ()):
        key = callable_index.get((candidate_scope, simple_name, argument_count))
        if key is not None:
            return key
    return None


def _call_confidence(resolved_key: str | None, call_kind: str) -> float:
    if resolved_key is not None:
        return 0.75
    return 0.35 if call_kind == "macro_invocation" else 0.45


def _type_resolution_index(file_path: str, source: bytes, root: Node) -> dict[str, str]:
    candidates: dict[str, list[str]] = {}
    for node in _type_index_candidates(root.named_children):
        if node.type not in _RUST_TYPE_ITEM_TYPES:
            continue
        name_node = _first_named_child(node, {"type_identifier"})
        if name_node is None:  # pragma: no cover - malformed type item
            continue
        name = node_text(source, name_node)
        candidates.setdefault(name, []).append(_symbol_key(file_path, name))
    return {name: keys[0] for name, keys in candidates.items() if len(keys) == 1}


def _callable_resolution_index(
    file_path: str, source: bytes, root: Node
) -> dict[tuple[tuple[str, ...], str, int], str]:
    candidates: dict[tuple[tuple[str, ...], str, int], list[str]] = {}
    for node, owner_name in _callable_index_candidates(source, root):
        name_node = _first_named_child(node, {"identifier"})
        if name_node is None:  # pragma: no cover - malformed callable item
            continue
        name = node_text(source, name_node)
        scope = () if owner_name is None else (owner_name,)
        local_name = (
            f"{owner_name}.{name}{_callable_signature(node, source)}"
            if owner_name
            else f"{name}{_callable_signature(node, source)}"
        )
        candidates.setdefault((scope, name, _parameter_count(node)), []).append(
            _symbol_key(file_path, local_name)
        )
    return {key: keys[0] for key, keys in candidates.items() if len(keys) == 1}


def _callable_index_candidates(
    source: bytes, root: Node
) -> Iterator[tuple[Node, str | None]]:
    yield from _callable_index_items(source, root.named_children)


def _callable_index_items(
    source: bytes, items: list[Node]
) -> Iterator[tuple[Node, str | None]]:
    for item in items:
        if item.type == "function_item":
            yield item, None
        elif item.type == "impl_item":
            owner_name = _impl_owner_name(source, item)
            declaration_list = _first_named_child(item, {"declaration_list"})
            if declaration_list is None:
                continue
            for method in declaration_list.named_children:
                if method.type == "function_item":
                    yield method, owner_name
        elif item.type == "mod_item":
            declaration_list = _first_named_child(item, {"declaration_list"})
            if declaration_list is not None:
                yield from _callable_index_items(
                    source, declaration_list.named_children
                )


def _type_index_candidates(items: list[Node]) -> Iterator[Node]:
    for item in items:
        if item.type in _RUST_TYPE_ITEM_TYPES:
            yield item
        elif item.type == "mod_item":
            declaration_list = _first_named_child(item, {"declaration_list"})
            if declaration_list is not None:
                yield from _type_index_candidates(declaration_list.named_children)


def _impl_owner_name(source: bytes, node: Node) -> str | None:
    type_nodes = [
        child for child in node.named_children if child.type in _RUST_TYPE_NODE_TYPES
    ]
    if type_nodes:
        return _last_identifier_text(source, type_nodes[-1])
    return None


def _tuple_struct_fields(node: Node) -> Iterator[Node]:
    ordered_fields = _first_named_child(node, {"ordered_field_declaration_list"})
    if ordered_fields is None:
        return
    yield from (
        field
        for field in ordered_fields.named_children
        if field.type in _RUST_TYPE_NODE_TYPES
    )


def _type_reference_nodes(node: Node) -> Iterator[Node]:
    for child in node.named_children:
        if child.type == "generic_type":
            yield from _type_reference_nodes(child)
            continue
        if child.type in _RUST_TYPE_NODE_TYPES:
            yield child
            continue
        if child.type in {"mod_item", "use_declaration"}:  # pragma: no cover
            continue
        yield from _type_reference_nodes(child)


def _type_text(source: bytes, node: Node) -> str:
    return "".join(node_text(source, node).split())


def _use_target_text(source: bytes, node: Node) -> str:
    text = node_text(source, node).strip()
    if text.startswith("use "):
        text = text[4:]
    return text.rstrip(";")


def _callable_signature(node: Node, source: bytes) -> str:
    parameters = _first_named_child(node, {"parameters"})
    if parameters is None:
        return "()"
    types = [
        parameter_text
        for parameter in parameters.named_children
        for parameter_text in _parameter_type_texts(parameter, source)
    ]
    return f"({','.join(types)})"


def _parameter_count(node: Node) -> int:
    parameters = _first_named_child(node, {"parameters"})
    if parameters is None:
        return 0
    return len(
        [
            parameter
            for parameter in parameters.named_children
            if parameter.type in {"parameter", "self_parameter"}
        ]
    )


def _parameter_type_texts(parameter: Node, source: bytes) -> Iterator[str]:
    if parameter.type == "self_parameter":
        yield _type_text(source, parameter)
        return
    type_node = _parameter_type_node(parameter)
    if type_node is not None:
        yield _type_text(source, type_node)


def _parameter_type_node(parameter: Node) -> Node | None:
    for child in reversed(parameter.named_children):
        if child.type in _RUST_TYPE_NODE_TYPES:
            return child
    return None


def _argument_count(node: Node) -> int:
    if node.type == "macro_invocation":
        return 0
    arguments = _first_named_child(node, {"arguments"})
    return 0 if arguments is None else len(arguments.named_children)


def _field_receiver_text(source: bytes, node: Node) -> str | None:
    if node.type != "field_expression" or not node.named_children:
        return None
    return node_text(source, node.named_children[0])


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


def _field_definition_occurrence(
    file_path: str, source: bytes, name_node: Node, key: str, name: str
) -> OccurrenceFact:
    return OccurrenceFact(
        file_path=file_path,
        role="definition",
        text=name,
        span=node_span(file_path, source, name_node),
        node_key=key,
        resolved_key=key,
        confidence=1.0,
        extractor=EXTRACTOR,
        metadata={"node_kind": "field"},
    )


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


def _symbol_key(file_path: str, local_name: str) -> str:
    return f"rust:{file_path}#{local_name}"


_RUST_TYPE_ITEM_TYPES = {"struct_item", "enum_item", "trait_item", "type_item"}

_RUST_TYPE_NODE_TYPES = {
    "array_type",
    "bounded_type",
    "dynamic_type",
    "generic_type",
    "impl_trait_type",
    "metavariable",
    "never_type",
    "pointer_type",
    "primitive_type",
    "qualified_type",
    "reference_type",
    "scoped_type_identifier",
    "tuple_type",
    "type_identifier",
    "unit_type",
}

_RUST_BUILTIN_TYPES = {
    "Self",
    "bool",
    "char",
    "f32",
    "f64",
    "i8",
    "i16",
    "i32",
    "i64",
    "i128",
    "isize",
    "str",
    "u8",
    "u16",
    "u32",
    "u64",
    "u128",
    "usize",
}
