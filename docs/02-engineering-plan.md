# Engineering Plan

## 1. Engineering goal

Build a standalone Python CLI that turns a local source repository into a durable SQLite code graph and emits ranked, source-grounded context bundles for manual LLM use.

The engineering priority is a functional MVP that is useful without compiler integration, network services, or direct LLM integration.

## 2. Core architecture

```text
local repo
  ↓
scanner
  - ignore rules
  - file discovery
  - language detection
  - content hashes
  - line offsets
  ↓
language frontends
  - tree-sitter Java
  - tree-sitter C++
  - parser diagnostics
  - graph fact emission
  ↓
fact normalizer
  - node facts
  - edge facts
  - occurrence facts
  - span/chunk facts
  ↓
graph store
  - SQLite
  - schema versioning
  - indexes
  - optional FTS tables
  ↓
query layer
  - symbol lookup
  - file/line anchor resolution
  - bounded neighborhoods
  - source snippet retrieval
  ↓
context planner
  - expansion
  - candidate generation
  - ranking
  - token pruning
  - deduplication
  ↓
output formatters
  - Markdown
  - JSON
  - plain text
```

## 3. Implementation language and dependencies

### 3.1 Language

The project shall be implemented in Python permanently, not as a throwaway prototype.

Target version: Python 3.11+.

### 3.2 Core dependencies

Required dependencies:

```text
tree-sitter
tree-sitter-java
tree-sitter-cpp
```

Built-in standard-library dependencies:

```text
argparse
sqlite3
json
pathlib
hashlib
dataclasses
typing
```

Optional dependencies:

```text
rich    # prettier terminal output only
pytest  # dev/test
ruff    # dev linting
mypy    # optional type checking
```

### 3.3 Dependency policy

The MVP shall avoid dependencies that require external services, project builds, compilers, IDEs, or network access at runtime.

Allowed:

- Parser libraries.
- Python packaging/test utilities.
- Local SQLite.
- Pure local output formatting helpers.

Avoid initially:

- ORM frameworks.
- Remote embedding services.
- LLM SDKs.
- MCP dependencies.
- Graph databases.
- Language servers.
- Compiler wrappers.

## 4. Module plan

```text
src/codectx/
  cli.py
    Argument parsing and command dispatch.

  scanner/
    repo.py
      Repository walking, ignore rules, file classification.
    hashing.py
      Content hashing.
    language_detect.py
      Extension/path based language detection.

  source/
    spans.py
      SourceSpan and line/byte coordinate utilities.
    snippets.py
      Snippet retrieval and line-range formatting.
    tokens.py
      Approximate token estimation.

  frontends/
    base.py
      Frontend interface and graph fact dataclasses.
    java_treesitter.py
      Java extraction.
    cpp_treesitter.py
      C++ extraction.
    queries/
      Tree-sitter query files.

  graph/
    schema.sql
      SQLite schema.
    store.py
      Connection management, migrations, inserts, queries.
    models.py
      Persisted row models.
    traversal.py
      Bounded graph walks and neighborhood assembly.

  context/
    anchors.py
      Resolve symbol or file/line into graph anchors.
    planner.py
      Goal-specific expansion strategy.
    ranking.py
      Scoring and score trace generation.
    bundle.py
      Bundle model.
    formatters.py
      Markdown, JSON, text output.
```

## 5. Data model

### 5.1 Design principles

1. Store entities, spans, occurrences, and relationships separately.
2. Keep node and edge kinds language-neutral.
3. Preserve language-specific facts as JSON metadata.
4. Store unresolved references explicitly.
5. Store confidence and extractor provenance for all graph facts.
6. Use byte offsets as canonical span coordinates.
7. Use line numbers for display and output.

### 5.2 Core tables

The SQL schema lives in `src/codectx/graph/schema.sql`.

Important tables:

```text
repo
snapshot
file
node
edge
occurrence
chunk
diagnostic
index_stat
```

### 5.3 Stable identities

The graph will use SQLite integer IDs internally. Stable identities are represented separately:

```text
file.path
file.content_hash
node.symbol_key
node.qualified_name
span byte range
```

### 5.4 Symbol keys

For MVP, symbol keys can be approximate and source-derived.

Java examples:

