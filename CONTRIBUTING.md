# Contributing to Jev-Mem

Bug fixes, reproducible experiments, documentation, and tests are welcome.
Discuss substantial algorithm or dependency changes in an issue first.

## Development

Use Python 3.11 or newer from a checkout:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e .
python -m pytest -q
python -m jev_mem.demo
python scripts/check_public_release.py
```

Tests and the demo use mocks and do not require API keys or model downloads.
Keep tests under `tests/`; benchmark runners live in `jev_mem/benchmarks/`.
Add focused regression coverage for changes to decisions, budgets, persistence,
SDK contracts, and compatibility. Use deterministic synthetic inputs.

See the [project layout](docs/architecture.md) before adding a new module.
Keep release and packaging manifests in sync when moving files.

## Pull requests

- Explain the problem, resulting behavior, and verification.
- Preserve the MAGMA baseline and label mock, fallback, and live results clearly.
- Record configuration, dataset version, samples, seeds where applicable, and
  generation/judging settings for experiments. Follow [evaluation guidance](docs/evaluation.md).
- Do not commit keys, `.env`, conversations, graphs, vectors, raw results, or
  private audit logs. The public examples must be original synthetic data.
- Update documentation and the changelog for user-visible changes.
- Run `python scripts/check_public_release.py --tracked` after staging changes.
  This checks the staged snapshot, including newly added files.

Contributions are submitted under the repository's MIT license. Preserve
upstream notices. Follow the [code of conduct](CODE_OF_CONDUCT.md) and report
security issues using [SECURITY.md](SECURITY.md).
