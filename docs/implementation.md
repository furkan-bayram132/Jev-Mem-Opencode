# Jev-Mem implementation

## Inspection map

This repository is modified in place. There is no second MAGMA repository or
external MAGMA dependency.

| Existing component | Jev-Mem role | Implementation |
| --- | --- | --- |
| `memory/memory_builder.py` | Explicit observation write pipeline | `build()` adds admission, typing, candidate search, relation judgment and insertion; `build_memory()` adapts LoCoMo turns |
| `memory/graph_db.py` | Canonical memory and relation storage | Existing `EventNode`, `Link`, and NetworkX multi-directed graph; missing timestamps now survive serialization |
| `memory/vector_db.py` | Candidate and anchor retrieval | Existing FAISS/NumPy search and encoders; bounded remote embedding requests |
| `memory/trg_memory.py` | MAGMA baseline and fallback | Existing extraction and graph operations retained; encoder injection allows offline tests |
| `memory/query_engine.py` | Query entry point | Optional Jev control; baseline path remains available |
| `memory/test_harness.py` | System-Two answer generation | Existing generation retained, with Jev-Mem call audit records |
| `test_fixed_memory.py` | LoCoMo experiments | Independent write/read flags, config fingerprints, separate cache/result paths |
| `test_longmemeval_chunked.py` | LongMemEval baseline | Preserved; its separate construction pipeline is not yet wired to Jev-Mem |
| `main.py` | Raw-observation build/query CLI | Repaired stale APIs; delegates benchmark mode to LoCoMo runner |
| `utils/memory_layer.py` | System-Two client | Existing OpenAI client honors `OPENAI_BASE_URL`, including Azure v1 |

New control-plane modules:

- `memory/jev_client.py`: official TypeSafe SDK adapter, Noul/Choice response
  validation, retries, batching, bounded in-memory cache, mock mode and JSONL audit.
- `memory/jev_questions.py`: all Jev prompts and explicit Noul/Choice criteria.
- `memory/jev_mem_config.py`: validated configuration with baseline defaults.
- `memory/jev_mem_policies.py`: admission/types, candidate generation, typed relation
  decisions, deterministic timestamps and graph budget allocation.
- `memory/jev_mem_retrieval.py`: graph routing, batched candidate scoring, and
  evidence-based stopping.
- `memory/openai_encoder.py`: implements the previously missing embedding adapter.

## Write path

```text
MemoryBuilder.build(raw observation)
  -> Jev independent memory type probabilities (no admission filter by default)
  -> embedding and deterministic MAGMA candidate search
  -> one Jev request containing questions for all candidate pairs
  -> one EventNode plus zero or more Links
  -> graph/vector insertion, keyword index, decision trace
  -> optional periodic consolidation decisions
```

`admission_enabled` defaults to `false`, including in `config/jev_mem.json`.
Every conversation turn is stored, including brief replies and repeated text.
The default path does not ask Jev admission questions or apply admission scores;
memory-type scores and relation decisions cannot reject a turn. Raw content,
speaker and dialogue IDs are preserved. Empty direct library inputs still raise
a validation error. Provider/storage failures follow the existing error policy.

To run the original filtering experiment, explicitly set `admission_enabled`
to `true`. That mode batches admission and typing and uses configurable weights:

```text
P(store) * max(0,
  (a * utility + b * importance + c * novelty) / (a + b + c)
  - d * redundancy)
```

`EventNode.attributes.sys1mem` records `admission_enabled` and memory-type scores;
admission scores are null when filtering is disabled. Existing
attributes carry entities, source, original text, and parent interaction ID.
`Link.properties` carries probability, confidence and subtype; link metadata
records its origin. Semantic, temporal, causal and entity edges all reference
the same canonical node. Type scores are independent, not a softmax.

When filtering is enabled, admission and typing share one request because they evaluate the same state.
Each Noul is the probability of an explicit yes/no proposition. For example,
importance asks whether a personally meaningful fact is present; its output is
not a graded measure of importance. The four memory types may all apply.

Timestamp ordering and exact entity identifiers do not call Jev. Implicit time
ordering uses Choice: `before`, `after`, `during`, `contains`, `overlaps`,
`same_time`, or `unknown`. Only the selected relation can create an ordering edge,
and `unknown` creates none. Shared episodes and ambiguous aliases use Noul. Causal decisions
are evaluated separately in each direction; semantic similarity never creates
causal edges. Comparisons are limited by `candidate_top_k`.

No extraction/summarization LLM is called for a successful Jev-Mem write.
An observation is stored after its required typing and relation decisions succeed.
Partial graph insertion rolls back the new node and its vector. If Jev fails
and `fallback_to_magma` is true, the observation takes the existing MAGMA write
path, which may use its existing LLM extraction. Fallback is explicitly logged.
Set `fallback_to_magma` to false for experiments that must fail on Jev errors.

## Retrieval path

Jev estimates all four graph needs, multi-hop need and recency importance.
The existing vector search and keyword/RRF fusion find anchors. The query does
not run MAGMA's full traversal before applying Jev budgets.

