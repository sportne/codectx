# T041 - Add optional FTS support

ID: T041
Title: Add optional FTS support
Status: done
Depends on: T040
Requirement coverage: FR-042, NFR-010 through NFR-013
Milestone: M4 - Symbol search and anchor resolution
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Detect FTS5 support.
- Create FTS tables when supported.
- Populate symbol/chunk FTS entries.
- Fall back to `LIKE` search when unavailable.

Deliverable:

- FTS-backed search path with fallback.

Acceptance:

- Tests pass in both simulated FTS-available and FTS-unavailable modes.
