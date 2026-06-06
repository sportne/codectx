# V1-001 - Define 1.0 release criteria and stable contracts

ID: V1-001
Title: Define 1.0 release criteria and stable contracts
Status: done
Depends on: none
Requirement coverage: Not specified.
Milestone: V1 - 1.0 readiness
Priority: P0
Type: HITL

Rationale:

A 1.0.0 release needs explicit stability promises for the CLI, output formats, schema behavior, release artifacts, and compatibility support.

Work:

- Decide which CLI commands and flags are stable for 1.0.
- Decide which JSON context bundle fields are stable for downstream tools.
- Decide the SQLite schema compatibility and migration promise.
- Decide the supported Python and platform compatibility promise.
- Record release artifact guarantees for wheels, source distributions, and PEX.

Deliverable:

- Completed task scope described by acceptance criteria.

Acceptance:

- Documents which CLI commands, JSON fields, schema behavior, release artifacts, and compatibility promises are stable for 1.0.
