# MVP Acceptance Review

Date: 2026-05-25

## Summary

MVP status: release-candidate ready for local Java and C++ context packaging.

The implemented CLI can index local Java and C++ repositories, persist a SQLite graph, search symbols/chunks, inspect graph facts, traverse bounded neighborhoods, and generate provenance-aware context bundles for `explain`, `failure-modes`, `dependencies`, and `call-neighborhood`.

## Requirement Coverage

| Area | Status | Evidence |
| --- | --- | --- |
| Repository scanning and source substrate | Complete | Scanner, hashing, spans, snippets, and fixture tests pass in `make ci`. |
| SQLite persistence and health stats | Complete | Graph store tests, indexing service tests, and CLI acceptance tests pass. |
| Java and C++ extraction | Complete for MVP heuristics | Golden Java/C++ fixtures cover definitions, imports/includes, calls, references, chunks, diagnostics, and persisted rows. |
| Search and inspection | Complete | `symbols`, `search`, `neighborhood`, `inspect-node`, and `inspect-edge` covered by CLI acceptance tests. |
| Context bundle generation | Complete | Markdown, JSON, and text formatters plus all four MVP goals are covered by unit, golden, and CLI tests. |
| Ranking, budgeting, provenance, uncertainty | Complete | Ranking/pruning tests and formatter tests cover score traces, confidence, extractor provenance, omitted candidates, and uncertainty notes. |
| Local-only privacy | Complete | README documents local operation and no built-in LLM, telemetry, or upload behavior. |
| MVP limitations | Documented | README and validation notes describe heuristic Java/C++ analysis limits and unresolved relationships. |

## Local Gates

Final local gate for T097:

```bash
make ci
```

Observed status on 2026-05-25: pass.

The gate includes Ruff formatting, Ruff linting, mypy strict type checking, Vulture reachability/dead-code checks, architecture tests, full pytest coverage, and per-file coverage threshold enforcement.

## Fixture Status

| Fixture | Coverage |
| --- | --- |
| `tests/fixtures/java_basic` | Definitions, imports, fields, resolved/unresolved calls, failure-mode methods, related tests, golden graph output, and `explain`/`failure-modes` context output. |
| `tests/fixtures/cpp_basic` | Includes, namespace/type/function extraction, fields, calls, unresolved calls, tests, golden graph output, and `explain`/`dependencies` context output. |

CLI acceptance tests run both fixtures through `index`, `health`, `symbols`, `search`, `context`, `neighborhood`, `inspect-node`, and `inspect-edge`.

## Integrity Status

`codectx health --integrity` now checks:

- SQLite `PRAGMA integrity_check`.
- SQLite `PRAGMA foreign_key_check`.
- Span byte and line ordering/bounds.
- Cross-snapshot file references.
- Unresolved edge endpoint invariants.

Passing fixture and intentionally corrupted database cases are covered by tests.

## Performance Smoke

Optional smoke tests live in `tests/test_performance_smoke.py` and are skipped by default. Run them manually with:

```bash
CODECTX_PERF_SMOKE=1 $(HOME)/.venvs/codectx/bin/python -m pytest -s tests/test_performance_smoke.py
```

They generate a synthetic 100-file Java/C++ repo and report index duration, representative query durations, database size, source size, and DB/source size ratio. They are non-strict smoke tests and are not part of default `make ci` timing guarantees.

## Manual Validation

Manual validation notes are recorded in [`validation-notes.md`](validation-notes.md).

Validated repositories:

- `/mnt/d/projects/mundane-java-di`
- `/mnt/d/projects/cpp-helper-libs`

Excluded repository:

- `/mnt/d/projects/WSL2-Linux-Kernel`

Validation reviewed five `explain` bundles and three `failure-modes` bundles. Java bundles were generally useful and stable. C++ bundles were usable for target/enclosing context but showed expected heuristic limits, especially high unresolved-reference counts and third-party parser diagnostics.

## Acceptance Decision

The MVP is functional and useful for local prompt-preparation workflows under the documented limitations.

Known caveats do not block MVP acceptance:

- C++ semantic resolution is heuristic and can leave many unresolved relationships.
- Vendored or third-party C++ files can contribute noisy parser diagnostics.
- Large enclosing scopes can consume much of a small context budget.
- Context bundles are source-grounded aids, not compiler or static-analysis proofs.
