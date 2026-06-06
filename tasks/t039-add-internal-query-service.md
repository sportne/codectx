# T039 - Add internal query service

ID: T039
Title: Add internal query service
Status: done
Depends on: T035
Requirement coverage: FR-101, FR-102, FR-105, FR-106
Milestone: M4 - Symbol search and anchor resolution
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Add CLI-facing query orchestration outside `cli.py`.
- Share missing-index and latest-snapshot resolution for query commands.
- Keep unimplemented query commands routed through the service until their tasks land.

Deliverable:

- `querying.py` query service foundation.

Acceptance:

- Query service resolves latest snapshots and missing-index errors.
- Query CLI placeholders are routed through the service.
