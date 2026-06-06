# T010 - Implement language detection

ID: T010
Title: Implement language detection
Status: done
Depends on: T003
Requirement coverage: FR-003
Milestone: M1 - Source substrate
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Map file extensions to `java`, `cpp`, or unsupported.
- Treat C++ headers as `cpp` for MVP.
- Add path-based test file hints.

Deliverable:

- `scanner/language_detect.py`.

Acceptance:

- Unit tests cover `.java`, `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hh`, `.hxx`, `.h`.
- Unsupported files return `None` or equivalent.
