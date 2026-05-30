# Verification and Validation Plan

Historical note: this document records the MVP verification and validation plan.
It is useful project history, but the current 1.0 user contract is defined by
[`../README.md`](../README.md) and
[`06-1.0-release-criteria.md`](06-1.0-release-criteria.md).

## 1. Purpose

This plan defines how to determine whether `codectx` is built correctly and whether it is useful for its intended purpose.

- **Verification:** Are we building the system according to the requirements?
- **Validation:** Does the system produce context bundles that actually help a human prepare useful LLM prompts?

## 2. Verification strategy

Verification shall combine:

1. Unit tests.
2. Integration tests.
3. Golden fixture tests.
4. CLI acceptance tests.
5. Database integrity checks.
6. Bundle schema checks.
7. Performance smoke tests.
8. Manual index health checks.

## 3. Validation strategy

Validation shall use real or realistic Java/C++ repositories and task-oriented bundle review.

A bundle is considered useful if a reviewer agrees that it includes the main code needed to ask an LLM about the target without excessive irrelevant material.

Validation activities:

1. Run `codectx context` on known target methods/functions.
2. Review included snippets against a rubric.
3. Record missing critical context.
4. Record irrelevant or redundant context.
5. Tune ranking and candidate generation.
6. Preserve cases as regression tests where possible.

## 4. Test levels

### 4.1 Unit tests

Unit tests shall cover:

- Language detection.
- Ignore rules.
- Content hashing.
- Line/byte span conversions.
- Token estimate calculation.
- Fact dataclass serialization.
- SQLite schema application.
- Basic insert/query operations.
- Ranking score calculations.
- Bundle JSON serialization.
- Markdown escaping/fencing.

Example test names:

```text
test_language_detects_java
test_language_detects_cpp_headers
test_line_offsets_round_trip_utf8
test_schema_applies_cleanly
test_node_insert_and_lookup
test_ranking_prefers_target_definition
test_markdown_formatter_includes_file_and_lines
```

### 4.2 Frontend fixture tests

Fixture tests shall use small source files with known structures.

Java fixture coverage:

- Package declaration.
- Imports.
- Class.
- Interface.
- Enum.
- Record, if supported by grammar version.
- Constructor.
- Method.
- Field.
- Annotation.
- Throws clause.
- Method invocation.
- Nested class.
- JUnit-style test.

C++ fixture coverage:

- Include.
- Namespace.
- Class.
- Struct.
- Enum.
- Free function.
- Method.
- Constructor/destructor.
- Field.
- Macro definition.
- Function call.
- Inheritance declaration.
- Header/source pair.

Fixture tests shall verify extracted graph facts, not just parser success.

### 4.3 Integration tests

Integration tests shall run the indexer against temporary repositories and verify:

- SQLite database is created.
- File rows are inserted.
- Node rows are inserted.
- Edge rows are inserted.
- Occurrence rows are inserted.
- Chunks are created.
- Symbol search returns expected candidates.
- File/line anchor resolves to expected node.
- Context bundle includes target snippet.

### 4.4 CLI acceptance tests

CLI tests shall execute commands as a user would.

Minimum acceptance commands:

```bash
codectx --help
codectx index fixtures/java-basic
codectx health --repo fixtures/java-basic
codectx symbols PaymentService --repo fixtures/java-basic
codectx context --repo fixtures/java-basic --symbol PaymentService.authorize --goal explain --budget 4000 --format markdown
codectx context --repo fixtures/java-basic --symbol PaymentService.authorize --goal explain --budget 4000 --format json
```

The tests should assert successful exit codes and essential output substrings.

### 4.5 Database integrity tests

Database integrity checks:

```sql
PRAGMA integrity_check;
PRAGMA foreign_key_check;
```

Additional checks:

- No edge references missing node IDs unless explicitly unresolved.
- No node has invalid file/span coordinates.
- No chunk has empty text unless explicitly allowed.
- Schema version exists.
- Required indexes exist.

### 4.6 Bundle schema tests

For JSON bundles, validate required fields:

```text
query
anchor
index_health
items
items[].rank
items[].file
items[].line_range
items[].reason
items[].score
items[].confidence
items[].text
omitted
uncertainty_notes
```

For Markdown bundles, verify:

- Header exists.
- Target information exists.
- Each item has file path and line range.
- Code fences are balanced.
- Reasons are present.
- Uncertainty notes are present when low-confidence facts are included.

### 4.7 Performance smoke tests

MVP performance targets:

| Test | Target |
| --- | --- |
| Index 100 source files | < 30 seconds |
| Index 1,000 source files | < 5 minutes |
| Generate context from existing index | < 10 seconds |
| SQLite integrity check | < 30 seconds for medium fixture |

These are smoke targets, not hard product guarantees.

## 5. Validation rubric

For each generated context bundle, reviewers should score the following from 1 to 5.

