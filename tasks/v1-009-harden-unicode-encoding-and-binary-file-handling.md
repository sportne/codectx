# V1-009 - Harden Unicode, encoding, and binary-file handling

ID: V1-009
Title: Harden Unicode, encoding, and binary-file handling
Status: done
Depends on: V1-002
Requirement coverage: Not specified.
Milestone: V1 - 1.0 readiness
Priority: P2
Type: AFK

Rationale:

Source span and snippet behavior must remain correct for real-world files with multibyte text, BOMs, invalid encodings, or binary-like content.

Work:

- Add tests for invalid UTF-8 and non-UTF-8 text files.
- Add tests for BOM handling and multibyte line boundaries.
- Decide how unsupported encodings and binary-like files are reported.
- Ensure indexing failures remain actionable diagnostics rather than crashes.

Deliverable:

- Completed task scope described by acceptance criteria.

Acceptance:

- Adds coverage for invalid UTF-8, BOMs, non-UTF-8 text, multibyte boundaries, and binary-ish source files.
