# T089 - Lock M9 indexing service boundary

ID: T089
Title: Lock M9 indexing service boundary
Status: done
Depends on: T069
Requirement coverage: NFR-040, NFR-043
Milestone: M9 - Verification, validation, and MVP hardening
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Confirm `cli.py` delegates index and health behavior to `codectx.indexing`.
- Confirm no duplicate indexing orchestration service is introduced.

Deliverable:

- Architecture coverage for the MVP indexing service boundary.

Acceptance:

- Boundary tests fail if CLI imports scanner/frontend/store orchestration directly or a duplicate indexing service appears.
