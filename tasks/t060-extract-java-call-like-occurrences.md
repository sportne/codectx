# T060 - Extract Java call-like occurrences

ID: T060
Title: Extract Java call-like occurrences
Status: done
Depends on: T033, T035
Requirement coverage: FR-027, FR-028
Milestone: M6 - References, call-like edges, and neighborhoods
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Extract method invocation expressions.
- Identify enclosing callable.
- Store occurrence text and unresolved call edge.
- Resolve same-class method calls when obvious.

Deliverable:

- Java call-like extraction.

Acceptance:

- Fixture test shows `authorize` has call-like edge to `validate` or unresolved `gateway.charge`.
