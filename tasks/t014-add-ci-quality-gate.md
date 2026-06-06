# T014 - Add CI quality gate

ID: T014
Title: Add CI quality gate
Status: done
Depends on: T013
Requirement coverage: development baseline
Milestone: M1 - Source substrate
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Add GitHub Actions workflow for pushes and pull requests to `main`.
- Run local quality gate on Python 3.11 and 3.12.
- Reuse `make setup-venv`, `make install-dev`, and `make ci`.

Deliverable:

- `.github/workflows/ci.yml`.

Acceptance:

- Workflow installs development dependencies.
- Workflow runs the same format, lint, typecheck, dead-code, architecture, and coverage gates as local `make ci`.

---

## M2 — SQLite graph store and fact persistence
