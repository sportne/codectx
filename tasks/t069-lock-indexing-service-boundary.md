# T069 - Lock indexing service boundary

ID: T069
Title: Lock indexing service boundary
Status: done
Depends on: T029
Requirement coverage: ARCH-001
Milestone: M7 - Ranking, budgeting, and provenance traces
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Keep indexing orchestration inside the existing indexing service.
- Verify `cli.py` does not import scanner/frontends/graph-store orchestration directly.
- Do not add a duplicate indexing service.

Deliverable:

- Architecture coverage for indexing service delegation.

Acceptance:

- Boundary tests fail if `cli.py` grows direct indexing orchestration imports.
