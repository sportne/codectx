# Release Automation

Tagged releases are published by `.github/workflows/release.yml`.

## Production Releases

Push a semantic version tag to publish a production release:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The workflow validates that the tag version matches both `pyproject.toml` and
`src/codectx/__init__.py`. It then runs `make release-ci`, builds the source
distribution, wheel, and a versioned PEX, smoke-tests the installed source and
wheel artifacts in isolated virtual environments, uploads the artifacts as
workflow artifacts, and creates or updates the matching GitHub Release.

Production tags must use this shape:

```text
vMAJOR.MINOR.PATCH
```

## Release-Smoke Tags

Use release-smoke tags to verify the publishing path without declaring a
production release:

```bash
git tag release-smoke/v0.1.0-smoke-202605300915
git push origin release-smoke/v0.1.0-smoke-202605300915
```

Smoke tags must use this shape:

```text
release-smoke/vMAJOR.MINOR.PATCH-smoke-YYYYMMDDHHMM
```

The base version must still match the package and module version. Smoke runs
publish a prerelease GitHub Release whose title and notes clearly mark it as a
release-smoke verification artifact. The PEX asset uses the smoke-qualified
version, while the wheel and source distribution retain the package version
because those filenames are generated from `pyproject.toml`.

Smoke tags and prereleases are verification artifacts. They may be deleted
after review, but they should not be reused for unrelated commits.

## Manual Dispatch

The release workflow can also be run manually from GitHub Actions. Provide the
existing tag name in the `tag` input. Manual dispatch is useful when a tag was
pushed but a transient infrastructure failure prevented artifact publication.

## Recovery

If the GitHub Release already exists, the workflow uploads the PEX, wheel, and
source distribution again with `--clobber`. To recover a failed release:

1. Inspect the failed Actions logs and confirm the tag points at the intended
   commit.
2. Fix repository-side workflow or build problems on `main` if needed.
3. Re-run the workflow manually for the existing tag after the fix is present
   at that tag, or create a new tag when the release commit must change.
4. Confirm the GitHub Release contains the versioned PEX, wheel, and source
   distribution.

Do not move a production tag after artifacts have been consumed. Prefer a new
patch version when release contents need to change.
