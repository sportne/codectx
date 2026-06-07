# Task Index

This directory is the active task tracker. Each task has a dedicated Markdown file using the project task format:

- ID
- Title
- Status
- Depends on
- Requirement coverage
- Work
- Deliverable
- Acceptance

Status values: `todo`, `in_progress`, `blocked`, `done`.

## M0 - Project skeleton and baseline

| Task | Name | Status | File |
| --- | --- | --- | --- |
| T001 | Create Python package skeleton | done | [t001-create-python-package-skeleton.md](t001-create-python-package-skeleton.md) |
| T002 | Add CLI shell | done | [t002-add-cli-shell.md](t002-add-cli-shell.md) |
| T003 | Define core dataclasses | done | [t003-define-core-dataclasses.md](t003-define-core-dataclasses.md) |

## M1 - Source substrate

| Task | Name | Status | File |
| --- | --- | --- | --- |
| T010 | Implement language detection | done | [t010-implement-language-detection.md](t010-implement-language-detection.md) |
| T011 | Implement repository scanner | done | [t011-implement-repository-scanner.md](t011-implement-repository-scanner.md) |
| T012 | Implement hashing and line offsets | done | [t012-implement-hashing-and-line-offsets.md](t012-implement-hashing-and-line-offsets.md) |
| T013 | Implement source snippet extraction | done | [t013-implement-source-snippet-extraction.md](t013-implement-source-snippet-extraction.md) |
| T014 | Add CI quality gate | done | [t014-add-ci-quality-gate.md](t014-add-ci-quality-gate.md) |

## M2 - SQLite graph store and fact persistence

| Task | Name | Status | File |
| --- | --- | --- | --- |
| T020 | Implement SQLite schema | done | [t020-implement-sqlite-schema.md](t020-implement-sqlite-schema.md) |
| T021 | Implement GraphStore connection and schema application | done | [t021-implement-graphstore-connection-and-schema-application.md](t021-implement-graphstore-connection-and-schema-application.md) |
| T022 | Persist repository snapshot and files | done | [t022-persist-repository-snapshot-and-files.md](t022-persist-repository-snapshot-and-files.md) |
| T023 | Persist graph facts | done | [t023-persist-graph-facts.md](t023-persist-graph-facts.md) |
| T024 | Implement index health stats persistence | done | [t024-implement-index-health-stats-persistence.md](t024-implement-index-health-stats-persistence.md) |

## M3 - Tree-sitter definition extraction

| Task | Name | Status | File |
| --- | --- | --- | --- |
| T029 | Add internal indexing service | done | [t029-add-internal-indexing-service.md](t029-add-internal-indexing-service.md) |
| T030 | Implement Tree-sitter frontend base | done | [t030-implement-tree-sitter-frontend-base.md](t030-implement-tree-sitter-frontend-base.md) |
| T031 | Implement Java parser harness | done | [t031-implement-java-parser-harness.md](t031-implement-java-parser-harness.md) |
| T032 | Implement C++ parser harness | done | [t032-implement-c-parser-harness.md](t032-implement-c-parser-harness.md) |
| T033 | Extract Java definitions | done | [t033-extract-java-definitions.md](t033-extract-java-definitions.md) |
| T034 | Extract C++ definitions | done | [t034-extract-c-definitions.md](t034-extract-c-definitions.md) |
| T035 | Wire frontends into `codectx index` | done | [t035-wire-frontends-into-codectx-index.md](t035-wire-frontends-into-codectx-index.md) |

## M4 - Symbol search and anchor resolution

| Task | Name | Status | File |
| --- | --- | --- | --- |
| T039 | Add internal query service | done | [t039-add-internal-query-service.md](t039-add-internal-query-service.md) |
| T040 | Implement symbol search query | done | [t040-implement-symbol-search-query.md](t040-implement-symbol-search-query.md) |
| T041 | Add optional FTS support | done | [t041-add-optional-fts-support.md](t041-add-optional-fts-support.md) |
| T042 | Implement file/line anchor resolution | done | [t042-implement-file-line-anchor-resolution.md](t042-implement-file-line-anchor-resolution.md) |
| T043 | Implement node and edge inspection | done | [t043-implement-node-and-edge-inspection.md](t043-implement-node-and-edge-inspection.md) |

## M5 - Context bundle v0 for `explain`