Graph budgets use exponentiated probabilities and largest-remainder integer
allocation. Inactive graphs receive zero. If the total cannot fund every
minimum, the highest-need graphs receive the available allocation.

Each round batches relevance, relation usefulness, novelty and corroboration
questions for candidate nodes. Ranking combines these decisions with cosine
similarity, relation probabilities and recency. Multi-hop need controls the
depth allowance within the configured maximum. The graph budget counts candidate
edge expansions, not just final selected nodes.

Evidence sufficiency is checked on the actual top-k evidence intended for the
answer prompt, including the anchor-only round. Missing evidence and unresolved
contradictions prevent a sufficient-evidence stop. Independent hard counters
limit nodes, examined edges, depth, graph expansions and Jev attempts, including
retries. Per-query budgets are local, so parallel benchmark queries do not share
counters. Cached decisions do not consume network attempts.

The monotonic latency deadline is checked between operations and limits remote
request timeouts. Synchronous local embedding inference and graph/index routines
are not forcibly preempted, so this is not a real-time wall-clock guarantee.
On Jev failure, bounded retrieval uses the existing deterministic intent,
embedding and graph signals and records the fallback. Budget limits remain active.

## Consolidation

`MemoryBuilder.consolidate(memory_id, summarizer=None)` compares a bounded set
of neighboring candidates in one Jev request. It uses independent Nouls for
redundancy, contradiction, obsolescence and linking, plus a Choice for the
representation: `keep_separate`, `merge`, `promote`, or `uncertain`.
Redundancy and contradiction links are idempotent. Raw observations are never
deleted. Obsolescence is recorded for inspection; this prototype does not
automatically hide or delete historical evidence.

If the selected merge/promote option meets the probability threshold and the
contradiction Noul stays below its threshold, an optional
`summarizer(list_of_source_texts) -> str` callback can invoke System Two. Its new
representation passes through the same admission/type/write pipeline and stores
source-memory provenance. Repeated summaries for the same source pair are
suppressed. Periodic consolidation currently creates decisions/links only;
summary generation is explicitly supplied by callers when needed.

## Configuration and providers

`config/jev_mem.json` enables the prototype. All defaults and validation live
in `JevMemConfig`. Configuration files reject unknown keys. Environment values
`TYPESAFE_DEFAULT_MODEL` and `TYPESAFE_BASE_URL` override the corresponding file
fields, and explicit CLI switches take precedence over the file.

```dotenv
TYPESAFE_API_KEY=<your TypeSafe key>
TYPESAFE_DEFAULT_MODEL=jev-latest
OPENAI_API_KEY=<your OpenAI or Azure resource key>
OPENAI_BASE_URL=https://YOUR-RESOURCE.services.ai.azure.com/openai/v1/
```

Omit `OPENAI_BASE_URL` for the public OpenAI API. Azure chat and embedding model
arguments identify deployments. To use `--embedding-model openai`, configure a
separate deployed embedding model as needed:

```dotenv
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
```

