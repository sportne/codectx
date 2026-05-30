# Dependency Compatibility

`codectx` 1.0 supports Python 3.11 and 3.12 in CI. Runtime parser dependencies
are intentionally bounded so grammar and parser APIs do not drift underneath a
stable release.

## Supported Runtime Matrix

| Dependency | Supported range | CI smoke |
| --- | --- | --- |
| Python | `>=3.11` | GitHub Actions runs Python 3.11 and 3.12. |
| `pathspec` | `>=0.12,<1` | Scanner filter tests cover gitwildmatch behavior. |
| `tree-sitter` | `>=0.25,<0.26` | Runtime compatibility test initializes parsers. |
| `tree-sitter-java` | `>=0.23,<0.24` | Runtime compatibility test parses minimal Java. |
| `tree-sitter-cpp` | `>=0.23,<0.24` | Runtime compatibility test parses minimal C++. |

## Upgrade Checklist

Before widening a runtime dependency range:

1. Update `pyproject.toml`.
2. Run `make install-dev` in a fresh virtual environment.
3. Run `make ci` on Python 3.11 and 3.12.
4. Run the real-repo evaluation harness when the local validation repositories
   are available.
5. Review generated bundles for parser diagnostic, symbol extraction, and
   context ranking changes.
6. Record any behavior changes in release notes or readiness docs.
