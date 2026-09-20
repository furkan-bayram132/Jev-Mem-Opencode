# Preparing a public Jev-Mem repository

Keep private working files separate from the public checkout. The exporter
copies only paths listed in `public-release-files.txt`, scans their contents,
and writes a SHA-256 manifest plus a ZIP archive. It refuses existing output
paths, symlinks, missing files, credentials, and known private artifact paths.
It never copies Git history or `.env`.

From the working project:

```bash
python scripts/check_public_release.py
python scripts/export_public_repo.py --output dist/Jev-Mem
```

Use a fresh output path for each export; the tool does not overwrite an earlier
release. The result is `dist/Jev-Mem/` and `dist/Jev-Mem.zip`.
Review that directory before creating a remote. Do not publish the private
working directory as an archive.

Inside the exported directory, initialize a new repository if needed:

```bash
git init -b main
git add .
python scripts/check_public_release.py --tracked
git diff --cached --stat
```

After review, make the initial commit using your own Git identity. Create an
empty GitHub repository named `Jev-Mem`, then use its actual URL:

```bash
git commit -m "Prepare Jev-Mem public source"
git remote add origin https://github.com/YOUR-OWNER/Jev-Mem.git
git push -u origin main
```

`YOUR-OWNER` is a placeholder. No remote or author identity is supplied by this
project. Add the actual authors, repository URL, and released commit/version to
`CITATION.bib` and package metadata before tagging a release. If an archive or
DOI is created later, cite the real identifier.

Enable the repository protections described in [SECURITY.md](../SECURITY.md),
run CI, and confirm the repository visibility. GitHub-specific settings cannot
be configured by files alone. Rotate any previously exposed credential at its
provider; a clean export does not revoke it.

The allowlist is intentional: when adding a public file, add its path there and
run the checker. CI additionally scans every tracked file, so manually adding
a private file outside the allowlist is still checked. The checker scans the
index in `--tracked` mode, not unstaged working changes, and does not audit prior
commits. Review arbitrary conversation content manually: no pattern scanner
can prove a file contains no private information.
