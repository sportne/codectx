# V1-010 - Simplify context planner internals without behavior drift

ID: V1-010
Title: Simplify context planner internals without behavior drift
Status: done
Depends on: V1-002, V1-004
Requirement coverage: Not specified.
Milestone: V1 - 1.0 readiness
Priority: P2
Type: AFK

Rationale:

The context planner is the largest concentration of ranking, SQL, candidate generation, and budget behavior; improving locality will make 1.0 maintenance safer.

Work:

- Identify planner responsibilities that can be separated behind stable internal interfaces.
- Refactor in small slices while preserving golden output.
- Keep behavior changes gated by the real-repo evaluation harness.
- Document any intentional ranking or output differences.

Deliverable:

- Completed task scope described by acceptance criteria.

Acceptance:

- Refactors context/planner.py for locality while keeping golden and real-repo evaluation output stable.
