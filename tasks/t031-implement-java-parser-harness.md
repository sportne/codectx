# T031 - Implement Java parser harness

ID: T031
Title: Implement Java parser harness
Status: done
Depends on: T030
Requirement coverage: FR-020, FR-029
Milestone: M3 - Tree-sitter definition extraction
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Initialize Java Tree-sitter parser.
- Parse source bytes.
- Detect parser errors.
- Emit parser diagnostic facts.

Deliverable:

- `frontends/java_treesitter.py` parser harness.

Acceptance:

- Fixture test parses valid Java and reports no fatal error.
- Invalid Java records diagnostic without crashing.
