# V3-005 - Document and validate expanded language support

ID: V3-005
Title: Document and validate expanded language support
Status: done
Depends on: V3-001, V3-002
Requirement coverage: Language expansion; scanner, frontend extraction, indexing, querying, and context bundle behavior.
Milestone: V3 - Additional language support
Priority: P2
Type: AFK

Rationale:

Users need clear language-support documentation and release validation for the
expanded language set implemented in this run. This task is scoped to Python
and MATLAB; Go and Rust remain planned future tasks.

Work:

- Update README and support docs with the Python/MATLAB language list, file
  extensions, parser dependencies, and known limitations.
- Add validation notes for Python and MATLAB fixture coverage.
- Extend artifact smoke coverage to prove added languages work through the PEX.
- Record known limitations for MATLAB scripts, MATLAB `.mlx`, Python dynamic
  imports, and unresolved runtime-dispatched calls.

Deliverable:

- Documentation and validation evidence for expanded language support.

Acceptance:

- README lists Java, C++, Python, and MATLAB support with caveats.
- README does not claim Go or Rust support.
- Validation notes include representative Python and MATLAB context bundle
  results.
- PEX smoke or acceptance coverage exercises at least one newly supported
  language.
- `make ci` and `make artifact-smoke` pass.
