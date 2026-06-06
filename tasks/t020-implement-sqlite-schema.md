# T020 - Implement SQLite schema

ID: T020
Title: Implement SQLite schema
Status: done
Depends on: T003
Requirement coverage: FR-040, FR-041, FR-046
Milestone: M2 - SQLite graph store and fact persistence
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Create `graph/schema.sql`.
- Include tables: `repo`, `snapshot`, `file`, `node`, `edge`, `occurrence`, `chunk`, `diagnostic`, `index_stat`.
- Include indexes for common lookup and traversal.
- Store schema version.

Deliverable:

- SQL schema file.

Acceptance:

- Schema applies to empty SQLite database.
- `PRAGMA integrity_check` passes.
- Required tables and indexes exist.
