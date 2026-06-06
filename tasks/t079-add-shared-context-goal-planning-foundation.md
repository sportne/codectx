# T079 - Add shared context goal planning foundation

ID: T079
Title: Add shared context goal planning foundation
Status: done
Depends on: T073
Requirement coverage: FR-067, FR-068, FR-104
Milestone: M8 - Additional context goals
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Route supported context goals through a shared planner entrypoint.
- Preserve existing `explain` behavior.
- Keep `cli.py` as argument parsing, service calls, and printing only.

Deliverable:

- Shared goal-aware context planning foundation.

Acceptance:

- Non-`explain` context goals reach bundle planning instead of returning not implemented.
