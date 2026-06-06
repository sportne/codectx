# T021 - Implement GraphStore connection and schema application

ID: T021
Title: Implement GraphStore connection and schema application
Status: done
Depends on: T020
Requirement coverage: FR-040, FR-041, NFR-022
Milestone: M2 - SQLite graph store and fact persistence
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Open SQLite connection.
- Apply pragmas.
- Apply schema.
- Check schema version.
- Provide context manager or close method.

Deliverable:

- `graph/store.py`.

Acceptance:

- Unit test creates temp DB and applies schema.
- Re-applying schema is safe.
