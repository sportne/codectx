# Task Decomposition

This document defines an ordered, executable task plan for building the MVP.

Each task is intended to be small enough for a focused implementation cycle and concrete enough to verify. The order favors getting to a useful context bundle as quickly as possible while preserving architecture for later enrichment.

## Milestone summary

| Milestone | Outcome |
| --- | --- |
| M0 | Project skeleton and development baseline. |
| M1 | Source substrate: scan files, store metadata, retrieve snippets. |
| M2 | SQLite graph store and core fact model. |
| M3 | Tree-sitter Java/C++ definition extraction. |
| M4 | Symbol search and file/line anchor resolution. |
| M5 | Context bundle v0 for `explain`. |
| M6 | Call-like references, unresolved edges, and neighborhoods. |
| M7 | Ranking, token budgeting, and provenance traces. |
| M8 | Additional context goals: `failure-modes`, `dependencies`, `call-neighborhood`. |
| M9 | Verification, validation, and MVP hardening. |

## Task format

Each task includes:

```text
ID
Title
Status
Depends on
Requirement coverage
Work
Deliverable
Acceptance
```

Status values are `todo`, `in_progress`, `blocked`, or `done`.

---

## M0 — Project skeleton and baseline

### T001 — Create Python package skeleton

Status: done

Depends on: none

Requirement coverage: CON-002, NFR-040

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

### T002 — Add CLI shell

Status: done

Depends on: T001

Requirement coverage: FR-100 through FR-107, NFR-001

Work:

- Implement `codectx.cli:main`.
- Add subcommands: `index`, `health`, `search`, `symbols`, `context`, `neighborhood`, `inspect-node`, `inspect-edge`.
- Each command should parse arguments and print a clear placeholder or dispatch to stub service functions.

Deliverable:

- Working CLI entry point.

Acceptance:

- `codectx --help` lists commands.
- `codectx index --help` shows repo argument.
- Stub commands return successful exit code or explicit not-yet-implemented message.

### T003 — Define core dataclasses

Status: done

Depends on: T001

Requirement coverage: FR-024, FR-046, NFR-040, NFR-043

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

### T010 — Implement language detection

Status: done

Depends on: T003

Requirement coverage: FR-003

Work:

- Map file extensions to `java`, `cpp`, or unsupported.
- Treat C++ headers as `cpp` for MVP.
- Add path-based test file hints.

Deliverable:

- `scanner/language_detect.py`.

Acceptance:

- Unit tests cover `.java`, `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hh`, `.hxx`, `.h`.
- Unsupported files return `None` or equivalent.

### T011 — Implement repository scanner

Status: done

Depends on: T010

Requirement coverage: FR-001, FR-002, FR-006, FR-007

Work:

- Walk repository recursively.
- Skip built-in ignored directories.
- Return `FileRecord` candidates with repo-relative paths.
- Mark likely tests and likely generated/vendor files.

Deliverable:

- `scanner/repo.py`.

Acceptance:

- Integration test over a temporary repo finds expected Java/C++ files and skips `.git`, `build`, `.codectx`, and `node_modules`.

### T012 — Implement hashing and line offsets

Status: done

Depends on: T011

Requirement coverage: FR-004, FR-005, FR-012

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

### T013 — Implement source snippet extraction

Status: done

Depends on: T012

Requirement coverage: FR-010, FR-011, FR-013

Work:

- Retrieve text by byte span.
- Retrieve text by line range.
- Include optional surrounding context lines.
- Implement rough token estimator: `ceil(chars / 4)`.

Deliverable:

- `source/snippets.py`, `source/tokens.py`.

Acceptance:

- Unit tests verify exact snippets and line numbering.
- Token estimate is deterministic.

### T014 — Add CI quality gate

Status: done

Depends on: T013

Requirement coverage: development baseline

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

### T020 — Implement SQLite schema

Status: done

Depends on: T003

Requirement coverage: FR-040, FR-041, FR-046

Work:

- Create `graph/schema.sql`.
- Include tables: `repo`, `snapshot`, `file`, `node`, `edge`, `occurrence`, `chunk`, `diagnostic`, `index_stat`.
- Include indexes for common lookup and traversal.
- Store schema version.

Deliverable:

- SQL schema file.

Acceptance:

- Schema applies to empty SQLite database.
- `PRAGMA integrity_check` passes.
- Required tables and indexes exist.

### T021 — Implement GraphStore connection and schema application

Status: done

Depends on: T020

Requirement coverage: FR-040, FR-041, NFR-022

Work:

- Open SQLite connection.
- Apply pragmas.
- Apply schema.
- Check schema version.
- Provide context manager or close method.

