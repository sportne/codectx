# V3-004 - Add Rust indexing frontend

ID: V3-004
Title: Add Rust indexing frontend
Status: todo
Depends on: V3-001
Requirement coverage: Language expansion; scanner, frontend extraction, indexing, querying, and context bundle behavior.
Milestone: V3 - Additional language support
Priority: P1
Type: AFK

Rationale:

Rust is a high-value systems language for internal tooling, but should follow Python/Go because modules, impl blocks, traits, and macros need careful heuristic boundaries.

Work:

- Add `tree-sitter-rust` as a bounded runtime dependency and PEX binary resolve flag.
- Detect `.rs` files and update test-file heuristics for Rust module and test conventions where practical.
- Implement `RustTreeSitterFrontend` for modules, `use` items, functions, impl methods, structs, enums, traits, fields or variants, unresolved calls, chunks, and parser diagnostics.
- Treat macro-heavy and generated code as heuristic; record diagnostics or uncertainty rather than over-resolving.
- Add Rust fixtures and tests for symbols, file-only bundles, imports/use items, impl methods, and parser diagnostics.

Deliverable:

- Rust files are indexed into useful module/type/function symbols and context bundles with documented macro limitations.

Acceptance:

- Rust functions, impl methods, structs, enums, and traits are discoverable via `symbols`.
- Rust `use` items and unresolved calls appear in context bundles where relevant.
- Macro-heavy fixtures produce bounded diagnostics/uncertainty without crashes.
- `make ci` and `make artifact-smoke` pass.