```text
java:src/main/java/acme/PaymentService.java#PaymentService
auto/java:com.acme.PaymentService#authorize
```

C++ examples:

```text
cpp:src/payments/payment_service.cpp#PaymentService::authorize
cpp:include/acme/payment_gateway.hpp#PaymentGateway::charge
```

Symbol keys may become more precise over time, but the MVP shall not require compiler-grade symbol identity.

## 6. SQLite plan

### 6.1 Database location

Default:

```text
<repo>/.codectx/graph.sqlite
```

Users may override with:

```bash
codectx index PATH --db /some/path/graph.sqlite
```

### 6.2 Schema application

At startup:

1. Connect to SQLite.
2. Enable pragmatic settings for local indexing.
3. Apply schema if missing.
4. Check schema version.
5. Refuse incompatible schemas unless `--rebuild` is supplied.

Recommended pragmas during indexing:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
```

### 6.3 Indexing transactions

Indexing shall batch inserts inside transactions. Avoid per-row commits.

### 6.4 Optional FTS

FTS5 should be used when available for faster symbol/chunk search. The tool must degrade to SQL `LIKE` search if FTS5 is unavailable.

## 7. Repository scanning plan

### 7.1 Ignore rules

The scanner should skip:

```text
.git
.codectx
node_modules
target
build
bazel-*
out
dist
.venv
venv
__pycache__
.gradle
.idea
.vscode
```

Later tasks may add `.gitignore` parsing. The MVP can start with built-in ignore patterns.

### 7.2 Language detection

Initial extension mapping:

```text
.java      -> java
.cpp       -> cpp
.cc        -> cpp
.cxx       -> cpp
.c++       -> cpp
.hpp       -> cpp
.hh        -> cpp
.hxx       -> cpp
.h++       -> cpp
.h         -> cpp-header-or-c-header; treat as cpp for MVP
```

### 7.3 Test detection heuristics

A file is likely a test if path or name contains:

```text
/test/
/tests/
Test.java
Tests.java
_test.cpp
Test.cpp
test_
```

## 8. Frontend plan

### 8.1 Frontend interface

Each language frontend shall expose:

```python
class LanguageFrontend(Protocol):
    language: str

    def parse(self, source: bytes) -> ParsedFile: ...
    def extract(self, file_record: FileRecord, source: bytes) -> ExtractedFacts: ...
```

The frontend emits normalized facts:

```text
NodeFact
EdgeFact
OccurrenceFact
ChunkFact
DiagnosticFact
```

### 8.2 Java extraction

Initial Java extraction targets:

- Package declaration.
- Imports.
- Classes.
- Interfaces.
- Enums.
- Records.
- Methods.
- Constructors.
- Fields.
- Parameters, initially optional.
- Annotations, stored as metadata or occurrences.
- Throws clauses.
- Method invocation expressions.
- JUnit-style test hints.

### 8.3 C++ extraction

Initial C++ extraction targets:

- Includes.
- Namespaces.
- Classes.
- Structs.
- Enums.
- Functions.
- Methods.
- Constructors.
- Destructors.
- Fields.
- Macro definitions, shallowly.
- Call expressions.
- Inheritance clauses.

### 8.4 Parser diagnostics

Tree-sitter parse errors shall be recorded. A file with parser errors can still produce partial facts.

### 8.5 Unresolved references

The MVP shall not require semantic resolution. A call-like occurrence may produce:

```json
{
  "kind": "calls",
  "src_node_id": 123,
  "dst_node_id": null,
  "unresolved_dst": "gateway.charge",
  "confidence": 0.42,
  "extractor": "tree-sitter-java"
}
```

## 9. Query layer plan

### 9.1 Symbol search

Symbol search shall combine:

- Exact name match.
- Case-insensitive substring match.
- Qualified-name match.
- Optional FTS match.
- File path match.

Return candidates with enough detail to disambiguate:

```text
node id
kind
name
qualified name
file
line range
confidence
```

### 9.2 File/line anchor resolution

Given `--file PATH --line N`, resolve:

1. Smallest node span containing the line.
2. Prefer callable over type over file.
3. If no symbol node contains line, return nearest chunk/file anchor.

### 9.3 Bounded neighborhood

Neighborhood query parameters:

```text
seed node
max depth
edge kind allowlist
direction: out, in, both
limit
```

MVP edge allowlist for `explain`:

```text
contains
references
calls
imports
includes
uses_type
throws
tests
```

## 10. Context planner plan

### 10.1 Goals

Initial goals:

```text
explain
failure-modes
dependencies
call-neighborhood
```

### 10.2 Candidate generation

For a seed node:

Required candidates:

- Target definition snippet.
- Signature or declaration snippet, if separable.
- Enclosing type/namespace/file context.

High-value candidates:

- Direct callees or call-like unresolved targets.
- Fields and types referenced by target.
- Imports/includes.
- Relevant tests.
- Parser diagnostics near target file.

Optional candidates:

- Callers.
- Sibling methods/functions.
- Same-directory related files.
- External/unresolved references as notes.

### 10.3 Ranking signals

Initial local-only ranking signals:

```text
is target
is enclosing context
edge relevance by goal
graph distance
source proximity
symbol/name match
same file
test relation
diagnostic relation
confidence
token cost
redundancy
```

Suggested first scoring formula:

```text
score =
  5.0 * is_target
