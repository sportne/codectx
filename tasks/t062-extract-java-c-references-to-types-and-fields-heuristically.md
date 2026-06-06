# T062 - Extract Java/C++ references to types and fields heuristically

ID: T062
Title: Extract Java/C++ references to types and fields heuristically
Status: done
Depends on: T060, T061
Requirement coverage: FR-027, FR-028, FR-068
Milestone: M6 - References, call-like edges, and neighborhoods
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Capture identifier/qualified-identifier occurrences in target spans.
- Avoid expression-level graph explosion by storing occurrences, not all tokens as nodes.
- Resolve unique project-wide names where safe.

Deliverable:

- Occurrence extraction and weak reference edges.

Acceptance:

- Fixture tests show selected type references and unresolved references.
