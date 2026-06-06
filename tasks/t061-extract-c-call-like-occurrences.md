# T061 - Extract C++ call-like occurrences

ID: T061
Title: Extract C++ call-like occurrences
Status: done
Depends on: T034, T035
Requirement coverage: FR-027, FR-028
Milestone: M6 - References, call-like edges, and neighborhoods
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Extract call expressions.
- Identify enclosing function/method.
- Store occurrence text and unresolved call edge.
- Resolve same-file/same-class calls when obvious.

Deliverable:

- C++ call-like extraction.

Acceptance:

- Fixture test shows target function has call-like edges.
