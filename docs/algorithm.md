# Jev-Mem: Typed Probabilistic Control of Graph Memory

This methods draft describes the current implementation and the active settings
in `config/jev_mem.json`. The proposed contributions concern the system design;
claims of priority over prior work require a separate literature comparison.

## 1. Proposed contribution and design rationale

Jev-Mem separates persistent evidence, structured memory decisions, and answer
generation. An observation is retained as a canonical memory node with its
original content and source metadata. A System-One controller, implemented with
Jev, evaluates explicit typed questions to annotate the observation and identify
relations to existing memories. At query time, the same controller estimates
which relation types are useful, allocates a finite graph-expansion budget, scores
candidate evidence, and decides whether another retrieval round is worthwhile.
A System-Two language model generates the answer from the selected evidence.

The current design preserves observations at ingestion and applies selectivity
during relation construction and retrieval. This choice addresses a basic
asymmetry: an observation that seems unimportant when written may later become
essential to a question. Accordingly, the main write path has no learned
store/discard decision. Brief responses and repeated text remain available as
separate observations with their own provenance. The original admission policy
is retained only as an optional ablation.

The contribution can be framed around three mechanisms:

1. **A shared typed control interface for writing and reading.** Independent
   yes/no judgments describe overlapping properties; categorical judgments
   select mutually exclusive actions or relations. Both operate on explicit
   structured state and yield auditable outputs.
2. **Preserved observations with selective graph structure.** One set of memory
   nodes supports semantic, temporal, causal, and entity relations. Expensive
   relation judgments are restricted to a bounded candidate set, while available
   timestamp and exact-identifier evidence is handled deterministically.
3. **Query-dependent retrieval with explicit resource limits.** Predicted graph
   needs determine relation-specific expansion allocations. An evidence-feedback
   loop combines candidate scoring, beam selection, and stopping decisions under
   independent bounds on expansion, inspected edges, visited nodes, depth, calls,
   and elapsed time.

This framing attributes the existing graph/vector data plane to MAGMA and the
decision primitives to TypeSafe. It does not claim that typed model outputs,
multi-graph memory, or beam search are individually new, nor that the project
introduces a newly trained controller. The contribution to establish empirically
is the behavior of their integration in Jev-Mem.

## 2. Representation and decision interface

Let an observation be \(o_t=(x_t,\tau_t,\mu_t)\), where \(x_t\) is its text,
\(\tau_t\) is an optional timestamp, and \(\mu_t\) contains provenance such as
speaker, dialogue identifier, session, and source. The memory state is

\[
\mathcal M_t=(V_t,\{E_t^g\}_{g\in\mathcal G},I_t^{\mathrm{vec}},I_t^{\mathrm{lex}}),
\qquad
\mathcal G=\{\mathrm{semantic},\mathrm{temporal},\mathrm{causal},\mathrm{entity}\}.
\]

The relation sets are logical views of a single directed multigraph: each
observation has one canonical node, and multiple typed edges may connect a pair.
The vector and lexical indexes reference the same node identifiers. A node
retains raw text, provenance, an embedding, and a four-component type vector:

\[
\mathbf t(v)=(t_{\mathrm{episodic}},t_{\mathrm{semantic}},
              t_{\mathrm{procedural}},t_{\mathrm{preference}}).
\]

These type labels may overlap. They are distinct from the four graph relations:
for example, “episodic” is a node attribute, whereas “temporal” denotes a relation
view. The current retrieval score does not consume the node-type vector; it is
stored for inspection and subsequent extensions.

We write a controller invocation as
\(\mathcal J(S,\mathcal Q)\), with shared state \(S\) and a batch of questions
\(\mathcal Q\). The implementation uses the following provider primitives:

| Primitive | Output | Use in Jev-Mem |
|---|---|---|
| Noul | A model-reported probability in \([0,1]\) for an explicit proposition | Memory types, semantic/entity/causal relations, graph needs, candidate properties, stopping signals |
| Choice | Selected label, distribution over options, and distribution-derived confidence | Implicit temporal order and consolidation representation |

Independent Noul questions are not normalized to sum to one. “Independent” here
means separately evaluated propositions, not a claim of statistical independence.
Choice is used when a single alternative should be selected. Action thresholds
use the selected label's probability; the returned confidence is retained in
the audit record and is not interpreted as probability of correctness.

