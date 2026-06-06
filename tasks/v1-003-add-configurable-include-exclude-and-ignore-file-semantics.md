# V1-003 - Add configurable include/exclude and ignore-file semantics

ID: V1-003
Title: Add configurable include/exclude and ignore-file semantics
Status: done
Depends on: V1-002
Requirement coverage: Not specified.
Milestone: V1 - 1.0 readiness
Priority: P0
Type: AFK

Rationale:

Fixed built-in ignore directories are not enough for messy real repositories, and vendored or generated files can dominate diagnostics and context rankings.

Work:

- Design user-facing include and exclude controls for indexing.
- Define how .gitignore, .ignore, and project-specific ignore files are respected.
- Support explicitly including files that would otherwise be ignored.
- Cover subdirectory invocation and nested ignore-file behavior.

Deliverable:

- Completed task scope described by acceptance criteria.

Acceptance:

- Supports user-controlled include/exclude behavior, respects common ignore files where intended, and covers subdirectory invocation and force-include style cases.
