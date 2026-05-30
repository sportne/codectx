# Requirements

Historical note: this document records the MVP requirements used to build the
initial tool. It is useful project history, but the current 1.0 user contract
is defined by [`../README.md`](../README.md) and
[`06-1.0-release-criteria.md`](06-1.0-release-criteria.md).

## 1. Purpose

`codectx` shall provide a local, standalone way to index a source repository into a durable code graph and generate ranked context bundles that a human can manually transfer into an LLM.

The system shall prioritize practical, useful context over compiler-perfect semantic analysis.

## 2. Product scope

### 2.1 In scope for MVP

The MVP shall support:

- Local repository indexing.
- Python implementation.
- SQLite persistence.
- Java and C++ syntax-aware extraction using Tree-sitter.
- Source file, span, symbol, occurrence, edge, and chunk storage.
- Heuristic graph relationships, clearly labeled with confidence and provenance.
- Context bundle generation for selected file/line or symbol anchors.
- Markdown, JSON, and plain-text bundle output.
- Ranking and pruning to a user-specified token budget.
- Inspection commands for graph nodes, edges, and index health.

### 2.2 Explicitly out of scope for MVP

The MVP shall not require or implement:

- Direct LLM API integration.
- MCP or agent tool integration.
- Remote services.
- Cloud indexing.
- Compiler-perfect static analysis.
- Required build-system integration.
- Required SCIP, LSP, Gradle, Maven, CMake, Bazel, or Clang integration.
- Neo4j or external graph database infrastructure.
- Embedding models as required dependencies.
- IDE plugin functionality.

Optional future features may import additional semantic data if available, but core usefulness must not depend on them.

## 3. Users and use cases

### 3.1 Primary user

A developer who wants to ask an LLM about unfamiliar or complex code, but needs help gathering the right repository context first.

### 3.2 Secondary users

- A maintainer preparing context for code reviews or debugging sessions.
- A developer working in an environment where direct LLM tool integration is not available or not allowed.
- A user who wants reproducible, inspectable context selection instead of ad hoc file copying.

### 3.3 Primary use cases

| ID | Use case | Description |
| --- | --- | --- |
| UC-001 | Explain symbol | Given a file/line or symbol name, gather context for understanding the target method/function/type. |
| UC-002 | Failure modes | Given a method/function, gather likely error-handling, validation, exception, diagnostic, and callee context. |
| UC-003 | Dependency context | Given a symbol, gather relevant imports/includes, used types, direct callees, and neighboring helpers. |
| UC-004 | Call neighborhood | Given a callable, show likely callers/callees and source snippets under a budget. |
| UC-005 | Manual LLM transfer | Emit Markdown/plain text suitable for copy/paste into any LLM interface. |
| UC-006 | Inspect graph | Let a user inspect why a context item was selected and where graph facts came from. |

## 4. Constraints

| ID | Constraint | Requirement |
| --- | --- | --- |
| CON-001 | Local-only | The MVP shall not require network or remote services. |
| CON-002 | Python permanent | The implementation shall be designed to remain Python-based rather than treating Python as a temporary prototype. |
| CON-003 | Free-standing | The tool shall operate on arbitrary local repositories even if they do not build. |
| CON-004 | Polyglot-first | The core graph schema shall avoid Java-only or C++-only assumptions. |
| CON-005 | Source-grounded | Context output shall include file paths and line ranges for selected snippets. |
| CON-006 | Inspectable | Context output shall include reasons, scores, confidence, and extractor provenance. |
| CON-007 | Dependency-light | The MVP shall avoid large framework dependencies and service dependencies. |
| CON-008 | Honest uncertainty | Heuristic and unresolved relationships shall be represented without pretending they are precise. |

## 5. Functional requirements

### 5.1 Repository scanning

| ID | Requirement | MVP acceptance |
| --- | --- | --- |
| FR-001 | The system shall recursively scan a local repository path. | `codectx index PATH` discovers source files under PATH. |
| FR-002 | The scanner shall ignore common non-source directories. | `.git`, build outputs, dependency caches, and virtual environments are skipped by default. |
| FR-003 | The scanner shall classify files by language. | `.java`, `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hh`, `.hxx`, and `.h` are classified. |
| FR-004 | The scanner shall compute content hashes. | Each indexed file has a stable content hash. |
| FR-005 | The scanner shall compute line offsets. | Source spans can be translated between bytes and line/column positions. |
| FR-006 | The scanner shall identify likely test files. | Files matching common naming/path conventions are flagged as tests. |
| FR-007 | The scanner shall identify likely generated/vendor files when possible. | Basic path/name heuristics are stored as metadata. |

### 5.2 Source storage and snippet extraction

