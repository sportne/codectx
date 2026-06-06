# T022 - Persist repository snapshot and files

ID: T022
Title: Persist repository snapshot and files
Status: done
Depends on: T021, T012
Requirement coverage: FR-010, FR-040
Milestone: M2 - SQLite graph store and fact persistence
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Insert repo row.
- Insert snapshot row.
- Insert file rows from scanner.
- Store line count, hash, language, flags.

Deliverable:

- File persistence methods.

Acceptance:

- Integration test indexes a temp repo and verifies file rows.