| Task | Name | Status | File |
| --- | --- | --- | --- |
| T049 | Add internal context service | done | [t049-add-internal-context-service.md](t049-add-internal-context-service.md) |
| T050 | Define context bundle model | done | [t050-define-context-bundle-model.md](t050-define-context-bundle-model.md) |
| T051 | Generate required candidates for `explain` | done | [t051-generate-required-candidates-for-explain.md](t051-generate-required-candidates-for-explain.md) |
| T052 | Implement Markdown formatter | done | [t052-implement-markdown-formatter.md](t052-implement-markdown-formatter.md) |
| T053 | Implement JSON formatter | done | [t053-implement-json-formatter.md](t053-implement-json-formatter.md) |
| T054 | Implement plain text formatter | done | [t054-implement-plain-text-formatter.md](t054-implement-plain-text-formatter.md) |
| T055 | Wire `codectx context --goal explain` | done | [t055-wire-codectx-context-goal-explain.md](t055-wire-codectx-context-goal-explain.md) |

## M6 - References, call-like edges, and neighborhoods

| Task | Name | Status | File |
| --- | --- | --- | --- |
| T059 | Add internal neighborhood service | done | [t059-add-internal-neighborhood-service.md](t059-add-internal-neighborhood-service.md) |
| T060 | Extract Java call-like occurrences | done | [t060-extract-java-call-like-occurrences.md](t060-extract-java-call-like-occurrences.md) |
| T061 | Extract C++ call-like occurrences | done | [t061-extract-c-call-like-occurrences.md](t061-extract-c-call-like-occurrences.md) |
| T062 | Extract Java/C++ references to types and fields heuristically | done | [t062-extract-java-c-references-to-types-and-fields-heuristically.md](t062-extract-java-c-references-to-types-and-fields-heuristically.md) |
| T063 | Implement bounded graph neighborhood query | done | [t063-implement-bounded-graph-neighborhood-query.md](t063-implement-bounded-graph-neighborhood-query.md) |
| T064 | Add neighborhood candidates to `explain` | done | [t064-add-neighborhood-candidates-to-explain.md](t064-add-neighborhood-candidates-to-explain.md) |

## M7 - Ranking, budgeting, and provenance traces

| Task | Name | Status | File |
| --- | --- | --- | --- |
| T069 | Lock indexing service boundary | done | [t069-lock-indexing-service-boundary.md](t069-lock-indexing-service-boundary.md) |
| T070 | Implement scoring model | done | [t070-implement-scoring-model.md](t070-implement-scoring-model.md) |
| T071 | Implement token budget pruning | done | [t071-implement-token-budget-pruning.md](t071-implement-token-budget-pruning.md) |
| T072 | Add goal-specific edge weights | done | [t072-add-goal-specific-edge-weights.md](t072-add-goal-specific-edge-weights.md) |
| T073 | Add provenance and uncertainty rendering | done | [t073-add-provenance-and-uncertainty-rendering.md](t073-add-provenance-and-uncertainty-rendering.md) |

## M8 - Additional context goals

| Task | Name | Status | File |
| --- | --- | --- | --- |
| T079 | Add shared context goal planning foundation | done | [t079-add-shared-context-goal-planning-foundation.md](t079-add-shared-context-goal-planning-foundation.md) |
| T080 | Implement `failure-modes` goal | done | [t080-implement-failure-modes-goal.md](t080-implement-failure-modes-goal.md) |
| T081 | Implement `dependencies` goal | done | [t081-implement-dependencies-goal.md](t081-implement-dependencies-goal.md) |
| T082 | Implement `call-neighborhood` goal | done | [t082-implement-call-neighborhood-goal.md](t082-implement-call-neighborhood-goal.md) |

## M9 - Verification, validation, and MVP hardening

| Task | Name | Status | File |
| --- | --- | --- | --- |
| T089 | Lock M9 indexing service boundary | done | [t089-lock-m9-indexing-service-boundary.md](t089-lock-m9-indexing-service-boundary.md) |
| T090 | Create Java golden fixture repository | done | [t090-create-java-golden-fixture-repository.md](t090-create-java-golden-fixture-repository.md) |
| T091 | Create C++ golden fixture repository | done | [t091-create-c-golden-fixture-repository.md](t091-create-c-golden-fixture-repository.md) |
| T092 | Implement CLI acceptance tests | done | [t092-implement-cli-acceptance-tests.md](t092-implement-cli-acceptance-tests.md) |
| T093 | Implement database integrity checks | done | [t093-implement-database-integrity-checks.md](t093-implement-database-integrity-checks.md) |
| T094 | Add performance smoke tests | done | [t094-add-performance-smoke-tests.md](t094-add-performance-smoke-tests.md) |
| T095 | Manual validation on real repositories | done | [t095-manual-validation-on-real-repositories.md](t095-manual-validation-on-real-repositories.md) |
| T096 | MVP polish and documentation pass | done | [t096-mvp-polish-and-documentation-pass.md](t096-mvp-polish-and-documentation-pass.md) |
| T097 | MVP acceptance review | done | [t097-mvp-acceptance-review.md](t097-mvp-acceptance-review.md) |

## V1 - 1.0 readiness

