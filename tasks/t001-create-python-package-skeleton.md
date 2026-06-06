# T001 - Create Python package skeleton

ID: T001
Title: Create Python package skeleton
Status: done
Depends on: none
Requirement coverage: CON-002, NFR-040
Milestone: M0 - Project skeleton and baseline
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Create `pyproject.toml`.
- Create `src/codectx` package.
- Create module directories: `scanner`, `source`, `frontends`, `graph`, `context`.
- Add `tests` directory.
- Add `.gitignore`.

Deliverable:

- Installable Python package skeleton.

Acceptance:

- `python -m pip install -e .[dev]` succeeds in a clean virtual environment.
- `python -c "import codectx"` succeeds.
