# T050 - Define context bundle model

ID: T050
Title: Define context bundle model
Status: done
Depends on: T003
Requirement coverage: FR-060 through FR-065, FR-080 through FR-084
Milestone: M5 - Context bundle v0 for `explain`
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Define bundle dataclasses: `ContextBundle`, `ContextItem`, `OmittedItem`, `TraceItem`.
- Include query, anchor, health, ranked items, omitted items, uncertainty notes.

Deliverable:

- `context/bundle.py`.

Acceptance:

- Unit test serializes a bundle to dict/JSON.