| Criterion | Question |
| --- | --- |
| Target correctness | Did the bundle include the intended target symbol? |
| Source grounding | Are all snippets clearly tied to file paths and lines? |
| Relevance | Are included snippets relevant to the user goal? |
| Completeness | Is important nearby context missing? |
| Concision | Is the bundle reasonably compact under the budget? |
| Uncertainty handling | Are heuristic/unresolved facts clearly labeled? |
| Manual usability | Could a user paste this into an LLM without major editing? |
| Trustworthiness | Can the user understand why snippets were included? |

Suggested MVP validation threshold:

```text
Average score >= 4.0 on target correctness, source grounding, and manual usability.
Average score >= 3.5 on relevance, completeness, and concision.
No critical unlabeled uncertainty in reviewed bundles.
```

## 6. Goal-specific validation

### 6.1 `explain`

The bundle should include:

- Target definition/body.
- Enclosing type or namespace when applicable.
- Signature/declaration.
- Imports/includes.
- Relevant fields or helper methods.
- Likely direct callees.
- Relevant tests if discoverable.

Failure cases:

- Target body missing.
- Enclosing context missing when needed.
- Large unrelated file dumps dominate budget.
- Unresolved calls are presented as resolved.

### 6.2 `failure-modes`

The bundle should prioritize:

- Throws clauses.
- Error/exception branches.
- Validation methods.
- Null checks and guard conditions.
- Called methods with names suggesting failure behavior.
- Tests expecting errors.
- Parser diagnostics or known uncertainty.

Failure cases:

- Bundle is identical to generic explain output.
- Failure-related code is omitted while low-value siblings are included.
- Exception/diagnostic snippets lack provenance.

### 6.3 `dependencies`

The bundle should prioritize:

- Imports/includes.
- Used types.
- Direct callees.
- Fields read/written.
- Constructor-injected dependencies.
- Header/source counterpart for C++ where discoverable.

Failure cases:

- Dependencies are listed without source context.
- Important import/include context omitted.
- C++ headers and source files are not linked when obvious by path/name.

### 6.4 `call-neighborhood`

The bundle should prioritize:

- Target callable.
- Likely callees.
- Likely callers.
- Source spans for each.
- Confidence labels for heuristic calls.

Failure cases:

- Heuristic call edges are overclaimed.
- No distinction between direct and indirect relationships.
- Output exceeds budget with repetitive snippets.

## 7. Requirement-to-test traceability

| Requirement area | Verification evidence |
| --- | --- |
| Repository scanning | Unit tests, integration index tests, health report checks |
| Source spans | Unit round-trip tests, snippet extraction tests |
| Java extraction | Java fixture tests |
| C++ extraction | C++ fixture tests |
| SQLite graph | Schema tests, insert/query tests, integrity checks |
| Symbol lookup | Integration and CLI tests |
| File/line anchor | Integration and CLI tests |
| Context planning | Ranking unit tests, bundle integration tests |
| Markdown output | Formatter tests, manual validation |
| JSON output | Schema tests, regression fixtures |
| Honest uncertainty | Bundle validation and low-confidence fixture cases |

## 8. Golden repository plan

Create small golden repos under test fixtures:

```text
tests/fixtures/java_basic/
  src/main/java/acme/PaymentService.java
  src/main/java/acme/PaymentGateway.java
  src/test/java/acme/PaymentServiceTest.java

tests/fixtures/cpp_basic/
  include/acme/payment_service.hpp
  src/payment_service.cpp
  tests/payment_service_test.cpp
```

Each golden repo should include expected outputs:

```text
expected_graph.json
expected_context_explain.json
expected_context_failure_modes.json
expected_context_dependencies.json
expected_context_dependencies_source.json
```

Golden outputs should be reviewed whenever extraction or ranking changes.

## 9. Regression test policy

Any bug involving one of the following should create a regression fixture:

- Wrong target anchor.
- Missing target snippet.
- Bad span/line range.
- Misleading resolved edge.
- Broken Markdown formatting.
- Context budget ignored.
- Parser error aborts entire indexing.
- High-value context omitted by ranking.

## 10. MVP acceptance gate

Before calling the MVP functional and useful, the project should pass:

1. Unit test suite.
2. Java fixture extraction tests.
3. C++ fixture extraction tests.
4. SQLite integrity tests.
5. CLI acceptance tests.
6. JSON bundle schema tests.
7. Manual validation on at least one Java and one C++ non-trivial repository.
8. Review of at least five `explain` bundles and three `failure-modes` bundles.

## 11. Open validation questions

These were the open questions during MVP development:

1. How often do Tree-sitter-only call-like edges help versus mislead?
2. How much enclosing context should be included before it becomes wasteful?
3. Are same-file helper methods more valuable than project-wide likely callees under small budgets?
4. What token budget is the default sweet spot: 4k, 8k, or 12k?
5. How should unresolved references be represented in Markdown so users trust but understand them?
6. Which C++ header/source linking heuristics are useful without build integration?