Deliverable:

- `graph/store.py`.

Acceptance:

- Unit test creates temp DB and applies schema.
- Re-applying schema is safe.

### T022 — Persist repository snapshot and files

Status: done

Depends on: T021, T012

Requirement coverage: FR-010, FR-040

Work:

- Insert repo row.
- Insert snapshot row.
- Insert file rows from scanner.
- Store line count, hash, language, flags.

Deliverable:

- File persistence methods.

Acceptance:

- Integration test indexes a temp repo and verifies file rows.

### T023 — Persist graph facts

Status: done

Depends on: T021, T003

Requirement coverage: FR-024, FR-025, FR-026, FR-027, FR-028, FR-046

Work:

- Insert node facts.
- Insert edge facts, including unresolved edges.
- Insert occurrence facts.
- Insert chunk facts.
- Insert diagnostic facts.
- Preserve extractor, confidence, metadata.

Deliverable:

- Batch insert methods in `GraphStore`.

Acceptance:

- Unit tests insert sample facts and read them back.
- Unresolved edge insert succeeds.

### T024 — Implement index health stats persistence

Status: done

Depends on: T022, T023

Requirement coverage: FR-029, FR-107, NFR-022

Work:

- Persist counts for files, languages, nodes, edges, occurrences, chunks, diagnostics, unresolved references.
- Add `health` CLI command to display stats.

Deliverable:

- `index_stat` storage and `health` command.

Acceptance:

- `codectx health --repo fixture` displays stats after indexing.

---

## M3 — Tree-sitter definition extraction

### T029 — Add internal indexing service

Status: done

Depends on: T024

Requirement coverage: FR-100, FR-107

Work:

- Move index orchestration out of `cli.py`.
- Create internal service for scanning, persistence, health stats, and health lookup.
- Keep CLI focused on argument parsing and output formatting.

Deliverable:

- `codectx/indexing.py`.

Acceptance:

- Existing `index` and `health` CLI tests pass through the service.
- Unit tests cover default DB path, rebuild cleanup, missing health, and stat output.

### T030 — Implement Tree-sitter frontend base

Status: done

Depends on: T003, T013

Requirement coverage: FR-020, FR-021, FR-024

Work:

- Create a shared frontend protocol.
- Implement parser initialization abstraction.
- Implement helper functions for node text, spans, and child traversal.

Deliverable:

- `frontends/base.py` and common Tree-sitter utilities.

Acceptance:

- Unit test can parse a minimal Java and C++ source string through frontend helpers.

### T031 — Implement Java parser harness

Status: done

Depends on: T030

Requirement coverage: FR-020, FR-029

Work:

- Initialize Java Tree-sitter parser.
- Parse source bytes.
- Detect parser errors.
- Emit parser diagnostic facts.

Deliverable:

- `frontends/java_treesitter.py` parser harness.

Acceptance:

- Fixture test parses valid Java and reports no fatal error.
- Invalid Java records diagnostic without crashing.

### T032 — Implement C++ parser harness

Status: done

Depends on: T030

Requirement coverage: FR-021, FR-029

Work:

- Initialize C++ Tree-sitter parser.
- Parse source bytes.
- Detect parser errors.
- Emit parser diagnostic facts.

Deliverable:

- `frontends/cpp_treesitter.py` parser harness.

Acceptance:

- Fixture test parses valid C++ and reports no fatal error.
- Invalid C++ records diagnostic without crashing.

### T033 — Extract Java definitions

Status: done

Depends on: T031

Requirement coverage: FR-022, FR-025

Work:

- Extract package declaration metadata.
- Extract imports.
- Extract type declarations.
- Extract methods and constructors.
- Extract fields.
- Emit containment edges.
- Emit chunks for definitions.

Deliverable:

- Java definition extraction.

Acceptance:

- Java fixture test verifies expected nodes and containment edges.
- Extracted spans point to correct source lines.

### T034 — Extract C++ definitions

Status: done

Depends on: T032

Requirement coverage: FR-023, FR-025

Work:

- Extract includes.
- Extract namespaces.
- Extract classes/structs/enums.
- Extract free functions and methods.
- Extract constructors/destructors when identifiable.
- Extract fields.
- Emit containment edges.
- Emit chunks for definitions.

Deliverable:

- C++ definition extraction.

Acceptance:

- C++ fixture test verifies expected nodes and containment edges.
- Extracted spans point to correct source lines.

### T035 — Wire frontends into `codectx index`

Status: done

Depends on: T022, T023, T033, T034

Requirement coverage: FR-100, FR-020 through FR-029

