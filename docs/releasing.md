# Packaging and source exports

`public-release-files.txt` is the explicit source-export allowlist.
`MANIFEST.in` lists the same files for source distributions. When adding,
moving, or removing source files, update both; regression tests enforce parity.
Only source files belong in these lists. Exports generate fresh `SHA256SUMS`.

## Check the working tree

```bash
python scripts/check_public_release.py
python scripts/check_public_release.py --git-objects
```

The default check scans allowlisted working files. `--git-objects` scans all
local Git blobs, including unreachable versions. After staging your changes,
`--tracked` scans the staged snapshot. Findings redact credential values.

## Create a clean source export

```bash
python scripts/export_public_repo.py --output dist/Jev-Mem
python scripts/check_public_release.py --root dist/Jev-Mem --all-files
```

The output directory and ZIP must not already exist. The exporter copies only
allowlisted files and creates a checksum manifest. It excludes Git history,
credentials, downloaded datasets, and experiment artifacts. `--all-files` is
intended for this clean export; a development tree may contain ignored local
artifacts that should not be published.

## Build distributions

After installing `requirements-dev.txt`:

```bash
python -m build
```

The wheel includes the `jev_mem`, `memory`, and `utils` packages plus legacy
entry points. The source distribution also includes documentation, profiles,
examples, tests, and maintenance scripts. See [security guidance](../SECURITY.md)
before distributing either source or derived data.
