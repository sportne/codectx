# V3-002 - Add MATLAB indexing frontend

ID: V3-002
Title: Add MATLAB indexing frontend
Status: todo
Depends on: V3-001
Requirement coverage: Language expansion; scanner, frontend extraction, indexing, querying, and context bundle behavior.
Milestone: V3 - Additional language support
Priority: P1
Type: AFK

Rationale:

MATLAB is a requested internal language and can share the Tree-sitter frontend pattern, but scripts and class/function file conventions need explicit handling.

Work:

- Add `tree-sitter-matlab` as a bounded runtime dependency and PEX binary resolve flag.
- Detect `.m` files as MATLAB and explicitly leave `.mlx` unsupported unless a later task adds notebook-style handling.
- Implement `MatlabTreeSitterFrontend` for function files, script files, `classdef`, methods, properties, imports or path-like references where available, unresolved calls, chunks, and parser diagnostics.
- Use file/source fallback for symbol-poor scripts while preserving file-only context usability.
- Add MATLAB fixtures and context/search tests covering function, class, method, property, and script cases.

Deliverable:

- MATLAB `.m` files produce useful symbols, outlines, chunks, diagnostics, and file-only context bundles.

Acceptance:

- MATLAB functions, classes, methods, and properties are discoverable via `symbols`.
- MATLAB scripts produce an actionable file-level bundle instead of an empty result.
- Parser diagnostics are recorded without crashing indexing.
- `make ci` and `make artifact-smoke` pass.
