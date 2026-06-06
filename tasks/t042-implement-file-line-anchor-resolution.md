# T042 - Implement file/line anchor resolution

ID: T042
Title: Implement file/line anchor resolution
Status: done
Depends on: T035
Requirement coverage: FR-043, FR-060
Milestone: M4 - Symbol search and anchor resolution
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Given file path and line number, find smallest containing node.
- Prefer callable over type over file.
- Return candidate if ambiguous.

Deliverable:

- `context/anchors.py`.

Acceptance:

- Fixture test resolves a method body line to the method node.
- Line outside a method resolves to enclosing type or file.
