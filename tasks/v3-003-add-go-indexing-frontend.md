# V3-003 - Add Go indexing frontend

ID: V3-003
Title: Add Go indexing frontend
Status: done
Depends on: V3-001
Requirement coverage: Language expansion; scanner, frontend extraction, indexing, querying, and context bundle behavior.
Milestone: V3 - Additional language support
Priority: P1
Type: AFK

Rationale:

Go is a strong additional language because package, import, function, method, struct, and interface syntax maps cleanly to the existing graph model.

Work:

- Add `tree-sitter-go` as a bounded runtime dependency and PEX binary resolve flag.
- Detect `.go` files and mark common Go test files such as `*_test.go` as tests.
- Implement `GoTreeSitterFrontend` for packages, imports, functions, methods, structs, interfaces, fields, type uses, unresolved calls, chunks, and parser diagnostics.
- Register the frontend and add Go fixtures/golden expectations.
- Validate symbol, file-only context, file/line context, and related-test behavior on Go fixtures.

Deliverable:

- Go repositories can be indexed and queried with useful symbols, imports, type/call relationships, and context bundles.

Acceptance:

- Go package, function, method, struct, interface, and field definitions are indexed.
- Go imports and unresolved calls/types appear in graph facts with provenance.
- Go test files are marked as tests and can contribute related context.
- `make ci` and `make artifact-smoke` pass.
