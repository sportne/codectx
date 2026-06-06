# V2-003 - Build file-level context from symbols in the file

ID: V2-003
Title: Build file-level context from symbols in the file
Status: done
Depends on: V2-002
Requirement coverage: Not specified.
Milestone: V2 - File-only context anchors
Priority: P1
Type: AFK

Rationale:

A file-level bundle should use the symbols defined in the file as the origin points for context collection instead of dumping the entire file or choosing an arbitrary line.

Work:

- Query callable, type, and field nodes/chunks defined in the anchor file.
- Add those definitions as file-origin candidates rather than mandatory target items.
- Reuse existing import/include, relationship, test, and diagnostic candidate logic across file symbols where practical.
- Deduplicate candidates by chunk id, edge id, and file/range.
- Fall back to file chunk or source snippet context when no symbols are indexed.

Deliverable:

- Completed task scope described by acceptance criteria.

Acceptance:

- Generates a context bundle for `--file PATH` that includes symbols from the file and related context collected from those symbols.
