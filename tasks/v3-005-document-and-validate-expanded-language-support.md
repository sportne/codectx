# V3-005 - Document and validate expanded language support

ID: V3-005
Title: Document and validate expanded language support
Status: todo
Depends on: V3-001, V3-002, V3-003, V3-004
Requirement coverage: Language expansion; scanner, frontend extraction, indexing, querying, and context bundle behavior.
Milestone: V3 - Additional language support
Priority: P2
Type: AFK

Rationale:

Users need clear language-support documentation and release validation once Python, MATLAB, Go, and Rust are indexed by default.

Work:

- Update README and support docs with the expanded language list, file extensions, parser dependencies, and known limitations.
- Add or update real-repo/manual usability evaluation targets for at least Python and MATLAB, with Go and Rust targets if representative repos are available.
- Extend release or artifact smoke coverage to prove at least one added language works through the PEX.
- Record known limitations for MATLAB scripts, Rust macros, Python dynamic imports, and unresolved cross-language references.

Deliverable:

- Documentation and validation evidence for expanded language support.

Acceptance:

- README lists Python, MATLAB, Go, and Rust support with caveats.
- Validation notes include representative expanded-language context bundle results.
- PEX smoke or acceptance coverage exercises at least one newly supported language.
- `make ci` and `make artifact-smoke` pass.
