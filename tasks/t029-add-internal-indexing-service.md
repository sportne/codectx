# T029 - Add internal indexing service

ID: T029
Title: Add internal indexing service
Status: done
Depends on: T024
Requirement coverage: FR-100, FR-107
Milestone: M3 - Tree-sitter definition extraction
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Move index orchestration out of `cli.py`.
- Create internal service for scanning, persistence, health stats, and health lookup.
- Keep CLI focused on argument parsing and output formatting.

Deliverable:

- `codectx/indexing.py`.

Acceptance:

- Existing `index` and `health` CLI tests pass through the service.
- Unit tests cover default DB path, rebuild cleanup, missing health, and stat output.