+ 3.0 * exact_symbol_match
+ 2.0 * edge_relevance
+ 1.5 * graph_proximity
+ 1.2 * source_proximity
+ 1.0 * lexical_match
+ 0.8 * is_enclosing_context
+ 0.7 * is_test_context
+ 0.5 * confidence
- 0.8 * token_cost_penalty
- 1.0 * redundancy_penalty
```

The formula is expected to change after validation. The important requirement is that each item can explain its score components.

### 10.4 Token budgeting

MVP token estimate:

```text
estimated_tokens = ceil(character_count / 4)
```

Budgeting behavior:

1. Always include required target context unless impossible.
2. Include highest score-per-token candidates next.
3. Deduplicate overlapping snippets.
4. Stop when budget is reached within tolerance.
5. Report omitted high-scoring candidates.

### 10.5 Bundle model

A context bundle shall include:

```text
query
anchor
index_health
items
omitted
uncertainty_notes
trace
```

## 11. Output formatter plan

### 11.1 Markdown

Markdown is the primary manual-transfer format. It should include:

- Bundle header.
- Goal and budget.
- Target symbol.
- Index health summary.
- Ranked snippets with code fences.
- Reason and confidence per item.
- Omitted items and uncertainty notes.

### 11.2 JSON

JSON is for inspection, reproducibility, and downstream tools. It should preserve structured fields.

### 11.3 Plain text

Plain text is for environments where Markdown renders poorly.

## 12. Error handling and diagnostics

### 12.1 CLI errors

Handle:

- Repo path not found.
- No index found.
- Unsupported language.
- Ambiguous symbol.
- Missing file path.
- File changed since index.
- SQLite schema mismatch.

### 12.2 Index health report

After indexing, print and persist:

```text
files scanned
files indexed
files skipped
language counts
nodes inserted
edges inserted
occurrences inserted
chunks inserted
parser errors
unresolved references
FTS availability
index duration
```

## 13. Incremental indexing plan

MVP can rebuild the full index by default.

Later incremental indexing can use:

- File content hashes.
- Snapshot IDs.
- Delete/reinsert facts for changed files.
- Preserve unchanged file facts.

Do not block MVP on incremental indexing.

## 14. Packaging plan

Initial development install:

```bash
python -m pip install -e .[dev]
```

Run:

```bash
codectx --help
```

MVP packaging can remain source-installable. Wheel distribution can come later.

## 15. Key engineering risks

| Risk | Mitigation |
| --- | --- |
| Tree-sitter extraction misses language constructs. | Keep query files inspectable and test with fixtures. |
| Heuristic references are misleading. | Preserve confidence and uncertainty labels. |
| Bundles are too large. | Budget during selection, not after. |
| Graph schema becomes language-specific. | Use generic node/edge kinds and metadata. |
| SQLite queries become slow. | Add indexes, bound traversal, avoid expression-level graph explosion. |
| Python performance is insufficient. | Batch inserts, avoid per-node commits, profile before optimizing. |
| Users distrust output. | Include file paths, lines, reasons, provenance, and health summaries. |
