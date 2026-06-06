# V3-001 - Add Python indexing frontend

ID: V3-001
Title: Add Python indexing frontend
Status: todo
Depends on: none
Requirement coverage: Language expansion; scanner, frontend extraction, indexing, querying, and context bundle behavior.
Milestone: V3 - Additional language support
Priority: P1
Type: AFK

Rationale:

Python is the highest-value next language for internal repositories and has a maintained Tree-sitter parser package with published wheels.

Work:

- Add `tree-sitter-python` as a bounded runtime dependency and PEX binary resolve flag.
- Detect `.py` and `.pyi` files as Python and update test-file heuristics for common Python test names.
- Implement `PythonTreeSitterFrontend` for modules, classes, functions, async functions, methods, imports, unresolved calls, chunks, and parser diagnostics.
- Register the frontend in `default_frontends()`.
- Add Python fixtures, graph/query/context tests, runtime compatibility coverage, and artifact-smoke coverage where practical.

Deliverable:

- Python source files are indexed into useful symbols, imports, call-like edges, chunks, diagnostics, and context bundles.

Acceptance:

- `codectx index` records Python files, nodes, chunks, imports, and unresolved calls for representative fixtures.
- `codectx symbols` finds Python classes and functions.
- `codectx context --file path/to/file.py` starts from Python symbols and returns useful context.
- `make ci` and `make artifact-smoke` pass.
