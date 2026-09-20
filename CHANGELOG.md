# Changelog

## 0.1.0 — Unreleased

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
- Rename the research prototype to Jev-Mem; retain legacy Python and CLI aliases.
- Add typed Noul/Choice decisions for memory construction and retrieval.
- Preserve all observations by default; make admission filtering optional.
- Bound graph traversal by graph, depth, node, edge, request, and latency budgets.
- Support configuration-aware LoCoMo caches, explicit reuse, and reconstruction.
- Include an offline demo, synthetic examples, algorithm draft, and overview figure.
- Prepare public distribution with credential checks, CI, and contributor guidance.

This is a research prototype. No benchmark superiority or probability-calibration
claim accompanies this release.
