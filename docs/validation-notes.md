# MVP Validation Notes

Date: 2026-05-25

Scope:

- Validation ran against local repositories under `/mnt/d/projects`.
- Excluded `/mnt/d/projects/WSL2-Linux-Kernel`.
- Java validation repo: `/mnt/d/projects/mundane-java-di`.
- C++ validation repo: `/mnt/d/projects/cpp-helper-libs`.
- Temporary databases and rendered bundles were written under `/tmp/codectx-m9-validation`.

## Commands

```bash
/home/jack/.venvs/codectx/bin/python -m codectx.cli index /mnt/d/projects/mundane-java-di --db /tmp/codectx-m9-validation/mundane-java-di.sqlite --rebuild
/home/jack/.venvs/codectx/bin/python -m codectx.cli index /mnt/d/projects/cpp-helper-libs --db /tmp/codectx-m9-validation/cpp-helper-libs.sqlite --rebuild
/home/jack/.venvs/codectx/bin/python -m codectx.cli health --repo /mnt/d/projects/mundane-java-di --db /tmp/codectx-m9-validation/mundane-java-di.sqlite --integrity
/home/jack/.venvs/codectx/bin/python -m codectx.cli health --repo /mnt/d/projects/cpp-helper-libs --db /tmp/codectx-m9-validation/cpp-helper-libs.sqlite --integrity
```

Representative context commands used `--format markdown --budget 3500 --output /tmp/codectx-m9-validation/bundles/...`.

## Index Results

| Repo | Files | Nodes | Edges | Chunks | Diagnostics | Unresolved references | FTS5 | Integrity | DB size |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: |
| `mundane-java-di` | 57 | 475 | 2652 | 475 | 0 | 2335 | enabled | ok | 2.6 MiB |
| `cpp-helper-libs` | 397 | 2547 | 14673 | 2605 | 1634 | 14218 | enabled | ok | 16 MiB |

Both validation databases passed SQLite integrity, foreign-key checks, span-range validation, and unresolved-edge invariant validation.

No critical crash or data-integrity issue was found during validation. Usability observations are recorded here for later prioritization; no future-task files were created.

## Bundle Review

| Bundle | Goal | Result | Notes |
| --- | --- | --- | --- |
| `AppContext.resolve` | `explain` | Useful | Included the target method, enclosing type, imports, and unresolved relationship notes. Good prompt substrate for understanding resolution flow. |
| `InjectionModuleSourceGenerator.generate` | `explain` | Useful | Included target/enclosing code, imports, referenced types, and related generator tests. This was one of the strongest bundles. |
| `GeneratorCli.writeSource` | `explain` | Useful | Included target file-writing behavior, enclosing CLI error handling, imports, and honest unresolved JDK/file API calls. |
| `solve_dijkstra` | `explain` | Partially useful | Included target wrapper, namespace, and includes. It surfaced unresolved call/type relationships but did not resolve the `solve_a_star` callee. |
| `Matrix3::solve` | `explain` | Partially useful | Included the large target and namespace context, plus detailed unresolved callee/type notes. The enclosing namespace consumed most of the budget. |
| `AppContext.resolve` | `failure-modes` | Useful | Prioritized thrown exceptions, sibling failure paths, imports, and one related test. Good fit for failure-mode review. |
| `InjectionModuleSourceGenerator.quoted` | `failure-modes` | Moderately useful | Included target escaping logic and nearby generator helpers. It found goal-relevant siblings but no related test snippet. |
| `solve_a_star` | `failure-modes` | Weak | Target and namespace were included, but parser diagnostics from vendored/third-party C++ files dominated the optional context. |

## Observations

- Java indexing and context generation were stable and produced no parser diagnostics on the selected repository.
- C++ indexing completed and integrity passed, but the repo includes third-party GoogleTest/benchmark sources that generated most parser diagnostics.
- The context formatters gave useful provenance: confidence labels, extractor names, score traces, unresolved relationship notes, and parser diagnostic warnings were visible in rendered bundles.
- The `failure-modes` goal worked best when failure behavior was local to the target or neighboring methods. It was less useful when global parser diagnostics outranked local failure evidence.
- C++ call/type resolution remains mostly heuristic on larger real-world code; unresolved notes are honest, but high unresolved counts reduce bundle precision.
- The scanner/indexer handled both validation repositories without crashing and kept parse failures as diagnostics instead of aborting.

