# Real-Repo Performance Gates

`codectx` includes an optional real-repository performance and storage harness
for 1.0 readiness. Normal CI does not require local validation repositories and
does not run this harness by default.

Run the harness explicitly:

```bash
CODECTX_REAL_REPO_PERF=1 $HOME/.venvs/codectx/bin/python scripts/real_repo_perf.py
```

If `CODECTX_REAL_REPO_PERF` is not set to `1`, the script prints a skip message
and exits successfully. If configured repositories are missing, the script
records those targets as skipped while continuing to run available targets.

By default, output is written under `/tmp/codectx-real-repo-perf-<timestamp>`.
Pass `--output-dir PATH` to choose a location. Each run writes:

- Fresh SQLite databases under `db/`.
- A human-readable `summary.md`.
- A structured `summary.json`.

The manifest at `scripts/real_repo_perf_targets.json` records representative
Java and C++ scenarios, scan filters, and conservative thresholds for:

- Full rebuild index time.
- No-change index time against the same database.
- One-file-change index time against a temporary copied repository.
- Integrity check time.
- Symbol search time.
- Combined search time.
- Context generation time.
- SQLite database size relative to indexed supported source bytes after the
  target's scan filters are applied.

The harness copies each configured repository into the output directory before
indexing so one-file-change measurements never modify the source validation
repositories.

Threshold failures are reported in normal mode but do not fail the process. To
turn the harness into a gate, pass `--enforce` or set
`CODECTX_REAL_REPO_PERF_ENFORCE=1`.

Update thresholds only after reviewing repeated local runs and the corresponding
real-repo evaluation bundles. Thresholds should include enough variance for
local-machine differences and should catch large regressions, not tiny timing
noise.
