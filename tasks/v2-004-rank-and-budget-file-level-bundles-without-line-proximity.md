# V2-004 - Rank and budget file-level bundles without line proximity

ID: V2-004
Title: Rank and budget file-level bundles without line proximity
Status: done
Depends on: V2-003
Requirement coverage: Not specified.
Milestone: V2 - File-only context anchors
Priority: P1
Type: AFK

Rationale:

Existing ranking assumes a single anchor line; file-level bundles need scoring that favors useful same-file symbols and graph-related context without treating every symbol as required.

Work:

- Add ranking behavior for file anchors that boosts same-file definitions and graph-related candidates.
- Avoid line-distance scoring when no line anchor exists.
- Ensure large files do not exhaust the budget with required same-file context.
- Add regression tests for multi-symbol files, large files, and overlapping candidates.

Deliverable:

- Completed task scope described by acceptance criteria.

Acceptance:

- Selects useful file-level context under budget without requiring every symbol in a large file.
