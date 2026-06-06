# T013 - Implement source snippet extraction

ID: T013
Title: Implement source snippet extraction
Status: done
Depends on: T012
Requirement coverage: FR-010, FR-011, FR-013
Milestone: M1 - Source substrate
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Retrieve text by byte span.
- Retrieve text by line range.
- Include optional surrounding context lines.
- Implement rough token estimator: `ceil(chars / 4)`.

Deliverable:

- `source/snippets.py`, `source/tokens.py`.

Acceptance:

- Unit tests verify exact snippets and line numbering.
- Token estimate is deterministic.
