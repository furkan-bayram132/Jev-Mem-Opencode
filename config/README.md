# Experiment profiles

- `jev_mem.json`: the default live profile used in README examples.
- `jev_mem_openrouter.json`: the default profile retargeted at OpenRouter's
  Decisions API, which publishes Jev as `~typesafe/jev-latest` and reads
  `OPENROUTER_API_KEY`. Retrieval and write settings are unchanged, so results
  are comparable with `jev_mem.json`.
- `jev_mem_accuracy.json`: an alternate experimental profile with different
  anchor counts, evidence limits, graph activation, and stopping thresholds.
  Its name does not establish an accuracy advantage or identify a paper run.

A profile's `jev_model`, `jev_base_url`, and `jev_api_key_env` take precedence
over the matching `TYPESAFE_*` environment variables, which only supply defaults.

Pass a profile with `--jev-config PATH`. Validation and defaults are defined in
[`JevMemConfig`](../memory/jev_mem_config.py). Record the full profile with each
experiment. Credentials belong in `.env`, not configuration JSON files.
