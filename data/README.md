# External datasets

Datasets are deliberately excluded from this repository and its release archive.
Download them from their original distributors and follow their licenses and usage terms:

- [LoCoMo](https://github.com/snap-research/locomo): place `locomo10.json` at
  `data/locomo10.json`, or supply another path with `--dataset`.
- [LongMemEval](https://github.com/xiaowu0162/LongMemEval): follow the upstream
  download instructions and place the cleaned JSON at `data/longmemeval_s_cleaned.json`.
  Run `python -m jev_mem.benchmarks.longmemeval --dataset data/longmemeval_s_cleaned.json
  --jev-config config/jev_mem.json --max-questions 5` for Jev-Mem, or omit the
  Jev configuration for the baseline. Each question contains its own haystack.

LoCoMo sample arguments are zero-based list positions. The loader expects a JSON
list of samples with `conversation` and `qa` fields. See the original fictional
example in `examples/locomo_synthetic.json` for the format.

Keep downloaded data and derived outputs local. A public source repository does
not grant redistribution rights to third-party datasets.