Work:

- Scanner discovers files.
- Frontend extracts facts per supported language.
- GraphStore persists facts.
- Health stats printed after index.

Deliverable:

- Functional `codectx index` for Java/C++ definitions.

Acceptance:

- `codectx index tests/fixtures/java_basic` creates DB with nodes.
- `codectx index tests/fixtures/cpp_basic` creates DB with nodes.

---

## M4 — Symbol search and anchor resolution

### T040 — Implement symbol search query

Status: todo

Depends on: T035

Requirement coverage: FR-042, FR-101, FR-102

Work:

- Query node table by name, qualified name, and path.
- Rank exact matches above substring matches.
- Return file and line range.

Deliverable:

- `graph/query.py` symbol search function and CLI command.

Acceptance:

- `codectx symbols PaymentService --repo fixture` returns expected node.

### T041 — Add optional FTS support

Status: todo

Depends on: T040

Requirement coverage: FR-042, NFR-010 through NFR-013

Work:

- Detect FTS5 support.
- Create FTS tables when supported.
- Populate symbol/chunk FTS entries.
- Fall back to `LIKE` search when unavailable.

Deliverable:

- FTS-backed search path with fallback.

Acceptance:

- Tests pass in both simulated FTS-available and FTS-unavailable modes.

### T042 — Implement file/line anchor resolution

Status: todo

Depends on: T035

Requirement coverage: FR-043, FR-060

Work:

- Given file path and line number, find smallest containing node.
- Prefer callable over type over file.
- Return candidate if ambiguous.

Deliverable:

- `context/anchors.py`.

Acceptance:

- Fixture test resolves a method body line to the method node.
- Line outside a method resolves to enclosing type or file.

### T043 — Implement node and edge inspection

Status: todo

Depends on: T035

Requirement coverage: FR-045, FR-105, FR-106

Work:

- Add `inspect-node` command.
- Add `inspect-edge` command.
- Display metadata, confidence, extractor, file, span.

Deliverable:

- Inspection CLI.

Acceptance:

- CLI displays expected details for fixture nodes/edges.

---

## M5 — Context bundle v0 for `explain`

### T050 — Define context bundle model

Status: done

Depends on: T003

Requirement coverage: FR-060 through FR-065, FR-080 through FR-084

Work:

- Define bundle dataclasses: `ContextBundle`, `ContextItem`, `OmittedItem`, `TraceItem`.
- Include query, anchor, health, ranked items, omitted items, uncertainty notes.

Deliverable:

- `context/bundle.py`.

Acceptance:

- Unit test serializes a bundle to dict/JSON.

### T051 — Generate required candidates for `explain`

Status: todo

Depends on: T042, T050

Requirement coverage: FR-060, FR-066

Work:

- Include target definition.
- Include enclosing type/namespace/file.
- Include imports/includes from same file.
- Include same-file sibling helpers as optional candidates.

Deliverable:

- `context/planner.py` initial explain candidate generation.

Acceptance:

- Fixture `explain` bundle includes target method and enclosing class/type.

### T052 — Implement Markdown formatter

Status: todo

Depends on: T050, T051

Requirement coverage: FR-080, NFR-002

Work:

- Render bundle header.
- Render target summary.
- Render health summary.
- Render ranked snippets with code fences.
- Render reasons and uncertainty notes.

Deliverable:

- `context/formatters.py` Markdown output.

Acceptance:

- Markdown output contains file paths, line ranges, reasons, and balanced code fences.

### T053 — Implement JSON formatter

Status: todo

Depends on: T050, T051

Requirement coverage: FR-081

Work:

- Serialize bundle to structured JSON.
- Preserve scores, reasons, confidence, provenance, text.

Deliverable:

- JSON output support.

Acceptance:

- JSON parses successfully and required fields exist.

### T054 — Implement plain text formatter

Status: todo

Depends on: T050, T051

Requirement coverage: FR-082

Work:

- Render simple text format without Markdown-specific syntax.

Deliverable:

- Plain text output support.

Acceptance:

- Plain text output includes target, files, lines, reasons, snippets.

### T055 — Wire `codectx context --goal explain`

Status: todo

Depends on: T051, T052, T053, T054

Requirement coverage: FR-060, FR-066, FR-080 through FR-084, FR-103

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

### T060 — Extract Java call-like occurrences

Status: todo

Depends on: T033, T035

Requirement coverage: FR-027, FR-028

Work:

- Extract method invocation expressions.
- Identify enclosing callable.
- Store occurrence text and unresolved call edge.
- Resolve same-class method calls when obvious.

Deliverable:

