# codectx

`codectx` is a standalone Python CLI for building a source-grounded code graph from a local repository and emitting ranked context bundles that a human can manually transfer into an LLM.

The project is intentionally **not** an LLM integration, MCP server, IDE plugin, compiler, static-analysis framework, or call-graph tool. It is a bridge capability: it helps users gather the right code context from a repository and package it clearly.

## Project definition

> A local, Python-based code-context packaging tool that indexes Java and C++ repositories into a SQLite-backed graph and emits provenance-aware Markdown, JSON, and plain-text context bundles for manual LLM use.

## MVP objective

The MVP should answer this question well:

> Given a file/line or symbol name, what source-grounded context should a human paste into an LLM to understand or ask about this code?

Supported MVP commands:

```bash
codectx index /path/to/repo [--db /path/to/graph.sqlite] [--rebuild]
codectx health --repo /path/to/repo [--db /path/to/graph.sqlite] [--integrity]
codectx symbols "PaymentService" --repo /path/to/repo
codectx search "PaymentService authorize" --repo /path/to/repo
codectx context --repo /path/to/repo --symbol PaymentService.authorize --goal explain --format markdown
codectx context --repo /path/to/repo --file src/main/java/acme/PaymentService.java --line 87 --goal failure-modes --format json
codectx neighborhood --repo /path/to/repo --symbol PaymentService.authorize --depth 1 --direction out
codectx inspect-node 123 --repo /path/to/repo
codectx inspect-edge 456 --repo /path/to/repo
```

## MVP scope

Included:

- Local-only operation.
- Python implementation.
- SQLite-backed graph store.
- Tree-sitter based extraction for Java and C++.
- Source file indexing, hashing, line offsets, and snippet extraction.
- Generic polyglot graph model: files, symbols, spans, occurrences, edges, chunks.
- Context bundle generation with ranking, token budgeting, provenance, and uncertainty notes.
- Markdown, JSON, and plain-text output.

Excluded from MVP:

- MCP.
- Direct LLM service integration.
- Remote services.
- Cloud indexing.
- IDE integration.
- Compiler-perfect Java/C++ analysis.
- Required Maven/Gradle/CMake/Bazel integration.
- Neo4j or external graph databases.
- Embeddings as a core dependency.

## Quickstart

Create the development environment and install the CLI:

```bash
make setup-venv
make install-dev
```

Index one of the checked-in fixtures:

```bash
codectx index tests/fixtures/java_basic --db /tmp/codectx-java-basic.sqlite --rebuild
codectx health --repo tests/fixtures/java_basic --db /tmp/codectx-java-basic.sqlite --integrity
```

Find a symbol and generate a context bundle:

```bash
codectx symbols PaymentService --repo tests/fixtures/java_basic --db /tmp/codectx-java-basic.sqlite
codectx context \
  --repo tests/fixtures/java_basic \
  --db /tmp/codectx-java-basic.sqlite \
  --symbol PaymentService.authorize \
  --goal explain \
  --budget 4000 \
  --format markdown
```

Generate JSON or plain text instead:

```bash
codectx context --repo tests/fixtures/java_basic --db /tmp/codectx-java-basic.sqlite --symbol PaymentService.authorize --goal failure-modes --format json
codectx context --repo tests/fixtures/java_basic --db /tmp/codectx-java-basic.sqlite --file src/main/java/acme/PaymentService.java --line 10 --goal dependencies --format text
```

Write output to a file when the parent directory already exists:

```bash
mkdir -p /tmp/codectx-output
codectx index tests/fixtures/cpp_basic --db /tmp/codectx-cpp-basic.sqlite --rebuild
codectx context --repo tests/fixtures/cpp_basic --db /tmp/codectx-cpp-basic.sqlite --symbol PaymentService::authorize --goal call-neighborhood --output /tmp/codectx-output/context.md
```

## Command Reference

- `index PATH`: recursively scans Java and C++ source/header files, applies the SQLite schema, extracts Tree-sitter facts, persists graph rows, creates optional FTS5 tables when supported, and prints health stats. Without `--db`, the database is stored at `<repo>/.codectx/graph.sqlite`. Use `--rebuild` to remove the database and SQLite sidecars first. Use repeated `--include PATTERN`, `--exclude PATTERN`, and `--force-include PATTERN` flags to control gitwildmatch-style scan filters relative to `PATH`; use `--no-ignore-files` to ignore `.gitignore` and `.ignore` rules.
- `health --repo PATH`: reads persisted health stats for the latest snapshot. Add `--integrity` to run SQLite integrity, foreign-key, span-range, and unresolved-edge invariant checks. Integrity failures return a nonzero exit code.
- `symbols QUERY`: searches symbol names, qualified names, symbol keys, and file paths.
- `search QUERY`: combines symbol and chunk search, using FTS5 when available and deterministic SQL fallback otherwise.
- `context`: generates a ranked context bundle from either `--symbol QUERY` or `--file PATH --line N`. Supported goals are `explain`, `failure-modes`, `dependencies`, and `call-neighborhood`. Supported formats are `markdown`, `json`, and `text`.
- `neighborhood`: shows a bounded graph neighborhood from a symbol seed. Use `--depth`, `--direction out|in|both`, repeated `--edge-kind`, and `--limit` to control traversal.
- `inspect-node NODE_ID` and `inspect-edge EDGE_ID`: display persisted graph details, spans, confidence, extractor provenance, endpoints, unresolved text, and metadata.