## V3 Python/MATLAB Fixture Validation

Date: 2026-06-06

Scope:

- Python fixture: `tests/fixtures/python_basic`
- MATLAB fixture: `tests/fixtures/matlab_basic`
- V3-005 originally documented Python and MATLAB. Go and Rust were completed
  later by V3-003 and V3-004 and are now documented as supported languages.

Validation commands:

```bash
make ci
make artifact-smoke
./dist/codectx.pex index tests/fixtures/python_basic --db /tmp/python.sqlite --rebuild
./dist/codectx.pex context --repo tests/fixtures/python_basic --db /tmp/python.sqlite --file src/payments/service.py --goal explain --format json
./dist/codectx.pex index tests/fixtures/matlab_basic --db /tmp/matlab.sqlite --rebuild
./dist/codectx.pex context --repo tests/fixtures/matlab_basic --db /tmp/matlab.sqlite --file src/PaymentService.m --goal explain --format json
```

Results:

- Python indexing records `.py`/`.pyi` files, classes, functions, async
  functions, methods, class fields, imports, unresolved calls, chunks, and
  parser diagnostics.
- MATLAB indexing records `.m` files, function definitions, `classdef`
  classes, methods, properties, import commands, unresolved calls, chunks, and
  parser diagnostics.
- MATLAB symbol-poor scripts emit source fallback chunks so file-only context
  does not return an empty bundle.
- The PEX artifact smoke now indexes Java, Python, and MATLAB fixtures and
  verifies file-only `context --file` commands for each.

Representative file-only context bundle results:

| Fixture | Anchor | Items | Leading context | Notes |
| --- | --- | ---: | --- | --- |
| Python | `src/payments/service.py` | 8 | `file.outline`, four `file.symbol` entries, imports, related test | Useful overview of service class, validation helper, imports, and test. Unresolved notes were limited to dynamic/runtime calls such as `ValueError` and `PaymentRequest`. |
| MATLAB | `src/PaymentService.m` | 5 | `file.outline` and four `file.symbol` entries | Useful overview of class, property, constructor, and methods. Unresolved notes honestly captured heuristic calls such as `obj.Gateway.charge`, `isempty`, `error`, and superclass `handle`. |

Known limitations:

- Python dynamic imports, monkeypatching, decorators, metaclasses, and
  runtime-dispatched calls remain heuristic.
- MATLAB scripts may rely on file/source fallback when no clear symbols exist.
- MATLAB `.mlx` files are unsupported.

## V3 Go Fixture Validation

Date: 2026-06-07

Scope:

- Go fixture: `tests/fixtures/go_basic`
- Rust was completed later in V3-004 and is validated in the following section.

Validation commands:

```bash
make ci
make artifact-smoke
./dist/codectx.pex index tests/fixtures/go_basic --db /tmp/go.sqlite --rebuild
./dist/codectx.pex context --repo tests/fixtures/go_basic --db /tmp/go.sqlite --file service.go --goal explain --format json
```

Results:

- Go indexing records `.go` files, package namespaces, imports, structs,
  interfaces, fields, functions, receiver methods, type references, unresolved
  calls, chunks, and parser diagnostics.
- Go `*_test.go` files are marked as tests and can contribute related context.
- The PEX artifact smoke indexes the Go fixture and verifies file-only
  `context --file service.go`.

Known limitations:

- Go module/package resolution, interface dispatch, and external package calls
  remain heuristic.

## V3 Rust Fixture Validation

Date: 2026-06-07

Scope:

- Rust fixture: `tests/fixtures/rust_basic`

Validation commands:

```bash
make ci
make artifact-smoke
./dist/codectx.pex index tests/fixtures/rust_basic --db /tmp/rust.sqlite --rebuild
./dist/codectx.pex context --repo tests/fixtures/rust_basic --db /tmp/rust.sqlite --file src/lib.rs --goal explain --format json
```

Results:

- Rust indexing records `.rs` files, modules, `use` items, structs, enums,
  traits, type aliases, fields/variants, free functions, impl methods, type
  references, unresolved calls, macro invocations, chunks, and parser
  diagnostics.
- Rust `*_test.rs` files and files under `tests/` are marked as tests and can
  contribute related context.
- The PEX artifact smoke indexes the Rust fixture and verifies file-only
  `context --file src/lib.rs`.

Known limitations:

- Rust macro expansion, trait resolution, generics, and module/crate resolution
  remain heuristic.
