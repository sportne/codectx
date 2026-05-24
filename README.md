# codectx

`codectx` is a standalone Python CLI for building a source-grounded code graph from a local repository and emitting ranked context bundles that a human can manually transfer into an LLM.

The project is intentionally **not** an LLM integration, MCP server, IDE plugin, compiler, static-analysis framework, or call-graph tool. It is a bridge capability: it helps users gather the right code context from a repository and package it clearly.

## Project definition

> A local, Python-based code-context packaging tool that indexes Java and C++ repositories into a SQLite-backed graph and emits provenance-aware Markdown/JSON context bundles for manual LLM use.

## MVP objective

The MVP should answer this question well:

> Given a file/line or symbol name, what source-grounded context should a human paste into an LLM to understand or ask about this code?

Initial target commands:

```bash
codectx index /path/to/repo
codectx search "PaymentService authorize"
codectx symbols "PaymentService"
codectx context --file src/main/java/acme/PaymentService.java --line 87 --goal explain --budget 8000 --format markdown
codectx context --symbol PaymentService.authorize --goal failure-modes --budget 8000 --format json
codectx inspect-node 123
codectx inspect-edge 456
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

## Development status

This repository is an initial planning and skeleton repository. The documentation defines the MVP and the ordered task decomposition needed to implement it.

## Design principles

1. **Graph-first:** the durable artifact is a queryable source graph, not ASTs or parser outputs.
2. **Source-grounded:** every useful graph fact should point back to files, spans, snippets, and provenance.
3. **Polyglot-first:** Java and C++ are first-class, but the core graph avoids language-specific assumptions.
4. **Local-first:** no service dependencies are required.
5. **Manual-transfer friendly:** Markdown and plain text are first-class outputs, not afterthoughts.
6. **Honest uncertainty:** heuristic references and unresolved calls are useful if labeled clearly.
7. **Ranking is central:** the project succeeds by selecting the right context under a token budget.
