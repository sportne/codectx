# V2-005 - Document and validate file-only context usage

ID: V2-005
Title: Document and validate file-only context usage
Status: done
Depends on: V2-004
Requirement coverage: Not specified.
Milestone: V2 - File-only context anchors
Priority: P2
Type: AFK

Rationale:

The README currently states that file context requires a line; once file-only anchors exist, user docs and validation examples must match the supported workflow.

Work:

- Update README quickstart and caveats for `context --file PATH`.
- Update release criteria or project notes with the file-level anchor contract.
- Add fixture or acceptance coverage for the PEX-style command shape.
- Record any known limitations for symbol-poor files.

Deliverable:

- Completed task scope described by acceptance criteria.

Acceptance:

- Documents the file-only context workflow and verifies it through existing CLI or acceptance tests.
