# V1-007 - Establish real-repo performance and storage gates

ID: V1-007
Title: Establish real-repo performance and storage gates
Status: done
Depends on: V1-002
Requirement coverage: Not specified.
Milestone: V1 - 1.0 readiness
Priority: P1
Type: AFK

Rationale:

Synthetic performance smoke tests are useful, but 1.0 readiness needs real-repo indexing, query, and database-size expectations.

Work:

- Define representative real-repo performance scenarios.
- Measure index time, query time, context time, and database size ratio.
- Add an opt-in or scheduled performance gate with documented thresholds.
- Record baseline results and expected variance.

Deliverable:

- Completed task scope described by acceptance criteria.

Acceptance:

- Defines real-repo index/query/storage thresholds and adds an opt-in or scheduled performance gate.
