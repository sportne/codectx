# T024 - Implement index health stats persistence

ID: T024
Title: Implement index health stats persistence
Status: done
Depends on: T022, T023
Requirement coverage: FR-029, FR-107, NFR-022
Milestone: M2 - SQLite graph store and fact persistence
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Persist counts for files, languages, nodes, edges, occurrences, chunks, diagnostics, unresolved references.
- Add `health` CLI command to display stats.

Deliverable:

- `index_stat` storage and `health` command.

Acceptance:

- `codectx health --repo fixture` displays stats after indexing.

---

## M3 — Tree-sitter definition extraction
