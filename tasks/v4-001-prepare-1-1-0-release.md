# V4-001 - Prepare 1.1.0 release candidate with manual QA

ID: V4-001

Title: Prepare 1.1.0 release candidate with manual QA

Status: in_progress

Depends on:

- V2-005
- V3-005

Requirement coverage:

- Release automation and artifact guarantees.
- File-only context anchor usability.
- Expanded language support validation.

Work:

- Bump package and module metadata to `1.1.0`.
- Update version-coupled release validation and CLI tests.
- Run local automated release gates.
- Run a manual QA pass over supported fixture languages without committing QA scripts or generated outputs.
- Monitor GitHub CI and release-smoke workflow results.
- Create the `v1.1.0` production tag after local gates, manual QA, main CI, and release-smoke pass.

Deliverable:

- A verified `1.1.0` release candidate and production release tag.

Acceptance:

- `make ci` passes.
- `make release-ci` passes.
- Manual QA covers editable CLI, built PEX, indexing, health, context, file/line anchors, symbol workflows, inspection, and actionable failure cases.
- Latest GitHub CI for the release commit passes on supported Python versions.
- `release-smoke/v1.1.0-smoke-YYYYMMDDHHMM` publishes the expected artifacts.
- `v1.1.0` production tag is created only after the preceding checks pass.
