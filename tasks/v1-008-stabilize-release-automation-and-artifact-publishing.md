# V1-008 - Stabilize release automation and artifact publishing

ID: V1-008
Title: Stabilize release automation and artifact publishing
Status: done
Depends on: V1-001
Requirement coverage: Not specified.
Milestone: V1 - 1.0 readiness
Priority: P1
Type: AFK

Rationale:

1.0 releases should have repeatable tagged builds and published artifacts, including a versioned PEX asset on GitHub Releases.

Work:

- Ensure tag-triggered release builds create or update GitHub Releases.
- Publish versioned PEX assets and workflow build artifacts.
- Document manual dispatch and recovery for existing tags.
- Verify release CI on a non-production test tag before 1.0.

Deliverable:

- Completed task scope described by acceptance criteria.

Acceptance:

- Ensures tagged releases create or update GitHub Releases with versioned PEX assets and documented manual recovery steps.
