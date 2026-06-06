# V1-004 - Improve token budgeting for large enclosing scopes

ID: V1-004
Title: Improve token budgeting for large enclosing scopes
Status: done
Depends on: V1-002
Requirement coverage: Not specified.
Milestone: V1 - 1.0 readiness
Priority: P0
Type: AFK

Rationale:

Current bundles can spend much of a small budget on required large enclosing scopes, reducing the precision of context for real tasks.

Work:

- Identify bundle cases where target or enclosing context dominates the budget.
- Define compact fallback behavior for large required scopes.
- Preserve provenance and uncertainty notes for any abbreviated context.
- Add fixture and real-repo validation for small-budget bundles.

Deliverable:

- Completed task scope described by acceptance criteria.

Acceptance:

- Prevents large enclosing scopes from dominating small budgets and verifies budget behavior through fixtures and real-repo cases.
