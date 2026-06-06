# T059 - Add internal neighborhood service

ID: T059
Title: Add internal neighborhood service
Status: done
Depends on: T055
Requirement coverage: FR-044, FR-104
Milestone: M6 - References, call-like edges, and neighborhoods
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Add a CLI-facing neighborhood service.
- Keep `cli.py` responsible for argument parsing and printing.
- Preserve placeholder behavior until bounded traversal is implemented.

Deliverable:

- `neighborhooding.py` service boundary for the neighborhood command.

Acceptance:

- `codectx neighborhood --symbol X` delegates through the service.
