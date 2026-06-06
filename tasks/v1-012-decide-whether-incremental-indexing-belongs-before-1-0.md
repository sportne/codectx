# V1-012 - Decide whether incremental indexing belongs before 1.0

ID: V1-012
Title: Decide whether incremental indexing belongs before 1.0
Status: done
Depends on: V1-007
Requirement coverage: Not specified.
Milestone: V1 - 1.0 readiness
Priority: P3
Type: HITL

Rationale:

Incremental indexing may improve repeated real-repo workflows, but it also adds complexity and compatibility surface that may not be needed for 1.0.

Work:

- Use real-repo performance evidence to decide whether full reindexing is acceptable for 1.0.
- If needed, define the minimum incremental indexing behavior for 1.0.
- If deferred, record the rationale and expected future trigger.
- Update release criteria and documentation with the decision.

Deliverable:

- Completed task scope described by acceptance criteria.

Acceptance:

- Records a decision on incremental indexing before 1.0, either implementing a minimal version or explicitly deferring it.
