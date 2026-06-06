# T063 - Implement bounded graph neighborhood query

ID: T063
Title: Implement bounded graph neighborhood query
Status: done
Depends on: T060, T061, T062
Requirement coverage: FR-044, FR-104
Milestone: M6 - References, call-like edges, and neighborhoods
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Traverse edges from seed node.
- Support direction and depth.
- Support edge-kind allowlist.
- Return nodes/edges with confidence and provenance.

Deliverable:

- `graph/traversal.py` and `neighborhood` CLI.

Acceptance:

- `codectx neighborhood --symbol X --depth 1` shows direct relationships.
