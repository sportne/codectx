# T055 - Wire `codectx context --goal explain`

ID: T055
Title: Wire `codectx context --goal explain`
Status: done
Depends on: T051, T052, T053, T054
Requirement coverage: FR-060, FR-066, FR-080 through FR-084, FR-103
Milestone: M5 - Context bundle v0 for `explain`
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Parse `--symbol` or `--file --line`.
- Resolve anchor.
- Generate bundle.
- Emit selected format.
- Support `--output` file path.

Deliverable:

- Functional context command for explain v0.

Acceptance:

- `codectx context --file ... --line ... --goal explain --format markdown` produces usable bundle.
- `--format json` produces valid JSON.

---

## M6 — References, call-like edges, and neighborhoods
