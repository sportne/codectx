# T093 - Implement database integrity checks

ID: T093
Title: Implement database integrity checks
Status: done
Depends on: T092
Requirement coverage: NFR-020 through NFR-023
Milestone: M9 - Verification, validation, and MVP hardening
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Add `codectx health --integrity` option.
- Run `PRAGMA integrity_check` and `foreign_key_check`.
- Validate spans and unresolved edge invariants.

Deliverable:

- Integrity check command and tests.

Acceptance:

- Fixture DB passes integrity checks.
