# Real-Repo Evaluation

`codectx` includes an optional real-repository evaluation harness for checking
context bundle quality before 1.0. Normal CI does not require these repositories
or run this harness.

The default target manifest is `scripts/real_repo_eval_targets.json`. It uses the
same local repositories from the MVP validation pass:

- `/mnt/d/projects/mundane-java-di`
- `/mnt/d/projects/cpp-helper-libs`

Run the harness explicitly:

```bash
CODECTX_REAL_REPO_EVAL=1 $HOME/.venvs/codectx/bin/python scripts/real_repo_eval.py
```

If `CODECTX_REAL_REPO_EVAL` is not set to `1`, the script prints a skip message
and exits successfully. If one of the configured repositories is missing, the
script exits successfully with a clear whole-run skip message so quality scores
are only compared when the full configured evaluation set is present.

By default, output is written under `/tmp/codectx-real-repo-eval-<timestamp>`.
Pass `--output-dir PATH` to choose a location. Each run writes:

- Fresh SQLite databases under `db/`.
- Generated Markdown bundles under `bundles/`.
- A human-readable `summary.md`.
- A structured `summary.json`.

The manifest records expected usefulness labels and 1-to-5 quality scores from
the validation rubric: Java bundles are generally useful and C++ bundles are
partially useful. The original MVP review found the `solve_a_star` failure-mode
bundle was weak because vendored and unrelated parser diagnostics could dominate
optional context; the current default C++ target excludes `third_party/**`, and
failure-mode planning keeps only anchor-file or closely related parser
diagnostics as context items while preserving aggregate diagnostic warnings.

Use `summary.md` for human review and `summary.json` for comparing runs. A
repository `status` of `ok` means indexing finished, `integrity` records the
SQLite health result, and each context row reports whether bundle generation
succeeded. Expected usefulness labels preserve the qualitative MVP review notes;
quality scores use the validation rubric's 1-to-5 scale, where higher scores
mean the bundle is more useful, grounded, concise, and trustworthy for manual
LLM prompt preparation.

To update the evaluation set, edit `scripts/real_repo_eval_targets.json` and add
or remove context targets. Each target should name a stable local repository,
symbol query, goal, budget, expected usefulness, quality score, and reviewer
notes.

Repository targets may also define scan filters using the same gitwildmatch
semantics as `codectx index`: `include_patterns`, `exclude_patterns`,
`force_include_patterns`, and `use_ignore_files`. The default C++ target excludes
`third_party/**` so vendor parser diagnostics do not dominate the validation
bundles.