## Indexing Behavior

The scanner walks repositories deterministically and skips built-in generated/cache directories such as `.git`, `.codectx`, `node_modules`, `target`, `build`, `bazel-*`, `out`, `dist`, `.venv`, `venv`, `__pycache__`, `.gradle`, `.idea`, and `.vscode`. It also respects root and nested `.gitignore` and `.ignore` files by default. Ignore-file rules are interpreted relative to the directory containing the ignore file.

Scan filters use gitwildmatch-style patterns relative to the indexed path. When any `--include` flag is present, only supported source files matching at least one include pattern are indexed. `--exclude` removes matching supported source files. `--force-include` includes matching supported source files even when they are skipped by built-in directories, ignore files, or explicit excludes. Unsupported file extensions remain ignored even when force-included. `--no-ignore-files` disables `.gitignore` and `.ignore` processing, but built-in generated/cache directory skips still apply unless force-included.

Supported languages are Java and C++ source/header extensions. Unsupported files are ignored. Indexing does not run Maven, Gradle, CMake, Bazel, preprocessors, compilers, or test suites. Parse failures are recorded as diagnostics and do not abort indexing.

The SQLite database stores file records, symbol nodes, edges, occurrences, snippets/chunks, diagnostics, index health stats, and optional FTS tables. The database is local and can be deleted or rebuilt at any time.

## Output Formats

Markdown and text output are intended for manual copy/paste into an LLM. JSON output is intended for scripts and regression tests. Every context bundle includes query details, anchor details, index health, ranked snippets, omitted candidates, uncertainty notes, and trace/provenance data.

## Privacy

`codectx` runs locally against local files. It does not call an LLM, upload source code, send telemetry, or require a remote service. The user decides what rendered context to copy elsewhere.

## Limitations

- Java and C++ extraction is heuristic and Tree-sitter based, not compiler-perfect semantic analysis.
- C++ templates, macros, overload resolution, includes, and build-configuration-specific code are only partially understood.
- Java symbol resolution does not perform full classpath, generics, annotation processing, or build-tool analysis.
- Call-like and reference edges are conservative heuristics; unresolved relationships are expected and rendered explicitly.
- Large enclosing scopes can consume much of a small context budget.
- Parser diagnostics from vendored or third-party C++ code can affect failure-mode bundles until ignored-path tuning is expanded.
- `context` bundles are prompt-preparation aids, not correctness proofs.

## Repository layout

```text
.
├── README.md
├── pyproject.toml
├── docs/
│   ├── 01-requirements.md
│   ├── 02-engineering-plan.md
│   ├── 03-verification-validation-plan.md
│   ├── 04-task-decomposition.md
│   └── examples/
├── src/codectx/
│   ├── cli.py
│   ├── scanner/
│   ├── frontends/
│   ├── graph/
│   ├── context/
│   └── source/
├── tasks/
└── tests/
```

## Documentation

Start here:

1. [`docs/01-requirements.md`](docs/01-requirements.md)
2. [`docs/02-engineering-plan.md`](docs/02-engineering-plan.md)
3. [`docs/03-verification-validation-plan.md`](docs/03-verification-validation-plan.md)
4. [`docs/04-task-decomposition.md`](docs/04-task-decomposition.md)

## Single-file artifact

For offline deployment, build one runnable PEX artifact that contains `codectx`
and its Python dependencies:

```bash
make setup-venv install-dev
make artifact-smoke
```

The artifact is written to `dist/codectx.pex`. By default it targets amd64
Linux and Windows for CPython 3.11 and 3.12. Copy that file plus a compatible
Python interpreter into the target environment, then run:

```bash
python dist/codectx.pex --help
python dist/codectx.pex --version
```

The default target platforms can be overridden when building:

```bash
make artifact ARTIFACT_PLATFORMS="--platform manylinux2014_x86_64-cp-312-cp312"
```

Tagged release publishing, release-smoke verification tags, and recovery steps
are documented in [`docs/release-automation.md`](docs/release-automation.md).

## Runtime Compatibility

`codectx` supports Python 3.11 and 3.12 for 1.0 readiness. Runtime dependency
ranges for `pathspec`, `tree-sitter`, `tree-sitter-java`, and
`tree-sitter-cpp` are bounded in `pyproject.toml` and documented in
[`docs/dependency-compatibility.md`](docs/dependency-compatibility.md).

## Development Status

The MVP CLI is implemented for local Java and C++ indexing, graph inspection, search, neighborhoods, and context bundle generation. See [`docs/validation-notes.md`](docs/validation-notes.md) for the latest local validation pass.

## Design principles

1. **Graph-first:** the durable artifact is a queryable source graph, not ASTs or parser outputs.
2. **Source-grounded:** every useful graph fact should point back to files, spans, snippets, and provenance.
3. **Polyglot-first:** Java and C++ are first-class, but the core graph avoids language-specific assumptions.
4. **Local-first:** no service dependencies are required.
5. **Manual-transfer friendly:** Markdown and plain text are first-class outputs, not afterthoughts.
6. **Honest uncertainty:** heuristic references and unresolved calls are useful if labeled clearly.
7. **Ranking is central:** the project succeeds by selecting the right context under a token budget.
