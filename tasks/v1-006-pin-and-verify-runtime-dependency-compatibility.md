# V1-006 - Pin and verify runtime dependency compatibility

ID: V1-006
Title: Pin and verify runtime dependency compatibility
Status: done
Depends on: V1-001
Requirement coverage: Not specified.
Milestone: V1 - 1.0 readiness
Priority: P1
Type: AFK

Rationale:

1.0 should not depend on unbounded runtime parser packages whose API or grammar behavior can change underneath users.

Work:

- Bound runtime dependencies in packaging metadata.
- Verify supported Python versions and tree-sitter package combinations in CI.
- Document the supported dependency and platform matrix.
- Add an upgrade checklist for future dependency bumps.

Deliverable:

- Completed task scope described by acceptance criteria.

Acceptance:

- Pins or bounds runtime dependencies and verifies supported Python/tree-sitter combinations in CI.
