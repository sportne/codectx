# V2-001 - Define the file-only context CLI contract

ID: V2-001
Title: Define the file-only context CLI contract
Status: done
Depends on: none
Requirement coverage: Not specified.
Milestone: V2 - File-only context anchors
Priority: P1
Type: AFK

Rationale:

Users should be able to ask for context around an indexed source file without also identifying a specific line, while preserving the current precise file/line anchor behavior.

Work:

- Define `codectx context --file PATH` as a file-level anchor.
- Keep `codectx context --file PATH --line N` as the existing line-level anchor.
- Keep `--symbol QUERY --line N` invalid.
- Decide the rendered query and anchor metadata shape for file-level bundles.

Deliverable:

- Completed task scope described by acceptance criteria.

Acceptance:

- Documents and tests the CLI validation contract for file-only anchors without changing existing symbol or file/line behavior.