| Task | Name | Status | File |
| --- | --- | --- | --- |
| V1-001 | Define 1.0 release criteria and stable contracts | done | [v1-001-define-1-0-release-criteria-and-stable-contracts.md](v1-001-define-1-0-release-criteria-and-stable-contracts.md) |
| V1-002 | Build real-repo context quality evaluation harness | done | [v1-002-build-real-repo-context-quality-evaluation-harness.md](v1-002-build-real-repo-context-quality-evaluation-harness.md) |
| V1-003 | Add configurable include/exclude and ignore-file semantics | done | [v1-003-add-configurable-include-exclude-and-ignore-file-semantics.md](v1-003-add-configurable-include-exclude-and-ignore-file-semantics.md) |
| V1-004 | Improve token budgeting for large enclosing scopes | done | [v1-004-improve-token-budgeting-for-large-enclosing-scopes.md](v1-004-improve-token-budgeting-for-large-enclosing-scopes.md) |
| V1-005 | Reduce C++ vendor diagnostics and unresolved-reference noise | done | [v1-005-reduce-c-vendor-diagnostics-and-unresolved-reference-noise.md](v1-005-reduce-c-vendor-diagnostics-and-unresolved-reference-noise.md) |
| V1-006 | Pin and verify runtime dependency compatibility | done | [v1-006-pin-and-verify-runtime-dependency-compatibility.md](v1-006-pin-and-verify-runtime-dependency-compatibility.md) |
| V1-007 | Establish real-repo performance and storage gates | done | [v1-007-establish-real-repo-performance-and-storage-gates.md](v1-007-establish-real-repo-performance-and-storage-gates.md) |
| V1-008 | Stabilize release automation and artifact publishing | done | [v1-008-stabilize-release-automation-and-artifact-publishing.md](v1-008-stabilize-release-automation-and-artifact-publishing.md) |
| V1-009 | Harden Unicode, encoding, and binary-file handling | done | [v1-009-harden-unicode-encoding-and-binary-file-handling.md](v1-009-harden-unicode-encoding-and-binary-file-handling.md) |
| V1-010 | Simplify context planner internals without behavior drift | done | [v1-010-simplify-context-planner-internals-without-behavior-drift.md](v1-010-simplify-context-planner-internals-without-behavior-drift.md) |
| V1-011 | Document 1.0 user guarantees and known limitations | done | [v1-011-document-1-0-user-guarantees-and-known-limitations.md](v1-011-document-1-0-user-guarantees-and-known-limitations.md) |
| V1-012 | Decide whether incremental indexing belongs before 1.0 | done | [v1-012-decide-whether-incremental-indexing-belongs-before-1-0.md](v1-012-decide-whether-incremental-indexing-belongs-before-1-0.md) |

## V2 - File-only context anchors

| Task | Name | Status | File |
| --- | --- | --- | --- |
| V2-001 | Define the file-only context CLI contract | done | [v2-001-define-the-file-only-context-cli-contract.md](v2-001-define-the-file-only-context-cli-contract.md) |
| V2-002 | Resolve indexed files as first-class context anchors | done | [v2-002-resolve-indexed-files-as-first-class-context-anchors.md](v2-002-resolve-indexed-files-as-first-class-context-anchors.md) |
| V2-003 | Build file-level context from symbols in the file | done | [v2-003-build-file-level-context-from-symbols-in-the-file.md](v2-003-build-file-level-context-from-symbols-in-the-file.md) |
| V2-004 | Rank and budget file-level bundles without line proximity | done | [v2-004-rank-and-budget-file-level-bundles-without-line-proximity.md](v2-004-rank-and-budget-file-level-bundles-without-line-proximity.md) |
| V2-005 | Document and validate file-only context usage | done | [v2-005-document-and-validate-file-only-context-usage.md](v2-005-document-and-validate-file-only-context-usage.md) |

## V3 - Additional language support

| Task | Name | Status | File |
| --- | --- | --- | --- |
| V3-001 | Add Python indexing frontend | done | [v3-001-add-python-indexing-frontend.md](v3-001-add-python-indexing-frontend.md) |
| V3-002 | Add MATLAB indexing frontend | done | [v3-002-add-matlab-indexing-frontend.md](v3-002-add-matlab-indexing-frontend.md) |
| V3-003 | Add Go indexing frontend | done | [v3-003-add-go-indexing-frontend.md](v3-003-add-go-indexing-frontend.md) |
| V3-004 | Add Rust indexing frontend | todo | [v3-004-add-rust-indexing-frontend.md](v3-004-add-rust-indexing-frontend.md) |
| V3-005 | Document and validate expanded language support | done | [v3-005-document-and-validate-expanded-language-support.md](v3-005-document-and-validate-expanded-language-support.md) |
