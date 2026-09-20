# External datasets

Datasets are deliberately excluded from this repository and its release archive.
Download them from their original distributors and follow their licenses and usage terms:

- [LoCoMo](https://github.com/snap-research/locomo): place `locomo10.json` at
  `data/locomo10.json`, or supply another path with `--dataset`.
- [LongMemEval](https://github.com/xiaowu0162/LongMemEval): follow the upstream
  download instructions, then use the separate baseline runner's `--help`.
  Jev-Mem control is currently integrated with LoCoMo, not this runner.

LoCoMo sample arguments are zero-based list positions. The loader expects a JSON
list of samples with `conversation` and `qa` fields. See the original fictional
example in `examples/locomo_synthetic.json` for the format.

Keep downloaded data and derived outputs local. A public source repository does
not grant redistribution rights to third-party datasets.
