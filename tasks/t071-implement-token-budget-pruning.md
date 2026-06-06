# T071 - Implement token budget pruning

ID: T071
Title: Implement token budget pruning
Status: done
Depends on: T070
Requirement coverage: FR-062, NFR-023
Milestone: M7 - Ranking, budgeting, and provenance traces
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Estimate tokens for each candidate.
- Always include required items.
- Select optional items by score/token ratio.
- Deduplicate overlapping snippets.
- Track omitted items.

Deliverable:

- Budget-aware selection.

Acceptance:

- Bundle stays within budget tolerance on fixture cases.
- Omitted items list includes high-scoring excluded candidates.
