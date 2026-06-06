# V1-005 - Reduce C++ vendor diagnostics and unresolved-reference noise

ID: V1-005
Title: Reduce C++ vendor diagnostics and unresolved-reference noise
Status: done
Depends on: V1-003
Requirement coverage: Not specified.
Milestone: V1 - 1.0 readiness
Priority: P1
Type: AFK

Rationale:

Real C++ validation showed high parser diagnostic and unresolved reference counts, especially from third-party code, which weakens context bundle precision.

Work:

- Use improved ignore semantics to reduce third-party diagnostic noise.
- Review C++ unresolved-reference patterns from real validation cases.
- Improve ranking or presentation so noisy global diagnostics do not dominate local failure-mode context.
- Add regression cases for the observed C++ validation failures.

Deliverable:

- Completed task scope described by acceptance criteria.

Acceptance:

- Reduces noisy C++ parser diagnostics and improves usefulness of C++ bundles, especially failure-mode bundles affected by vendored code.
