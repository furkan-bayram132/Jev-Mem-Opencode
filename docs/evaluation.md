# Evaluation and reproducibility

The public repository provides evaluation code, not a validated performance
claim. Unit tests and the offline demo establish software behavior with mocks;
they do not measure Jev's live answer quality or probability calibration.

## A reproducible comparison

1. Record the source commit, dataset source/version, Python and package versions,
   provider model/deployment identifiers, and the complete configuration.
2. Choose development and held-out samples before tuning. Keep conversation
   ingestion and question/category sets identical across systems.
3. Run `--best-of-n 1` for single-answer comparisons. The inherited benchmark
   default is 3; reference-aware best-of-N selection must be reported separately
   as an oracle-assisted setting. Do not present it as ordinary inference.
4. Report each category and aggregate, with denominators. Disclose that the
   harness uses dataset question categories in retrieval/generation settings.
   Include category 5 only with an explicit adversarial evaluation protocol.
5. Report answer scores together with evidence recall, provider attempts,
   latency, fallback frequency, and construction cost. State whether embedding
   download, memory construction, generation, and judging are included in timing.
6. Keep raw data, graphs, and results private. Publish only aggregates or examples
   you are authorized to redistribute, after reviewing them for sensitive content.

Temperature settings do not guarantee provider determinism. Record repeated
runs and uncertainty where feasible. Jev outputs are model-reported scores;
threshold tuning does not establish their calibration.

## Construction and retrieval ablations

Use `--no-jev-write` and `--no-jev-read` to isolate control paths. Omit Jev flags
and configuration for the retained MAGMA baseline. Use a new cache root or
`--rebuild` after changing construction settings, prompts, or input data.

The default write path disables admission filtering. `admission_enabled=true`
is a separate experiment. Successful Jev writes avoid extraction/summarization
LLM calls, but fallback to MAGMA can introduce them. Report fallback events and
cost separately. Consolidation records decisions and links; generated summaries
require an explicitly supplied callback.

`--reuse-memory PATH` is for retrieval-only tuning on one sample. It validates
write settings and accepts legacy `sys1mem_config.json` caches. It does not
prove that a graph came from the same dataset revision or embedding model;
the experimenter must verify provenance and use the correct sample.

## Evidence recall

The harness records retrieved dialogue IDs and evidence recall after each query.
To inspect only the vector/keyword anchor stage on an existing cache:

```bash
python scripts/evaluate_anchor_recall.py --help
```

This diagnostic requires a locally available embedding model and a trusted
saved graph. It does not call Jev or generate answers. Compare evidence recall
before changing thresholds: missing ingestion, missing anchors, traversal
limits, answer formatting, and scoring can cause different failures.

The bundled profiles are experimental settings, not universally optimal values.
The filename `jev_mem_accuracy.json` denotes a historical tuning profile; it is
not a claim that it outperforms `jev_mem.json`.
