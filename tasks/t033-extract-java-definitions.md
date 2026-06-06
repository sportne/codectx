# T033 - Extract Java definitions

ID: T033
Title: Extract Java definitions
Status: done
Depends on: T031
Requirement coverage: FR-022, FR-025
Milestone: M3 - Tree-sitter definition extraction
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Extract package declaration metadata.
- Extract imports.
- Extract type declarations.
- Extract methods and constructors.
- Extract fields.
- Emit containment edges.
- Emit chunks for definitions.

Deliverable:

- Java definition extraction.

Acceptance:

- Java fixture test verifies expected nodes and containment edges.
- Extracted spans point to correct source lines.
