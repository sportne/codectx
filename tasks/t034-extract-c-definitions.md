# T034 - Extract C++ definitions

ID: T034
Title: Extract C++ definitions
Status: done
Depends on: T032
Requirement coverage: FR-023, FR-025
Milestone: M3 - Tree-sitter definition extraction
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Extract includes.
- Extract namespaces.
- Extract classes/structs/enums.
- Extract free functions and methods.
- Extract constructors/destructors when identifiable.
- Extract fields.
- Emit containment edges.
- Emit chunks for definitions.

Deliverable:

- C++ definition extraction.

Acceptance:

- C++ fixture test verifies expected nodes and containment edges.
- Extracted spans point to correct source lines.