- Java call-like extraction.

Acceptance:

- Fixture test shows `authorize` has call-like edge to `validate` or unresolved `gateway.charge`.

### T061 — Extract C++ call-like occurrences

Status: todo

Depends on: T034, T035

Requirement coverage: FR-027, FR-028

Work:

- Extract call expressions.
- Identify enclosing function/method.
- Store occurrence text and unresolved call edge.
- Resolve same-file/same-class calls when obvious.

Deliverable:

- C++ call-like extraction.

Acceptance:

- Fixture test shows target function has call-like edges.

### T062 — Extract Java/C++ references to types and fields heuristically

Status: todo

Depends on: T060, T061

Requirement coverage: FR-027, FR-028, FR-068

Work:

- Capture identifier/qualified-identifier occurrences in target spans.
- Avoid expression-level graph explosion by storing occurrences, not all tokens as nodes.
- Resolve unique project-wide names where safe.

Deliverable:

- Occurrence extraction and weak reference edges.

Acceptance:

- Fixture tests show selected type references and unresolved references.

### T063 — Implement bounded graph neighborhood query

Status: todo

Depends on: T060, T061, T062

Requirement coverage: FR-044, FR-104

Work:

- Traverse edges from seed node.
- Support direction and depth.
- Support edge-kind allowlist.
- Return nodes/edges with confidence and provenance.

Deliverable:

- `graph/traversal.py` and `neighborhood` CLI.

Acceptance:

- `codectx neighborhood --symbol X --depth 1` shows direct relationships.

### T064 — Add neighborhood candidates to `explain`

Status: todo

Depends on: T063, T055

Requirement coverage: FR-066

Work:

- Include likely direct callees.
- Include likely references/types.
- Include unresolved relationship notes.
- Include relevant tests by naming/path heuristics.

Deliverable:

- Improved `explain` bundle.

Acceptance:

- Fixture bundle includes direct callee snippets where resolvable and unresolved call notes where not.

---

## M7 — Ranking, budgeting, and provenance traces

### T070 — Implement scoring model

Status: todo

Depends on: T064

Requirement coverage: FR-061, NFR-043

Work:

- Implement score components: target, exact match, edge relevance, graph proximity, source proximity, lexical match, enclosing context, test context, confidence, token cost.
- Store score trace per candidate.

Deliverable:

- `context/ranking.py`.

Acceptance:

- Unit tests show target definition outranks unrelated sibling.
- Score trace is included in JSON output.

### T071 — Implement token budget pruning

Status: todo

Depends on: T070

Requirement coverage: FR-062, NFR-023

Work:

- Estimate tokens for each candidate.
- Always include required items.
- Select optional items by score/token ratio.
- Deduplicate overlapping snippets.
- Track omitted items.

Deliverable:

- Budget-aware selection.

Acceptance:

- Bundle stays within budget tolerance on fixture cases.
- Omitted items list includes high-scoring excluded candidates.

### T072 — Add goal-specific edge weights

Status: todo

Depends on: T070

Requirement coverage: FR-066, FR-067, FR-068

Work:

- Define relation weights per goal.
- Start with `explain`, `failure-modes`, `dependencies`, `call-neighborhood`.

Deliverable:

- Goal policy module or configuration.

Acceptance:

- Unit tests show different goals rank candidates differently.

### T073 — Add provenance and uncertainty rendering

Status: todo

Depends on: T071

Requirement coverage: FR-063, FR-064, FR-084, CON-008

Work:

- Render confidence labels.
- Render extractor names.
- Render unresolved edge notes.
- Render parser diagnostic warnings.

Deliverable:

- Improved bundle formatters.

Acceptance:

- Low-confidence edges are visibly labeled in Markdown and JSON.

---

## M8 — Additional context goals

### T080 — Implement `failure-modes` goal

Status: todo

Depends on: T072, T073

Requirement coverage: FR-067

Work:

- Prioritize throws clauses, diagnostics, error-named calls, validation methods, guards, tests with failure/error names.
- Include target definition and relevant callees.

Deliverable:

- `--goal failure-modes` context planning.

Acceptance:

- Fixture bundle includes validation/error snippets before unrelated helpers.

### T081 — Implement `dependencies` goal

Status: todo

Depends on: T072, T073

Requirement coverage: FR-068

Work:

- Prioritize imports/includes, used types, fields, constructor-injected dependencies, direct callees.

Deliverable:

- `--goal dependencies` context planning.

Acceptance:

- Fixture bundle includes import/include and dependency snippets.

### T082 — Implement `call-neighborhood` goal

Status: todo

Depends on: T063, T072, T073

