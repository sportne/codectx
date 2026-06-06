# T003 - Define core dataclasses

ID: T003
Title: Define core dataclasses
Status: done
Depends on: T001
Requirement coverage: FR-024, FR-046, NFR-040, NFR-043
Milestone: M0 - Project skeleton and baseline
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Define `SourceSpan`.
- Define `FileRecord`.
- Define `NodeFact`, `EdgeFact`, `OccurrenceFact`, `ChunkFact`, `DiagnosticFact`.
- Include extractor, confidence, metadata, and source span fields where applicable.

Deliverable:

- `frontends/base.py`, `source/spans.py`, and related model files.

Acceptance:

- Unit tests instantiate and serialize each fact type.
- Type hints are clear enough for later modules.

---

## M1 — Source substrate
