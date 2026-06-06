# codectx

`codectx` is a local CLI for turning Java and C++ repositories into
source-grounded context bundles for LLM prompts.

It indexes a repository into a SQLite code graph, then emits Markdown, JSON, or
plain-text snippets around a file, a file/line anchor, or a symbol. It does not
call an LLM or upload source code.

## Quickstart

Get the PEX artifact, then verify it runs:

```bash
python dist/codectx.pex --version
```

Index a repository once:

```bash
python dist/codectx.pex index /path/to/repo
```

Then ask for context around a file:

```bash
python dist/codectx.pex context \
  --repo /path/to/repo \
  --file src/main/java/acme/PaymentService.java \
  --goal explain \
  --format markdown
```

Add `--line` when you want to narrow the anchor to a specific line:

```bash
python dist/codectx.pex context \
  --repo /path/to/repo \
  --file src/main/java/acme/PaymentService.java \
  --line 87
```

Write the bundle to a file:

```bash
python dist/codectx.pex context \
  --repo /path/to/repo \
  --file src/main/java/acme/PaymentService.java \
  --output /tmp/payment-service-context.md
```

Choose how much context to include with `--budget`:

```bash
python dist/codectx.pex context \
  --repo /path/to/repo \
  --file src/main/java/acme/PaymentService.java \
  --budget 12000
```

If you prefer to start from a symbol:

```bash
python dist/codectx.pex symbols PaymentService --repo /path/to/repo
python dist/codectx.pex context --repo /path/to/repo --symbol PaymentService.authorize
```

## Commands

```bash
codectx index PATH [--db PATH] [--rebuild]
codectx health --repo PATH [--db PATH] [--integrity]
codectx search QUERY --repo PATH [--db PATH]
codectx symbols QUERY --repo PATH [--db PATH]
codectx context --repo PATH (--symbol QUERY | --file PATH [--line N]) [options]
codectx neighborhood --repo PATH --symbol QUERY [options]
codectx inspect-node NODE_ID --repo PATH [--db PATH]
codectx inspect-edge EDGE_ID --repo PATH [--db PATH]
```

Common `context` options:

```bash
--goal explain|failure-modes|dependencies|call-neighborhood
--budget N
--format markdown|json|text
--output PATH
```

## What Gets Indexed

`codectx` currently supports Java and C++ source/header files. It respects
`.gitignore` and `.ignore` files by default, skips common generated/cache
directories, and stores its default database at:

```text
<repo>/.codectx/graph.sqlite
```

Use scan filters when needed:

```bash
python dist/codectx.pex index /path/to/repo \
  --include "src/**" \
  --exclude "third_party/**" \
  --rebuild
```

## Output

Context bundles include:

- the requested anchor
- index health metadata
- ranked source snippets with file and line provenance
- omitted candidates
- uncertainty notes for heuristic or ambiguous matches

Markdown and text are intended for copy/paste into an LLM. JSON is intended for
scripts and regression tests.

## Caveats

- File-only context uses symbols in that file as context origins. Symbol-poor
  files may fall back to file/source context.
- Use `--line N` with `--file PATH` when you need context around one precise
  line.
- Index before generating context, or pass `--db` to use a specific index.
- Java and C++ extraction is Tree-sitter based and heuristic, not
  compiler-perfect.
- C++ macros/templates and Java classpath-dependent behavior may be incomplete.
- The SQLite database is a local cache and can be deleted and rebuilt.

## Development

Run the test suite:

```bash
make test
```

Build a single-file PEX artifact:

```bash
make setup-venv install-dev
make artifact-smoke
```

The artifact is written to `dist/codectx.pex`. A local editable install also
provides the shorter `codectx` command for development.

Further release, compatibility, validation, and maintainer notes live in
[`docs/`](docs/), especially [`docs/project-notes.md`](docs/project-notes.md).