Requirement coverage: FR-068, FR-104

Work:

- Prioritize likely callers and callees.
- Label heuristic edges.
- Include source snippets for resolvable callable nodes.

Deliverable:

- `--goal call-neighborhood` context planning.

Acceptance:

- Fixture bundle distinguishes callers, callees, and unresolved calls.

---

## M9 — Verification, validation, and MVP hardening

### T090 — Create Java golden fixture repository

Status: todo

Depends on: T080, T081, T082

Requirement coverage: V&V fixture coverage

Work:

- Create `tests/fixtures/java_basic` with main and test code.
- Include expected node/edge/context outputs.

Deliverable:

- Java golden fixture.

Acceptance:

- Fixture tests run in CI/local test suite.

### T091 — Create C++ golden fixture repository

Status: todo

Depends on: T080, T081, T082

Requirement coverage: V&V fixture coverage

Work:

- Create `tests/fixtures/cpp_basic` with header, source, and test code.
- Include expected node/edge/context outputs.

Deliverable:

- C++ golden fixture.

Acceptance:

- Fixture tests run in CI/local test suite.

### T092 — Implement CLI acceptance tests

Status: todo

Depends on: T090, T091

Requirement coverage: FR-100 through FR-107

Work:

- Run CLI commands against fixtures.
- Assert exit codes and key output fields.

Deliverable:

- CLI test suite.

Acceptance:

- Tests cover `index`, `health`, `symbols`, `context`, `neighborhood`, `inspect-node`, `inspect-edge`.

### T093 — Implement database integrity checks

Status: todo

Depends on: T092

Requirement coverage: NFR-020 through NFR-023

Work:

- Add `codectx health --integrity` option.
- Run `PRAGMA integrity_check` and `foreign_key_check`.
- Validate spans and unresolved edge invariants.

Deliverable:

- Integrity check command and tests.

Acceptance:

- Fixture DB passes integrity checks.

### T094 — Add performance smoke tests

Status: todo

Depends on: T092

Requirement coverage: NFR-010 through NFR-013

Work:

- Generate synthetic fixture repos.
- Measure index and query duration.
- Print performance stats.

Deliverable:

- Non-strict performance smoke tests.

Acceptance:

- Tests can be run manually or as optional CI marker.

### T095 — Manual validation on real repositories

Status: todo

Depends on: T093

Requirement coverage: MVP success criteria

Work:

- Choose one Java and one C++ repository.
- Run index and context queries.
- Score bundles using validation rubric.
- Record issues and tuning notes.

Deliverable:

- `docs/validation-notes.md` or equivalent.

Acceptance:

- At least five `explain` bundles and three `failure-modes` bundles reviewed.
- Critical usability issues are converted into tasks or fixed.

### T096 — MVP polish and documentation pass

Status: todo

Depends on: T095

Requirement coverage: all MVP requirements

Work:

- Update README with actual commands.
- Add quickstart.
- Document limitations.
- Document known unsupported cases.
- Ensure CLI help is accurate.

Deliverable:

- MVP-ready documentation.

Acceptance:

- New user can install, index a fixture, and generate a bundle using README instructions.

### T097 — MVP acceptance review

Status: todo

Depends on: T096

Requirement coverage: MVP success criteria

Work:

- Review requirements checklist.
- Review V&V evidence.
- Review known limitations.
- Tag or mark MVP release candidate.

Deliverable:

- MVP acceptance checklist.

Acceptance:

- Requirements owner agrees the MVP is functional and useful.

## Suggested implementation order

Strict minimum path to first useful bundle:

```text
T001 → T002 → T003
T010 → T011 → T012 → T013
T020 → T021 → T022 → T023 → T024
T030 → T031 → T032 → T033 → T034 → T035
T040 → T042
T050 → T051 → T052 → T053 → T055
```

This yields a first useful `explain` context bundle even before call-like references and advanced ranking.

Then continue:

```text
T060 → T061 → T062 → T063 → T064
T070 → T071 → T072 → T073
T080 → T081 → T082
T090 → T091 → T092 → T093 → T094 → T095 → T096 → T097
```

## MVP completion definition

The MVP is complete when:

1. `codectx index` works on Java and C++ repositories without requiring builds.
2. `codectx context` supports file/line and symbol anchors.
3. Markdown and JSON bundles include ranked snippets, reasons, file paths, line ranges, token estimates, confidence, and uncertainty notes.
4. `explain`, `failure-modes`, `dependencies`, and `call-neighborhood` goals work heuristically.
5. The verification suite passes.
6. Manual validation shows bundles are useful for preparing LLM prompts.
