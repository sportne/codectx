# Incremental Indexing Decision For 1.0

## Decision

`codectx` will include minimal incremental indexing before 1.0.

The implementation is a per-file extraction cache, not row-level graph mutation.
Each index that changes repository content still writes a fresh immutable
snapshot. Unchanged source files can reuse cached raw extraction facts, changed
files are re-extracted, and project-wide reference resolution is recomputed for
the new snapshot.

## Rationale

Small real-repo validation targets showed full rebuilds under a few seconds, but
Apache Commons Math changed the tradeoff. A local shallow checkout with 1,087
Java files took about 125.5 seconds for a full rebuild while health, symbol
search, text search, and context generation stayed under one second.

That makes repeated full extraction too expensive for larger local workflows,
but in-place mutation would add too much compatibility and correctness surface
before 1.0. A raw extraction cache addresses the measured bottleneck while
preserving the rebuildable SQLite-cache model.

## 1.0 Contract Impact

- `codectx index` may reuse cached extraction facts when `--rebuild` is not set.
- `codectx index --rebuild` remains the guaranteed clean indexing path.
- SQLite remains a local cache/artifact, not a public compatibility contract.
- Cache statistics are observability fields, not stable JSON bundle fields.
- Future releases may change cache format or require rebuilding the database.

## Future Triggers

Consider deeper incremental indexing after 1.0 only if:

- one-file-change indexing remains too slow on multi-thousand-file repositories;
- DB size or snapshot accumulation becomes a practical problem;
- users need persistent row identity across snapshots;
- real-repo performance gates show extraction caching is not enough.
