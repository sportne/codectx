# Project Notes

This page keeps project-level notes that are useful for maintainers but too
verbose for the top-level README.

## Project Definition

`codectx` is a local, Python-based code-context packaging tool that indexes
Java and C++ repositories into a SQLite-backed graph and emits provenance-aware
Markdown, JSON, and plain-text context bundles for manual LLM use.

It is intentionally not an LLM integration, MCP server, IDE plugin, compiler,
static-analysis framework, or call-graph tool. It is a bridge capability: it
helps users gather the right code context from a repository and package it
clearly.

## 1.0 Readiness Objective

The 1.0-ready CLI should answer this question well:

> Given a file, file/line, or symbol name, what source-grounded context should a
> human paste into an LLM to understand or ask about this code?

## Scope

Included:

- local-only operation
- Python implementation
- SQLite-backed graph store
- Tree-sitter based extraction for Java and C++
- source file indexing, hashing, line offsets, and snippet extraction
- generic polyglot graph model for files, symbols, spans, occurrences, edges,
  and chunks
- context bundle generation with ranking, token budgeting, provenance, and
  uncertainty notes
- Markdown, JSON, and plain-text output

Excluded from 1.0:

- MCP
- direct LLM service integration
- remote services
- cloud indexing
- IDE integration
- compiler-perfect Java/C++ analysis
- required Maven/Gradle/CMake/Bazel integration
- Neo4j or external graph databases
- embeddings as a core dependency

## Design Principles

1. **Graph-first:** the durable artifact is a queryable source graph, not ASTs
   or parser outputs.
2. **Source-grounded:** every useful graph fact should point back to files,
   spans, snippets, and provenance.
3. **Polyglot-first:** Java and C++ are first-class, but the core graph avoids
   language-specific assumptions.
4. **Local-first:** no service dependencies are required.
5. **Manual-transfer friendly:** Markdown and plain text are first-class
   outputs, not afterthoughts.
6. **Honest uncertainty:** heuristic references and unresolved calls are useful
   if labeled clearly.
7. **Ranking is central:** the project succeeds by selecting the right context
   under a token budget.

## Runtime Compatibility

`codectx` supports Python 3.11 and 3.12 for 1.0 readiness. Runtime dependency
ranges for `pathspec`, `tree-sitter`, `tree-sitter-java`, and
`tree-sitter-cpp` are bounded in `pyproject.toml` and documented in
[`dependency-compatibility.md`](dependency-compatibility.md).

## Related Docs

- [`06-1.0-release-criteria.md`](06-1.0-release-criteria.md)
- [`08-1.0-readiness-audit.md`](08-1.0-readiness-audit.md)
- [`dependency-compatibility.md`](dependency-compatibility.md)
- [`release-automation.md`](release-automation.md)
- [`validation-notes.md`](validation-notes.md)
