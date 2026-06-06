# T097 - MVP acceptance review

ID: T097
Title: MVP acceptance review
Status: done
Depends on: T096
Requirement coverage: MVP success criteria
Milestone: M9 - Verification, validation, and MVP hardening
Priority: Not specified.
Type: Not specified.

Rationale:

Not specified.

Work:

- Review requirements checklist.
- Review V&V evidence.
- Review known limitations.
- Tag or mark MVP release candidate.

Deliverable:

- MVP acceptance checklist.

Acceptance:

- Requirements owner agrees the MVP is functional and useful.

## Suggested implementation order

Strict minimum path to first useful bundle:

```text
T001 → T002 → T003
T010 → T011 → T012 → T013
T020 → T021 → T022 → T023 → T024
T030 → T031 → T032 → T033 → T034 → T035
T039 → T040 → T042
T050 → T051 → T052 → T053 → T055
```

This yields a first useful `explain` context bundle even before call-like references and advanced ranking.

Then continue:

```text
T060 → T061 → T062 → T063 → T064
T070 → T071 → T072 → T073
T080 → T081 → T082
T089 → T090 → T091 → T092 → T093 → T094 → T095 → T096 → T097
```

## MVP completion definition

The MVP is complete when:

1. `codectx index` works on Java and C++ repositories without requiring builds.
2. `codectx context` supports file/line and symbol anchors.
3. Markdown and JSON bundles include ranked snippets, reasons, file paths, line ranges, token estimates, confidence, and uncertainty notes.
4. `explain`, `failure-modes`, `dependencies`, and `call-neighborhood` goals work heuristically.
5. The verification suite passes.
6. Manual validation shows bundles are useful for preparing LLM prompts.
