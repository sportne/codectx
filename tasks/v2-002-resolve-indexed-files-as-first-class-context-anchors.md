# V2-002 - Resolve indexed files as first-class context anchors

ID: V2-002
Title: Resolve indexed files as first-class context anchors
Status: done
Depends on: V2-001
Requirement coverage: Not specified.
Milestone: V2 - File-only context anchors
Priority: P1
Type: AFK

Rationale:

File-only context needs an explicit anchor shape so planner code does not fake a line number or overload the existing file/line anchor semantics.

Work:

- Add a file anchor resolver that validates the file exists in the latest indexed snapshot.
- Return file id, path, language, line count, and any useful file metadata.
- Produce actionable errors for missing indexes and unindexed files.
- Add focused resolver and service tests.

Deliverable:

- Completed task scope described by acceptance criteria.

Acceptance:

- Resolves `--file PATH` to an indexed file anchor and reports clear errors for missing or unindexed files.
