# T052 - Implement Markdown formatter

ID: T052
Title: Implement Markdown formatter
Status: done
Depends on: T050, T051
Requirement coverage: FR-080, NFR-002
Milestone: M5 - Context bundle v0 for `explain`
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Render bundle header.
- Render target summary.
- Render health summary.
- Render ranked snippets with code fences.
- Render reasons and uncertainty notes.

Deliverable:

- `context/formatters.py` Markdown output.

Acceptance:

- Markdown output contains file paths, line ranges, reasons, and balanced code fences.
