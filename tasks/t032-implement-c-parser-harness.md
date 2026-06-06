# T032 - Implement C++ parser harness

ID: T032
Title: Implement C++ parser harness
Status: done
Depends on: T030
Requirement coverage: FR-021, FR-029
Milestone: M3 - Tree-sitter definition extraction
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Initialize C++ Tree-sitter parser.
- Parse source bytes.
- Detect parser errors.
- Emit parser diagnostic facts.

Deliverable:

- `frontends/cpp_treesitter.py` parser harness.

Acceptance:

- Fixture test parses valid C++ and reports no fatal error.
- Invalid C++ records diagnostic without crashing.
