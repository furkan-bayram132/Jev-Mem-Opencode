# Security and data handling

Jev-Mem is a research prototype. Only load graphs, vector indexes, and serialized
files from trusted sources; some persistence backends use Python pickle.

Keep credentials in your local `.env` or environment. `.env.example` must contain
blank values and placeholders only. Never put keys in source, issues, screenshots,
logs, or pull requests. If a credential is exposed, revoke or rotate it at its
provider; deleting it from a file or Git history does not revoke it.

Live Jev decisions send observations or retrieved context to TypeSafe. Answer
generation and judging send context to the configured OpenAI/Azure endpoint.
An OpenAI embedding backend also sends text to that endpoint. Review provider
terms and use data you are permitted to process. Graphs, vectors, benchmark
outputs, and caches can retain conversation content. Keep them private even
when decision logs omit raw observations.

## Reporting a vulnerability

Use the repository's private vulnerability reporting feature if the maintainer
has enabled it (Security → Report a vulnerability). If it is unavailable, open
an issue asking for a private contact channel, without disclosing exploit
details, credentials, or personal data. There is no guaranteed response SLA.

Only the current development branch is maintained; there is no separate
supported-release schedule yet.

## Before publication

Run `python scripts/check_public_release.py --tracked` in the public checkout.
The check looks for common credential formats, sensitive filenames, local paths,
and private artifacts; it is a guardrail, not proof that arbitrary content is
safe. Review the staged diff yourself. Enable GitHub secret scanning, push
protection, private vulnerability reporting, and branch protection where
available. Do not force-add ignored local files.

For a workspace containing private experiments, use the allowlisted export
described in [the release guide](docs/releasing.md). Its fresh repository has no
earlier local history. If adding this code to an existing repository, audit that
repository's history separately.
