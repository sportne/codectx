"""Vulture whitelist for planned public surfaces."""

_.extract  # frontend protocol method

_.anchor  # context bundle field
_.chunks  # extracted facts field
_.code  # diagnostic field
_.confidence  # graph fact and context bundle field
_.content_hash  # file record field
_.diagnostics  # extracted facts field
_.dst_key  # edge fact field
_.edges  # extracted facts field
_.end_byte  # source span field
_.end_col  # source span field
_.end_line  # source span and chunk field
_.extractor  # graph fact and context bundle field
_.file  # context item field
_.file_path  # graph fact and source span field
_.index_health  # context bundle field
_.is_generated  # file record field
_.is_test  # file record field
_.items  # context bundle field
_.kind  # graph fact and context item field
_.language  # frontend protocol and graph fact field
_.line_count  # file record field
_.line_range  # context item field
_.message  # diagnostic field
_.metadata  # graph fact and context item field
_.name  # graph fact and omitted item field
_.node_key  # occurrence and chunk fact field
_.nodes  # extracted facts field
_.occurrences  # extracted facts field
_.omitted  # context bundle field
_.qualified_name  # graph node fact field
_.query  # context bundle field
_.rank  # context item field
_.reason  # context and omitted item field
_.resolved_key  # occurrence fact field
_.role  # occurrence fact field
_.row_factory  # sqlite connection configuration
_.score  # context and omitted item field
_.severity  # diagnostic field
_.size_bytes  # file record field
_.source  # frontend protocol parameter
_.span  # graph fact field
_.src_key  # edge fact field
_.start_byte  # source span field
_.start_col  # source span field
_.start_line  # source span and chunk field
_.symbol_key  # graph node fact field
_.text  # occurrence, chunk, and context item field
_.token_estimate  # context and chunk field
_.trace  # context bundle field
_.uncertainty_notes  # context bundle field
_.unresolved_dst  # edge fact field
_.unresolved_src  # edge fact field
_.weight  # edge fact field

ContextBundle  # context bundle public model
FileRecord  # scanner public model
LanguageFrontend  # frontend protocol public API
JavaTreeSitterFrontend  # Java frontend public API
SourceSnippet  # source snippet public model
apply_schema  # graph store schema lifecycle API
build_parser  # CLI parser construction API
close  # graph store lifecycle API
contains_line  # source span query API
create_repo  # graph store repository persistence API
create_snapshot  # graph store snapshot persistence API
detect_language  # scanner public API
byte_range_to_span  # source coordinate conversion API
estimate_token_count  # source token estimate API
file_sha256  # scanner hashing public API
first_child_by_field_name  # Tree-sitter helper API
insert_files  # graph store file persistence API
insert_chunks  # graph store chunk persistence API
insert_diagnostics  # graph store diagnostic persistence API
insert_edges  # graph store edge persistence API
insert_nodes  # graph store node persistence API
insert_occurrences  # graph store occurrence persistence API
integrity_check  # graph store health API
is_likely_test  # scanner public API
latest_snapshot_id  # graph store snapshot lookup API
line_range_to_byte_range  # source coordinate conversion API
main  # console entry point
make_chunk  # Tree-sitter helper API
make_language  # Tree-sitter helper API
make_parser  # Tree-sitter helper API
named_children  # Tree-sitter helper API
node_span  # Tree-sitter helper API
node_text  # Tree-sitter helper API
parse_source  # Tree-sitter helper API
snippet_by_byte_span  # source snippet public API
snippet_by_line_range  # source snippet public API
to_dict  # context bundle serialization API