| ID | Requirement | MVP acceptance |
| --- | --- | --- |
| FR-010 | The system shall store enough file metadata to reproduce snippets. | File path, content hash, language, size, and line count are persisted. |
| FR-011 | The system shall retrieve source snippets by file and line range. | Context output and graph inspection can display source-grounded line ranges. |
| FR-012 | The system shall use byte offsets as canonical span coordinates. | Spans include start/end bytes and display line ranges. |
| FR-013 | The system shall estimate token cost for snippets. | Each chunk has a rough token estimate. |

### 5.3 Graph extraction

| ID | Requirement | MVP acceptance |
| --- | --- | --- |
| FR-020 | The system shall parse Java files with Tree-sitter. | Java files produce parser diagnostics and extractable syntax nodes. |
| FR-021 | The system shall parse C++ files with Tree-sitter. | C++ files produce parser diagnostics and extractable syntax nodes. |
| FR-022 | The Java frontend shall extract package/import/type/callable/field facts. | Classes/interfaces/enums/records, methods/constructors, fields, imports are represented. |
| FR-023 | The C++ frontend shall extract include/namespace/type/callable/field facts. | Namespaces, classes/structs/enums, functions/methods, fields, includes are represented. |
| FR-024 | The frontends shall emit generic graph facts rather than language-specific database rows. | Java and C++ facts can be inserted into the same node/edge tables. |
| FR-025 | The graph shall represent containment. | Files contain types/functions; types contain methods/fields. |
| FR-026 | The graph shall represent imports/includes. | Java imports and C++ includes are edges or occurrences with source spans. |
| FR-027 | The graph shall represent call-like occurrences. | Method/function-call-like syntax emits occurrence and possible `calls` edge facts. |
| FR-028 | The graph shall allow unresolved edges. | Calls like `gateway.charge` can be stored without resolved destination node. |
| FR-029 | The graph shall represent parser diagnostics. | Files with parse errors record diagnostic facts or index health entries. |

### 5.4 Graph storage and querying

| ID | Requirement | MVP acceptance |
| --- | --- | --- |
| FR-040 | The system shall persist graph data in SQLite. | `.codectx/graph.sqlite` is created by `index`. |
| FR-041 | The graph store shall support schema migration/versioning. | Schema version is stored and checked. |
| FR-042 | The graph store shall support symbol lookup by name. | `codectx symbols QUERY` returns matching symbols. |
| FR-043 | The graph store shall support anchor lookup by file/line. | `context --file PATH --line N` resolves the enclosing symbol. |
| FR-044 | The graph store shall support bounded neighborhood queries. | `neighborhood --symbol X --depth N` returns related nodes/edges. |
| FR-045 | The graph store shall support node and edge inspection. | `inspect-node` and `inspect-edge` display persisted facts. |
| FR-046 | The graph store shall preserve provenance and confidence. | Nodes/edges/occurrences include extractor and confidence fields. |

### 5.5 Context planning

| ID | Requirement | MVP acceptance |
| --- | --- | --- |
| FR-060 | The system shall generate a context bundle for a symbol or file/line. | `codectx context` emits Markdown/JSON/plain text. |
| FR-061 | The system shall rank candidate snippets. | Output items include rank and score. |
| FR-062 | The system shall prune to a budget. | Output respects approximate `--budget` token target. |
| FR-063 | The system shall include item reasons. | Each selected item has a human-readable reason. |
| FR-064 | The system shall include source provenance. | Each selected snippet has file path and line range. |
| FR-065 | The system shall report omissions. | Important omitted items can be listed with reasons. |
| FR-066 | The system shall support at least `explain` goal. | `--goal explain` returns target, enclosing context, calls, imports/includes, and related snippets. |
| FR-067 | The system shall support at least `failure-modes` goal. | Output prioritizes error-related code, throws, conditions, diagnostics, and callees heuristically. |
| FR-068 | The system shall support at least `dependencies` goal. | Output prioritizes imports/includes, used types, direct callees, and fields. |

### 5.6 Output formats

| ID | Requirement | MVP acceptance |
| --- | --- | --- |
| FR-080 | The system shall output Markdown context bundles. | `--format markdown` emits copy/paste-friendly Markdown. |
| FR-081 | The system shall output JSON context bundles. | `--format json` emits structured bundle data. |
| FR-082 | The system shall output plain text bundles. | `--format text` emits low-format copy/paste text. |
| FR-083 | Output shall include an index health summary. | Bundle header includes index status and known limitations. |
| FR-084 | Output shall clearly label heuristic facts. | Unresolved or low-confidence edges are not presented as certain. |

### 5.7 CLI behavior

| ID | Requirement | MVP acceptance |
| --- | --- | --- |
| FR-100 | The CLI shall provide `index`. | Indexes a repository and prints an index health report. |
| FR-101 | The CLI shall provide `search`. | Searches symbols/chunks. |
| FR-102 | The CLI shall provide `symbols`. | Lists candidate symbols matching a query. |
| FR-103 | The CLI shall provide `context`. | Generates context bundle. |
| FR-104 | The CLI shall provide `neighborhood`. | Displays bounded graph neighborhood. |
| FR-105 | The CLI shall provide `inspect-node`. | Displays node details. |
| FR-106 | The CLI shall provide `inspect-edge`. | Displays edge details. |
| FR-107 | The CLI shall provide `health`. | Shows index statistics, parser errors, unresolved references, and feature availability. |

