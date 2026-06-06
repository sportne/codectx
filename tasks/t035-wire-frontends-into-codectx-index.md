# T035 - Wire frontends into `codectx index`

ID: T035
Title: Wire frontends into `codectx index`
Status: done
Depends on: T022, T023, T033, T034
Requirement coverage: FR-100, FR-020 through FR-029
Milestone: M3 - Tree-sitter definition extraction
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Scanner discovers files.
- Frontend extracts facts per supported language.
- GraphStore persists facts.
- Health stats printed after index.

Deliverable:

- Functional `codectx index` for Java/C++ definitions.

Acceptance:

- `codectx index tests/fixtures/java_basic` creates DB with nodes.
- `codectx index tests/fixtures/cpp_basic` creates DB with nodes.

---

## M4 — Symbol search and anchor resolution
