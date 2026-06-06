# T023 - Persist graph facts

ID: T023
Title: Persist graph facts
Status: done
Depends on: T021, T003
Requirement coverage: FR-024, FR-025, FR-026, FR-027, FR-028, FR-046
Milestone: M2 - SQLite graph store and fact persistence
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Insert node facts.
- Insert edge facts, including unresolved edges.
- Insert occurrence facts.
- Insert chunk facts.
- Insert diagnostic facts.
- Preserve extractor, confidence, metadata.

Deliverable:

- Batch insert methods in `GraphStore`.

Acceptance:

- Unit tests insert sample facts and read them back.
- Unresolved edge insert succeeds.