Questions explicitly identify their state fields. Questions sharing the same
state are batched in one SDK request, but no question silently depends on another
answer in that batch. Probability calibration is an empirical question, not an
assumption guaranteed by the API. The interface follows the
[TypeSafe API](https://docs.typesafe.ai/api) and
[Python SDK](https://docs.typesafe.ai/sdk/python).

## 3. Write workflow: preserve observations and construct relations

### 3.1 Observation preparation and typing

For each valid observation, the writer preserves its text and source identifiers
and requests four Noul judgments for episodic, semantic, procedural, and preference
content. None of these values gates insertion. The implementation accepts supplied
entities or uses a simple name-extraction heuristic, enriches the text with metadata
and keywords, and computes its embedding. It does not require System-Two extraction
or summarization on the successful Jev-Mem path.

The LoCoMo adapter processes conversation sessions and their turns. Each successfully
written turn produces a canonical node; short and duplicate turns are retained.
Image captions already included by the dataset loader remain part of the input
text. Dataset answers and annotated QA evidence are not used to construct memory.

### 3.2 Candidate selection

For the new node \(v\), deterministic candidate generation combines vector
similarity, keyword overlap, shared entity strings, and timestamp proximity to
select at most \(K_w\) existing event nodes:

\[
C(v)=\operatorname{TopK}_{u\in V_t}\,s_{\mathrm{cand}}(v,u).
\]

The current candidate heuristic gives a similarity contribution to vector-search
hits, then adds entity, keyword, and time signals while scanning existing event
nodes. The cap bounds the number of pairs submitted to Jev; it does not make
candidate generation independent of memory size.

### 3.3 Batched relation inference

A single request evaluates the new observation against all candidates. For each
pair, independent Noul questions estimate useful semantic relatedness, causal
influence in each direction, and whether the observations describe the same
episode. If exact entity strings do not match, an additional Noul evaluates
whether names or aliases refer to the same entity. Semantic similarity alone
does not create a causal edge.

Available timestamps determine chronological edges directly; matching entity
strings determine shared-entity edges directly. When either timestamp is missing,
a Choice question selects one temporal alternative:

\[
\{\text{before},\text{after},\text{during},\text{contains},
\text{overlaps},\text{same\_time},\text{unknown}\}.
\]

For an inferred relation \(g\), an edge is created only if its probability meets
\(\theta_{\mathrm{rel}}\). The selected temporal alternative contributes at most
one ordering relation; “unknown” contributes none. The same-episode relation is
evaluated separately and may coexist with ordering. Causal and temporal edge
orientation follows the inferred direction. Exact timestamps and shared entity
strings supply deterministic relations with weight one.

In LoCoMo, node timestamps are conversation-session timestamps. Consequently,
deterministic chronology describes observation time and does not necessarily
establish when the narrated event occurred. Exact string equality is also a
practical matching heuristic, not a guarantee of resolved real-world identity.
These distinctions should remain visible in the paper's interpretation.

### 3.4 Commit and maintenance

The writer inserts the canonical node, embedding, selected edges, and keyword
index entries, and records the typed decisions. Partial graph insertion triggers
rollback of the new graph node and vector; this is an in-process safeguard rather
than a distributed transactional guarantee. Graph/vector/index snapshots support
reuse across retrieval experiments.

Every \(J_c\) writes, optional consolidation compares the new memory with a bounded
set of neighbors. Nouls describe redundancy, contradiction, obsolescence, and
link usefulness. A Choice selects `keep_separate`, `merge`, `promote`, or
`uncertain`. The normal benchmark path records these decisions and adds applicable
links; it does not delete observations or automatically generate summaries.
Obsolescence is recorded for inspection rather than used to remove historical
evidence.

If a caller supplies a System-Two summarizer, an approved merge/promotion can
produce an additional representation with source-node provenance. Its selected
action must meet the consolidation threshold and its contradiction score must
remain below that threshold. The result re-enters the writer, while original
observations remain available.

```text
Algorithm 1: WriteObservation(o, M)
  Require valid observation text and metadata.
  t ← J(observation=o.text, questions=four memory types)
  v ← prepare canonical node with raw text, provenance, t, and embedding
  C ← deterministic candidate search(M, v, Kw)
  if C is not empty:
      R ← J(state={v, C}, questions=batched pair relations)
      Enew ← deterministic timestamp/entity edges
              ∪ inferred edges passing the relation threshold
  else:
      Enew ← ∅
  insert v, its vector, Enew, and keyword entries; record decisions
  if periodic maintenance is due:
      record bounded consolidation decisions and supported links
      optionally invoke a supplied summarizer for an approved action
  return v
```

The pseudocode shows the successful admission-disabled path. If a required Jev
call fails, the configured implementation either uses the existing MAGMA fallback
or raises an error. The fallback may use System-Two extraction and is logged.

## 4. Retrieval workflow: route, expand, and assess evidence

### 4.1 Query routing and budget allocation

Given query \(q\), Jev returns six Nouls: four relation needs
\(\mathbf p(q)=\{p_g(q)\}_{g\in\mathcal G}\), a multi-hop-need value \(h(q)\),
and a recency-importance value \(r(q)\). More than one graph may be useful.
The active graph set is

\[
\mathcal A(q)=\{g:p_g(q)>0\;\land\;p_g(q)\geq\theta_{\mathrm{act}}\}.
\]

Let \(B\) be the total expansion allocation and \(m\) the minimum per active graph.
After reserving feasible minimum allocations, the remaining budget is distributed
according to

\[
w_g(q)=\frac{p_g(q)^\gamma}{\sum_{j\in\mathcal A(q)}p_j(q)^\gamma},
\qquad b_g=m+\operatorname{LRound}_g\big[(B-m|\mathcal A|)w_g\big].
\]

Here \(\operatorname{LRound}\) denotes largest-remainder integer allocation over
the active graphs. If the budget cannot support every minimum, the implementation
retains the highest-need graphs and adjusts the minimum to feasibility. Inactive
graphs receive zero; if no graph is active, all graph budgets are zero. Thus
\(\sum_g b_g\le B\), with equality when a nonempty allocation is made.

The adaptive depth allowance is

\[
D(q)=\min\{D_{\max},\max(1,\lceil D_{\max}h(q)\rceil)\}.
\]

These budgets are allocated once per query, not reallocated after each round.
The feedback loop changes candidate selection and the decision to continue.

### 4.2 Hybrid anchor retrieval

Vector search and keyword search independently produce candidate rankings. Their
reciprocal-rank fusion score is

\[
s_{\mathrm{RRF}}(v,q)=
\sum_{L\in\{L_{\mathrm{vec}},L_{\mathrm{lex}}\}:v\in L}
\frac{1}{\kappa+\operatorname{rank}_L(v)},\qquad\kappa=60,
\]

using one-based ranks. The first \(\min(A,N_{\max},K)\) nodes initialize the
visited set and frontier, where \(A\) is the anchor limit and \(K\) is the final
evidence limit. Keyword search ranks all matched postings before applying its
result limit. In the current code, anchor selection uses RRF, while the retained
anchor scores used for later evidence ranking are clipped cosine similarities.

### 4.3 Evidence checks and bounded graph expansion

At the start of each round, the controller forms \(E_d\), the highest-scoring
\(K\) visited nodes. Jev evaluates four propositions against \((q,E_d)\):
evidence sufficiency \(s_d\), expected usefulness of another round \(u_d\),
missing required evidence \(m_d\), and unresolved contradiction \(c_d\).
Retrieval can stop as sufficient when

\[
s_d\geq\theta_{\mathrm{suff}}
\;\land\;m_d<\theta_{\mathrm{cont}}
\;\land\;c_d<\theta_{\mathrm{cont}}.
\]

It can also stop when \(u_d<\theta_{\mathrm{cont}}\), even if the evidence is
incomplete; that outcome means further retrieval was judged unhelpful, not that
an answer was proved. Hard limits terminate the search independently of these
model judgments. The same configured continuation threshold currently gates
usefulness, missing evidence, and contradiction.

If retrieval continues, the data plane examines edges adjacent to the frontier.
For each eligible edge whose graph budget remains available, its target neighbor
is proposed and that graph's expansion counter is incremented. The implementation
examines both incoming and outgoing neighbors, so stored direction is supplied
as evidence rather than enforced as a one-way traversal constraint. Per-node
proposals are deduplicated; when multiple proposals reach the same node, the edge
with the largest structural probability is retained. Parallel edges can consume
budget before this deduplication. An additional counter bounds all inspected
edges, including ones later rejected.

### 4.4 Candidate scoring and beam update

For every proposed node \(v\), Jev evaluates relevance \(a_v\), usefulness of
its connecting relation \(\ell_v\), new information \(n_v\), and corroboration
of current evidence \(c_v\). These questions for all proposals share one request
state consisting of the query, selected evidence, and candidate descriptions.

Let \(z_v\) be clipped cosine similarity and \(\pi_e\) the retained edge weight.
For graph type \(g\), the implemented transition score is

\[
s(v\mid q,E_d)=
\frac{\lambda_1 z_v+\lambda_2 a_v+
\lambda_3 p_g(q)\ell_v+\lambda_4 n_v+
\lambda_5(\pi_e+c_v)/2}{\sum_{i=1}^{5}\lambda_i}.
\]

If timestamps are available, a small recency adjustment uses query-dependent
importance \(r(q)\). With \(\tau_*\) the newest timestamp among visited nodes,

\[
\rho_v=\frac{1}{1+\max(0,\tau_*-\tau_v)/\mathrm{day}},
\qquad
\widetilde s(v)=\frac{s(v)+0.1r(q)\rho_v}{1+0.1r(q)}.
\]

The top \(W\) candidates, subject to remaining node capacity, become the next
frontier and join the visited set. Paths and graph-budget usage are recorded.
Anchor cosine scores and transition scores are currently retained without a
common learned reranker; this implementation detail should not be described as
a globally calibrated relevance model.

### 4.5 System-Two answer generation

The final \(K\) selected memories are formatted with original text and available
speaker/date information and passed to the answer model. The multi-hop formatter
also includes dialogue identifiers. The answer model performs free-form synthesis;
the retrieval controller does not call it during normal routing or traversal.
Abstention remains possible when the selected evidence does not support an answer.
Answer cleaning preserves lists, names, negation, and temporal qualifiers.

```text
Algorithm 2: Retrieve(q, M, K)
  initialize per-query limits and counters
  (p, h, r) ← J(q, routing questions)
  b ← allocate integer graph budgets(p, B, activation threshold, exponent)
  D ← adaptive depth(h)
  anchors ← TopA(RRF(vector ranking, keyword ranking)), capped by K and Nmax
  U ← anchors; frontier ← anchors; d ← 0
  while U is not empty:
      E ← TopK(U, retained scores)
      if deadline has expired: break
      (s, u, m, c) ← J({q, E}, stopping questions), if enabled
      if sufficient(s, m, c) or further retrieval is unhelpful(u): break
      if any applicable hard limit is reached: break
      C ← bounded neighboring proposals(frontier, b, counters)
      if C is empty: break
      P ← J({q, E, C}, four questions per candidate)
      score C using P, embeddings, graph needs, edge weights, and recency
      frontier ← TopW(C), capped by remaining node capacity
      U ← U ∪ frontier; d ← d + 1
  return TopK(U), traversal metadata

Algorithm 3: Answer(q)
  (E, trace) ← Retrieve(q, M, K)
  y ← SystemTwo(q, format(E))
  return minimally normalized y, trace
```

Jev failure may trigger bounded deterministic retrieval fallback. Call limits
include retry attempts; cached decisions do not consume network attempts. The
latency deadline is checked between operations and bounds remote timeouts, but
synchronous local inference and index operations are not forcibly interrupted.

## 5. Workload and implementation limits

On the successful path, an ordinary write uses one type request and, if candidates
exist, one relation request. At most \(K_w\) pairs are judged. Each pair has four
baseline Nouls, an optional entity Noul, and an optional temporal Choice. Periodic
consolidation adds one request with four Nouls and one Choice per candidate.
These are model-call and question-count bounds, not token-count bounds: texts
and histories have variable length.

For a query with \(R\) expansion rounds, an uncached, error-free run uses one
routing request, up to \(R+1\) stopping requests, and up to \(R\) candidate-scoring
requests, before final answer generation. Each scoring batch contains four
questions per proposed node. Early stopping, disabled checks, empty frontiers,
cache hits, and failures change this count. No claim of constant-time candidate
search or measured latency superiority follows from batching alone.

The active experimental settings are:

| Parameter | Value |
|---|---:|
| Admission filtering | Disabled |
| Write candidates \(K_w\) / relation threshold | 10 / 0.60 |
| Consolidation interval / threshold | 20 writes / 0.85 |
| Anchors \(A\) | 30 |
| Evidence limit \(K\), ordinary / multi-hop | 40 / 50 |
| Graph budget \(B\) / exponent \(\gamma\) | 80 / 1.0 |
| Graph activation threshold / minimum allocation | 0.10 / 1 |
| Beam width / maximum nodes | 10 / 60 |
| Maximum depth / inspected edges | 8 / 2400 |
| Sufficiency / continuation threshold | 0.95 / 0.15 |
| Maximum Jev attempts / latency target | 16 / 15 seconds |
| Transition weights \(\lambda_{1:5}\) | (0.25, 0.35, 0.15, 0.15, 0.10) |

These values are a current experimental configuration, not a validated optimum.
The benchmark harness selects the 40/50 evidence limit using the supplied QA
category; its answer prompts also use that category. This category-aware protocol
must be disclosed, or replaced with a category-agnostic protocol for deployment
claims. Gold answers and evidence identifiers are excluded from construction and
retrieval. Use best-of-N equal to one for an unbiased experiment: existing optional
judge/F1 answer selectors can access the expected answer.

## 6. Overall figure specification

The companion files `figures/jev_mem_overview.svg` and
`figures/jev_mem_overview.pdf` provide a vector illustration. The editable drawing
source is `figures/draw_jev_mem_overview.py`; a logical flowchart is available in
`figures/jev_mem_overview.mmd`.

Use three horizontal regions:

- **Top: observation writing.** Raw observation → Jev memory typing → embedding
  and bounded candidate search → batched relation decisions → canonical-node
  insertion. Label the input “retain every valid observation”; do not draw an
  active discard branch.
- **Middle: shared memory.** One canonical node store and its semantic, temporal,
  causal, and entity relation views, plus vector and keyword indexes. A small
  side branch shows periodic consolidation. Optional summary generation is a
  captioned extension, not part of the primary write arrows.
- **Bottom: query retrieval.** Query → Jev routing and budget allocation → hybrid
  anchors → evidence check. An insufficient-evidence branch leads to bounded
  expansion → Jev candidate scoring and beam update → evidence check. A stopping
  branch leads to selected evidence and System-Two answer generation.

Use blue for Jev decisions, green for deterministic memory operations, neutral
gray for stored evidence, and orange for System Two. Solid arrows carry data or
workflow; dashed arrows mark controller outputs or periodic maintenance. Mark the
retrieval region with its resource limits without placing every numeric setting
inside the figure. Do not draw separate memories for the four relation views or
connect the node-type vector to routing as if that dependency were implemented.

**Suggested caption.** Overall architecture of Jev-Mem. The write workflow retains
each observation as a canonical memory node, annotates overlapping memory types,
and adds relations judged over a bounded candidate set. A shared memory data plane
stores semantic, temporal, causal, and entity views with vector and keyword
indexes. During retrieval, Jev estimates graph needs, allocates expansion budgets,
evaluates candidate evidence, and controls continuation. The selected evidence is
passed to a System-Two language model for answer synthesis. Periodic consolidation
records additional structure while preserving original observations.

## 7. Claim boundaries and evaluation needed

The code supports claims about preservation policy, typed control, batched
candidate evaluation, bounded traversal, and logged decision traces. It does not
yet establish state-of-the-art accuracy, calibrated uncertainty, globally optimal
budget allocation, learned memory updates, strict real-time guarantees, or
autonomous summary consolidation. The current implementation retains an existing
MAGMA fallback, which must be reported separately when comparing System-Two cost.

To establish the contribution, compare the MAGMA baseline, deterministic retrieval
on the same preserved graph, Jev write-only control, Jev read-only control, and the
combined system. Ablate admission, graph routing, transition scoring, stopping,
and consolidation while reporting answer quality, evidence recall, token/call
cost, and latency. Use a fixed graph for read-side ablations and distinguish the
effect of retaining more input from that of the controller. Select parameters on
development data and report held-out samples. Offline anchor-recall measurements
are diagnostic evidence and should not be presented as end-to-end QA gains.

## 8. Implementation map

| Mechanism | Source |
|---|---|
| Observation writing and consolidation | `memory/memory_builder.py` |
| Candidate generation and relation policies | `memory/jev_mem_policies.py` |
| Typed Jev question definitions | `memory/jev_questions.py` |
| SDK calls, validation, cache, retries, audit | `memory/jev_client.py` |
| Routing, budgets, traversal, stopping | `memory/jev_mem_retrieval.py` |
| Keyword search and reciprocal-rank fusion | `memory/query_engine.py` |
| Evidence formatting and answer normalization | `memory/answer_formatter.py` |
| Evaluation context limits and evidence recall | `memory/test_harness.py` |
| Current experimental settings | `config/jev_mem.json` |
