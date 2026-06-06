# T030 - Implement Tree-sitter frontend base

ID: T030
Title: Implement Tree-sitter frontend base
Status: done
Depends on: T003, T013
Requirement coverage: FR-020, FR-021, FR-024
Milestone: M3 - Tree-sitter definition extraction
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Create a shared frontend protocol.
- Implement parser initialization abstraction.
- Implement helper functions for node text, spans, and child traversal.

Deliverable:

- `frontends/base.py` and common Tree-sitter utilities.

Acceptance:

- Unit test can parse a minimal Java and C++ source string through frontend helpers.
