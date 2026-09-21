# Evaluation

Download benchmark data using the [data guide](../data/README.md). Run these
commands from the repository root with live providers configured in `.env`.

```bash
python -m jev_mem.benchmarks.locomo \
  --dataset data/locomo10.json --sample 0 --max-questions 10 \
  --jev-config config/jev_mem.json --model gpt-4o-mini \
  --category-to-test 1,2,3,4 --best-of-n 1

python -m jev_mem.benchmarks.longmemeval \
  --dataset data/longmemeval_s_cleaned.json --max-questions 5 \
  --jev-config config/jev_mem.json --model gpt-4o-mini
```

These are smoke runs, not commands that reproduce the complete paper tables.
For an entirely offline demonstration, use `python -m jev_mem.demo`.
Benchmark `--jev-mock` replaces only the Jev controller; answer generation and
evaluation still use live providers.

Optional NLTK and sentence-transformer scoring resources are initialized when
their metrics are requested, and may download data or model weights then.
Importing scoring utilities or viewing CLI help does not initialize those resources.

## Scoring and subsets

LoCoMo sample positions are zero-based. The question cap applies per sample
after category filtering, without truncating the ingested conversation. Use
`--best-of-n 1` for single-answer evaluation; the inherited default of 3 uses
reference-aware selection. Category 5 is adversarial and needs separate analysis.
The README's paper results include that category.

LongMemEval constructs memory separately for each question's history. Its
existing runner reports a lenient score, not the official benchmark metric.
Category IDs differ from LoCoMo; inspect each command's `--help` output.

## Comparisons and timing

Use the same dataset subset, answer model, embeddings, and scoring settings for
comparisons. Record the Git commit, full configuration, provider models,
selection settings, cache state, and any fallback events. Tune on development
data, then evaluate on held-out data.

Jev runs record construction, save/load, retrieval, and query timings. The
construction timer excludes model initialization, disk saving, and question
answering; cached runs skip construction. Query timing excludes construction
and judging. Match timing boundaries before comparing runs with paper results.

Omit all Jev options for the MAGMA baseline. With Jev enabled, add
`--no-jev-write` or `--no-jev-read` for controller ablations. Matching benchmark
runs reuse cached graphs; `--rebuild` reconstructs them. A single LoCoMo sample
can use `--reuse-memory PATH` for retrieval tuning when construction settings
match. Keep separate cache directories for independent experiments.
