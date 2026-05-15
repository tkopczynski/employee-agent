# Spec — 04 Semantic Recall + RRF

Issue: `.scratch/employee-agent-mvp/issues/04-semantic-recall-rrf.md`
Constrained by: ADR-0001 (single SQLite file), ADR-0002 (local fastembed),
ADR-0005 (seal-gate), PRD "Recall retrieval", `CONTEXT.md` vocabulary.

## Goal

Make `Recall.search` a **hybrid** retriever: the existing FTS5 keyword arm
plus a new `sqlite-vec` semantic arm, fused by **Reciprocal Rank Fusion**, then
bounded by a **top-K + token-ceiling** budget. Headline behaviour: a
paraphrased query ("prepare a report") recalls a Conversation that used
different wording ("draft a one-pager"), while exact-token lookups still work
(no regression from 03).

## Interface (unchanged public surface — deep module)

`Recall.add_units(units)` and `Recall.search(query, k) -> list[Hit]` keep their
signatures. `Hit` is unchanged. All new complexity (vectors, RRF, budget) stays
behind these two methods. This is a purely additive change to a deep module.

## Design

### 1. Embedding on `add_units`

- A `vec_search_units` virtual table is created via the `sqlite-vec`
  extension: `vec0(embedding float[384])`, `rowid = search_units.id`
  (PRD schema, ADR-0002 dimensionality).
- `add_units` embeds each unit's `text` through the injected `Embedder`
  (`embed(texts) -> list[list[float]]`) in **one batched call** and inserts the
  vector at the unit's `search_units.id` rowid, in the same transaction as the
  FTS insert. Offline by construction — the `Embedder` seam never makes a
  network call (ADR-0002).
- The `sqlite-vec` extension is loaded on Recall's own connection
  (`enable_load_extension` + `sqlite_vec.load`).

### 2. Hybrid `search` with RRF

Both arms are **seal-gated** (join `search_units -> conversations`,
`sealed_at IS NOT NULL`) — semantic results obey ADR-0005 exactly like keyword.

- **Keyword arm**: existing FTS5 `MATCH ... ORDER BY bm25` over sealed units →
  ordered list of `search_units.id`.
- **Semantic arm**: embed the query, `vec_search_units` KNN
  (`embedding MATCH ? ORDER BY distance`) restricted to sealed unit ids →
  ordered list of `search_units.id`.
- **RRF fuse (unit level)**: for a unit appearing at 1-based rank `r` in a
  list, it scores `1/(K_RRF + r)` for that list; a unit's fused score is the
  sum across the lists it appears in. `K_RRF = 60`. No score normalisation,
  no per-arm weighting (per issue + PRD). A unit ranked in **both** lists beats
  one ranked highly in only one — the property the acceptance criteria call
  for.
- **Fold to one Hit per Conversation**: a Conversation's score is the **max**
  fused score over its units; its snippet is that best unit's text; summary
  line + date come from the `conversations` row (as in 03). Conversations are
  ordered by that score, descending.

### 3. Budget after fusion (acceptance #5; the 03-deferred budget)

Applied to the fused, Conversation-folded, ranked list:

- **Top-K**: at most `k` Conversations (caller's `k`, default from config).
- **Token ceiling**: walk the ranked hits, estimating each hit's token cost
  (summary line + snippet) with a deterministic, dependency-free heuristic
  (`ceil(len(text) / 4)` — no tokenizer, stable across runs). Keep whole hits
  while the running total stays within the ceiling; once the next hit would
  exceed it, **stop** — "fewer complete hits over more truncated ones" (PRD).
  Snippets are never truncated. The single top hit is always returned even if
  it alone exceeds the ceiling (recall must not silently return nothing for a
  real top match).

### 4. Config

`Config` gains a recall section with defaults (overridable, like the model
map): `recall_k = 6`, `recall_token_ceiling = 2000`, `rrf_k = 60`
(PRD: "K and the ceiling are config"; values from the PRD ranges). `search`'s
explicit `k` argument still wins when the caller passes one; otherwise
`recall_k` is the default. `Agent`'s `search_recall` tool keeps passing the
model's requested `k` (default falls through to config).

## Test strategy (deterministic, offline — PRD Testing Decisions)

New controllable fake Embedder (`tests/fakes.py`): a **topic** embedder. You
give it topic→texts groups; texts in the same topic embed to the same unit
basis vector, different topics are orthogonal, unknown text is a distinct
"noise" vector. This lets tests assert *ordering and recall behaviour*, never
raw vectors, and makes RRF deterministic. The generic random `FakeEmbedder` is
**replaced** by this; existing Recall/integration tests are migrated to
declare their topics (keyword tests group their corpus so the semantic arm
reinforces, keeping their existing exact-order assertions valid and
deterministic).

Behaviours under test (vertical TDD slices, one at a time):

1. **Embedding happens & is seal-gated** — a paraphrase query returns nothing
   before Seal, then the semantically-close Conversation after Seal (semantic
   arm respects ADR-0005).
2. **Paraphrase recall** — query "prepare a report"; corpus has a sealed
   Conversation whose only relevant unit says "draft a one-pager" with **zero
   shared content words**; it is recalled (semantic arm + RRF).
3. **No keyword regression** — an exact-token query still returns its keyword
   match (the headline 03 behaviour holds under fusion).
4. **RRF rewards "good in both"** — a Conversation ranked mid in keyword *and*
   mid in semantic outranks one ranked top in only a single arm.
5. **Top-K cap after fusion** — more matching Conversations than `k` → exactly
   `k` returned.
6. **Token-ceiling budget** — many hits over the ceiling → fewer *complete*
   hits returned (no truncated snippets); the top hit always survives.

Re-expressed Issue-03 test (per agreed decision): in
`tests/test_recall_integration.py`,
`test_seal_indexes_user_turns_requests_and_summary_not_agent_turns` drops the
now-invalid `recall.search("drafted") == []` and instead asserts the real
intent — the Agent reply text never appears as any hit's snippet across the
recallable corpus (Agent Turns are not indexed units), while the User Turn,
Request and Summary remain recallable. No other Issue-03 assertions change.

## Out of scope / unchanged

- `get_conversation`, the seal-gate mechanism, `Agent.seal`/`_units_for`,
  the Store schema for conversations/turns, the tool surface and its past-vs-
  current framing — all unchanged (additive change only).
- Real `FastEmbedEmbedder` stays untested glue (no model download in tests),
  as in 03.
- Compaction-time incremental embedding and cost logging — Issue 06.

## Acceptance mapping

| Issue criterion | Covered by |
|---|---|
| Units embedded locally via Embedder into sqlite-vec; offline | Design §1; test 1 |
| `search` fuses vec + FTS5 via RRF; rewards "good in both" | Design §2; test 4 |
| Paraphrased query retrieves differently-worded Conversation | Design §2; test 2 |
| Exact-token query still retrieves keyword match (no 03 regression) | Design §2; test 3 |
| Result budget (top-K, token ceiling) honoured after fusion | Design §3; tests 5, 6 |
| Tests: hybrid + RRF ordering with deterministic fake Embedder | whole test strategy |
