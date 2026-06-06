# T011 - Implement repository scanner

ID: T011
Title: Implement repository scanner
Status: done
Depends on: T010
Requirement coverage: FR-001, FR-002, FR-006, FR-007
Milestone: M1 - Source substrate
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Walk repository recursively.
- Skip built-in ignored directories.
- Return `FileRecord` candidates with repo-relative paths.
- Mark likely tests and likely generated/vendor files.

Deliverable:

- `scanner/repo.py`.

Acceptance:

- Integration test over a temporary repo finds expected Java/C++ files and skips `.git`, `build`, `.codectx`, and `node_modules`.
