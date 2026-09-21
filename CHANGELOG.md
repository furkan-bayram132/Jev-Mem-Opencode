# Changelog

## 0.1.0 — Unreleased

- Include both architecture figures in source releases and defer optional scoring
  resource downloads until metric evaluation. Mark cache hashes as non-security uses.
- Standardize the project title as "Jev-Mem: System-One Controlled Agentic
  Memory". Remove earlier project-name aliases from scripts, imports, constructor
  arguments, and CLI flags; migrate historical cache metadata on read.
- Group application code, dataset loaders, and benchmark runners under
  `jev_mem`, retaining legacy commands and imports. Add module entry points,
  developer guides, local-artifact ignore rules, and consistent release manifests.
- Remove the unused duplicate dataset loader and stale source-tree checksums;
  the release exporter generates fresh checksums for each export.
- Integrate Jev-Mem construction and retrieval with LongMemEval, including
  content-aware caches, message-level progress, and timing records.
- Standardize new controller traces as `jev-mem`, retaining cache compatibility.
- Remove obsolete release profiles and duplicate exports; scan complete public
  trees and local Git objects, including Hugging Face credentials.
- Preserve temporal precision when resolving relative dates, keep adjacent
  dialogue evidence together, and weight rare event terms in temporal retrieval.
  Existing MAGMA-temporal graphs support the new reader without reconstruction.
- Print and record per-sample graph construction, saving, and cache-loading times.
- Restore MAGMA sequence/proximity rules for temporal writes; keep other Jev
  decisions and retrieval intact. Earlier Jev-temporal caches require rebuilding.
- Use Jev-Mem names for the public API, controller configuration, and CLI.
- Add typed Noul/Choice decisions for memory construction and retrieval.
- Preserve all observations by default; make admission filtering optional.
- Bound graph traversal by graph, depth, node, edge, request, and latency budgets.
- Support configuration-aware LoCoMo caches, explicit reuse, and reconstruction.
- Include an offline demo, synthetic examples, developer guides, and architecture figures.
- Prepare public distribution with credential checks, packaging, and contributor guidance.

This research software accompanies the Jev-Mem paper. See the README for the
current reported benchmark results and their evaluation scope.
