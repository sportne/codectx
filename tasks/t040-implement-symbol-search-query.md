# T040 - Implement symbol search query

ID: T040
Title: Implement symbol search query
Status: done
Depends on: T035
Requirement coverage: FR-042, FR-101, FR-102
Milestone: M4 - Symbol search and anchor resolution
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Query node table by name, qualified name, and path.
- Rank exact matches above substring matches.
- Return file and line range.

Deliverable:

- `graph/query.py` symbol search function and CLI command.

Acceptance:

- `codectx symbols PaymentService --repo fixture` returns expected node.
