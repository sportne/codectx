# T012 - Implement hashing and line offsets

ID: T012
Title: Implement hashing and line offsets
Status: done
Depends on: T011
Requirement coverage: FR-004, FR-005, FR-012
Milestone: M1 - Source substrate
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Compute SHA-256 content hash.
- Compute line-start byte offsets.
- Convert byte ranges to line/column.
- Convert line ranges to byte ranges where possible.

Deliverable:

- `scanner/hashing.py` and `source/spans.py` utilities.

Acceptance:

- Unit tests cover ASCII and UTF-8 source.
- Byte-to-line conversion round-trips for known fixture positions.