The adapter uses the official [TypeSafe Python SDK](https://docs.typesafe.ai/sdk/python)
and follows the [API reference](https://docs.typesafe.ai/api). Jev-Mem requires Python 3.11 or newer; Python 3.11 is recommended. `requirements.txt` installs `typesafe-sdk>=0.7,<1`.
The project currently tests against SDK 0.7.0.

Both CLI entry points load `.env`. Set `TYPESAFE_API_KEY` to the key itself,
without a `Bearer` prefix. An existing environment variable takes precedence
over `.env`. Library callers should load `.env` themselves or pass
`JevClient(config, api_key=...)`. Jev uses this TypeSafe key; OpenAI/Azure uses
`OPENAI_API_KEY` separately. The SDK handles the authentication header.

The underlying SDK call has this shape (a standalone example):

```python
from dotenv import load_dotenv
from typesafe_sdk import TypeSafeClient, Noul, Choice

load_dotenv()
with TypeSafeClient() as client:  # reads TYPESAFE_API_KEY
    result = client.system_one(
        state={"observation": "Alice attended a workshop before her exhibition."},
        questions={
            "episodic": Noul(
                instructions="Does `observation` describe a particular experience?",
                criteria={"true": "A specific event", "false": "Only a general fact"},
            ),
            "order": Choice(
                instructions="In `observation`, when was the workshop relative to the exhibition?",
                criteria={"before": "Earlier", "after": "Later", "unknown": "Unstated or ambiguous"},
            ),
        },
    )
print(result.nouls["episodic"].noul)
print(result.choices["order"].choice)
```

Jev-Mem reuses a synchronous client and batches typed questions with the same
state in one `system_one` call. Prompts reference state paths explicitly because
question IDs are not model input. Its adapter validates Noul probabilities and
Choice labels, complete distributions, normalization and confidence. Choice
decisions use the selected option's probability; returned confidence is a
distribution summary and is retained for inspection, not treated as correctness.

SDK retries are disabled inside the adapter so every network attempt counts
against Jev-Mem's call budget. The outer loop handles transient failures,
including 429/529, with backoff and `Retry-After` within the remaining deadline.
Authentication (401) and request validation (422) failures are not retried.
The client supports `close()` and context-manager use.

Credentials and raw observations are not written to Jev-Mem decision logs.
The bounded process-local cache includes model, state and full question definitions;
errors and fallback decisions are not cached. `decision_schema_version=noul-choice-v2`
changes CLI memory/result fingerprints, keeping the revised policy separate from
previous runs. Rebuild manually managed library caches when changing prompts.

The live transport has mock-HTTP contract tests. No live Jev key validation or
end-to-end Azure request was performed as part of the offline prototype tests.

## Run

```bash
source .venv/bin/activate
python -m pytest -q
python jev_mem_demo.py
python test_fixed_memory.py --help
```

The demo uses explicit mock decisions and deterministic lexical embeddings.
It demonstrates control flow, not Jev accuracy. It never generates an answer
with an LLM or downloads an embedding model.

For live LoCoMo runs:

```bash
python test_fixed_memory.py --jev-config config/jev_mem.json \
  --sample 0 --model gpt-4o-mini --max-questions 10 --best-of-n 1
```

Add `--no-jev-write` or `--no-jev-read` to ablate either controller independently.
Omit Jev-Mem flags/config for the baseline. `--jev-mock` replaces only Jev; the
benchmark's answer generation and evaluation still call System Two. Existing
benchmark metrics and LLM judges are evaluation infrastructure, separate from
memory-control decisions. `--use-episodes` is rejected with Jev-Mem writes because
its legacy LLM segmentation would bypass admission.

LoCoMo reuses a saved graph automatically when `graph.json` exists at the resolved
cache path. Keep the same model, embedding model, sample, cache root and Jev-Mem
configuration. Question limits and category filters can change without rebuilding.
Add `--rebuild` to skip loading, reconstruct from the conversation, and replace
the saved graph, vectors and keyword index. Use a different `--cache-dir` root to
preserve the previous construction. There is no CLI flag that disables saving:
`--rebuild` bypasses cache reads but still saves the new memory.

The admission setting is included in the config fingerprint. Disabling it selects
a new cache, so graphs that previously dropped turns are not reused. Reconstruct
memory before comparing QA accuracy; storing all turns does not itself guarantee
that retrieval will find every answer.

In library code, a new `MemoryBuilder` starts empty; call `builder.load()` to reuse
a cache, or `builder.build_memory(sample)` followed by `builder.save()` to rebuild.
Use a fresh builder for reconstruction, since building on an already loaded
instance adds to its current memory. The constructor does not auto-load vectors.

For retrieval tuning, `--reuse-memory PATH` loads an exact existing Jev-Mem cache
for one sample even when read settings change. It rejects differing construction
settings and cannot be combined with `--rebuild`. New logs/results use the new
configuration fingerprint; the source graph is not overwritten. Library code
can use `builder.load(PATH)` while keeping a separate output directory.

`config/jev_mem_accuracy.json` provides a wider retrieval experiment. The harness
uses `answer_top_k` (default 15) and `multihop_top_k` (default 30), and now records
retrieved dialogue IDs and evidence recall after each query. See [evaluation guidance](evaluation.md) for evidence-recall diagnostics and
reproducible comparisons. Both bundled profiles are experiments, not validated optima.

For application observations, write a JSON list of strings or objects with
`content` (or `text`), optional ISO timestamp and metadata:

```json
[
  {"content": "Alice prefers concise explanations.",
   "timestamp": "2026-09-19T12:00:00Z",
   "metadata": {"entities": ["person:alice"], "source": "conversation"}}
]
```

```bash
python main.py --mode build --input observations.json --jev-mem --cache-dir ./jev_mem_cache/app
python main.py --mode query --question "What does Alice prefer?" --jev-mem --cache-dir ./jev_mem_cache/app
```

Use identical config flags for the build/query pair so they select the same
cache fingerprint. Library users can inject `JevMemConfig` and `JevClient`
into `MemoryBuilder`/`QueryEngine` directly. `main.TRGSystem` remains a compatible
alias for the repaired `JevMemSystem` orchestration class.

## Traces and remaining evaluation

Decision logs include admission/types, relation scores, full Choice answers,
returned model and token usage, graph needs/budgets,
visited nodes, examined edges, depth, Jev calls, cache hits, stopping and fallback
events. Retrieval records have `llm_calls=0`; subsequent `system_two_answer`
records use the same query ID and count successful generation calls. Evaluator
calls are not included in retrieval latency. Configuration is saved alongside
the graph and included in LoCoMo result files.

Tests cover HTTP contracts, retries/auth failures, invalid probabilities,
admission rejection, directional relations, timestamp/alias handling,
construction rollback, both persistence backends, bounded traversal,
adaptive stopping, consolidation decisions, ablations and System-Two handoff.
Full dataset accuracy, probability calibration, latency under live provider
load, automatic consolidation summary quality and LongMemEval integration
remain follow-up work. No benchmark-quality claim is made from mock tests.