## 6. Non-functional requirements

### 6.1 Usability

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | The CLI shall be understandable without documentation for common commands. | `--help` provides examples. |
| NFR-002 | Markdown output shall be manually copy/paste friendly. | Bundle includes headers, paths, lines, reasons, and fenced code blocks. |
| NFR-003 | Errors shall be actionable. | Missing index, unsupported file, and ambiguous symbol errors include next steps. |

### 6.2 Performance

Initial MVP performance targets are intentionally modest and local-machine oriented.

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-010 | Index a small repository. | 100 source files in under 30 seconds on a typical developer laptop. |
| NFR-011 | Index a medium repository. | 1,000 source files in under 5 minutes. |
| NFR-012 | Generate context. | Context query in under 10 seconds for an already-indexed medium repo. |
| NFR-013 | Database size. | SQLite DB should be reasonable relative to source size; track ratio during validation. |

### 6.3 Reliability and integrity

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-020 | Indexing shall be deterministic for unchanged input. | Re-indexing produces equivalent graph counts and hashes. |
| NFR-021 | Partial parse failures shall not abort the whole index. | File-level errors are recorded and index continues. |
| NFR-022 | Graph facts shall be auditable. | Extractor, confidence, file, span, and metadata are stored. |
| NFR-023 | Bundle generation shall not silently exceed budget by large margins. | Output target within configurable tolerance, initially ±20%. |

### 6.4 Privacy and security

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-030 | The tool shall not send code anywhere. | No network calls in MVP code path. |
| NFR-031 | The tool shall warn before writing outside repo/index path. | Output paths are explicit. |
| NFR-032 | The tool shall avoid executing repository code. | Indexing parses source files only. |

### 6.5 Maintainability

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-040 | Language extraction shall be isolated by frontend modules. | Java and C++ frontends use shared fact model. |
| NFR-041 | Tree-sitter extraction behavior shall be versioned with source. | Frontend modules and tests live in the repository with the rest of the source. |
| NFR-042 | SQL schema shall be explicit and tested. | Schema file is stored in source and migration tests cover it. |
| NFR-043 | Context ranking shall be explainable. | Score components are traceable for each item. |

## 7. Core graph model requirements

### 7.1 Node kinds

The MVP graph shall support these generic node kinds:

```text
repository
snapshot
directory
source_file
namespace
type
callable
field
variable
parameter
macro
diagnostic
external_symbol
chunk
```

Language-specific distinctions shall be stored in metadata, for example:

```json
{
  "language": "java",
  "language_kind": "class",
  "modifiers": ["public"],
  "annotations": ["Deprecated"]
}
```

### 7.2 Edge kinds

The MVP graph shall support these generic edge kinds:

```text
contains
defines
declares
references
calls
imports
includes
uses_type
reads
writes
returns
throws
annotated_by
tests
diagnostic_for
same_as
resolves_to
generated_from
```

The MVP does not need to populate all edge kinds, but the schema should not prevent them.

### 7.3 Required provenance fields

Every node, edge, and occurrence shall include:

```text
extractor
confidence
file/span when applicable
metadata_json
```

Confidence is numeric in storage and can be rendered as labels:

```text
0.90-1.00 resolved/high
0.60-0.89 strong heuristic
0.30-0.59 weak heuristic
0.00-0.29 low confidence
```

## 8. Context bundle requirements

A context bundle shall include:

1. Query information.
2. Target anchor information.
3. Index health summary.
4. Ranked source snippets.
5. Reason for each snippet.
6. File path and line range for each snippet.
7. Confidence/provenance for each snippet or graph path.
8. Approximate token count.
9. Omitted candidates when useful.
10. Uncertainty notes.

## 9. MVP success criteria

The MVP is considered useful when it can:

1. Index at least one non-trivial Java repository and one non-trivial C++ repository without requiring either to build.
2. Resolve a file/line anchor to an enclosing callable or type.
3. Produce a Markdown context bundle for `explain` that includes the target, enclosing context, imports/includes, same-file helpers, likely direct callees, and relevant tests when available.
4. Produce a JSON bundle with equivalent structured data.
5. Label unresolved or heuristic edges clearly.
6. Provide an index health report.
7. Stay within an approximate token budget.
8. Pass the MVP verification suite described in the V&V plan.

## 10. Requirement traceability

Implementation tasks in `docs/04-task-decomposition.md` reference these requirement IDs. Verification activities in `docs/03-verification-validation-plan.md` map tests back to these requirements.
