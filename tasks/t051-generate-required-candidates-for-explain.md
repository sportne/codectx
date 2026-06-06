# T051 - Generate required candidates for `explain`

ID: T051
Title: Generate required candidates for `explain`
Status: done
Depends on: T042, T050
Requirement coverage: FR-060, FR-066
Milestone: M5 - Context bundle v0 for `explain`
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Include target definition.
- Include enclosing type/namespace/file.
- Include imports/includes from same file.
- Include same-file sibling helpers as optional candidates.

Deliverable:

- `context/planner.py` initial explain candidate generation.

Acceptance:

- Fixture `explain` bundle includes target method and enclosing class/type.
