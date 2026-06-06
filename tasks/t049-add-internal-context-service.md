# T049 - Add internal context service

ID: T049
Title: Add internal context service
Status: done
Depends on: T043
Requirement coverage: FR-060, FR-080 through FR-084, FR-103
Milestone: M5 - Context bundle v0 for `explain`
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Add CLI-facing context orchestration outside `cli.py`.
- Share request validation and output-path handling for context commands.
- Keep context CLI placeholder routed through the service until generation lands.

Deliverable:

- `contexting.py` context service foundation.

Acceptance:

- Context service validates requests and preserves placeholder behavior.
- `codectx context` routes through the context service.
