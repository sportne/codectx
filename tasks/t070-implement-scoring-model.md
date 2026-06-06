# T070 - Implement scoring model

ID: T070
Title: Implement scoring model
Status: done
Depends on: T064
Requirement coverage: FR-061, NFR-043
Milestone: M7 - Ranking, budgeting, and provenance traces
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Implement score components: target, exact match, edge relevance, graph proximity, source proximity, lexical match, enclosing context, test context, confidence, token cost.
- Store score trace per candidate.

Deliverable:

- `context/ranking.py`.

Acceptance:

- Unit tests show target definition outranks unrelated sibling.
- Score trace is included in JSON output.
