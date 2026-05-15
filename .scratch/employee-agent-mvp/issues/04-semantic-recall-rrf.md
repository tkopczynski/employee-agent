# 04 — Semantic Recall + RRF

Status: ready-for-human

## Parent

PRD: `.scratch/employee-agent-mvp/PRD.md`

## What to build

Add semantic retrieval and fuse it with the existing keyword index. The **Embedder** (fastembed `bge-small-en-v1.5`, 384-dim, ADR-0002) embeds the same `search_units` into a sqlite-vec index. `search_recall` now runs both the sqlite-vec semantic query and the FTS5 keyword query and fuses their **rankings** with Reciprocal Rank Fusion (k≈60, no score normalisation or weight tuning), then applies the K / token-ceiling budget. The headline paraphrase query now lands: "prepare a report" finds a Conversation that said "draft a one-pager".

## Acceptance criteria

- [x] Each indexed unit is embedded locally via the `Embedder` interface into a sqlite-vec index; no hosted embedding provider; works offline
- [x] `search_recall` fuses sqlite-vec and FTS5 results via RRF; ordering rewards "good in both lists" over "good in one"
- [x] A paraphrased query retrieves a Conversation that used different wording (semantic match)
- [x] An exact-token query still retrieves its keyword match (no regression from 03)
- [x] The result budget (top-K, token ceiling) is honoured after fusion
- [x] Tests: **Recall** hybrid retrieval + RRF ordering with a deterministic fake Embedder (assert ordering/recall behaviour, not raw vectors)

## Comments

**2026-05-15 — implemented via TDD (4 red→green cycles + refactor).**

Spec: `docs/spec-04-semantic-recall-rrf.md` (agreed before coding).

Delivered, all behind the unchanged `Recall` public interface (`add_units`,
`search`, `Hit`) — a purely additive deepening of the deep module:

- `add_units` now batches one local `Embedder.embed` call (ADR-0002, offline)
  and writes a `sqlite-vec` `vec0(embedding float[384])` row sharing the
  unit's rowid, in the same transaction as the FTS insert.
- `search` is hybrid: FTS5 keyword arm + sqlite-vec KNN semantic arm, **both
  seal-gated** (semantic obeys ADR-0005 exactly like keyword), fused by RRF
  (`1/(rrf_k+rank)` summed, `rrf_k=60`, no normalisation/weights), folded to
  one Hit per Conversation by its best (max-RRF) unit, then bounded by the
  budget.
- Result budget after fusion (the 03-deferred cap): top-K then a token
  ceiling via a deterministic dependency-free `ceil(len/4)` estimate — keep
  whole hits, never truncate snippets, always return the top hit. `recall_k`
  / `recall_token_ceiling` / `rrf_k` are config (PRD).

**03 contract change (agreed with User).** Hybrid recall always returns
nearest semantic neighbours, so a query with no shared keywords still yields
hits — that is the paraphrase feature. The Issue-03 assertion
`recall.search("drafted") == []` could not survive; it was re-expressed to
assert the real intent (the Agent reply text is never an indexed unit / never
a hit snippet). No other 03 assertion changed.

**Test embedder.** The random-hash `FakeEmbedder` was replaced by a
controllable `TopicEmbedder` (same-topic → identical basis vector, different
topics orthogonal, unknown → shared far vector). With no topics it is an
inert constant embedder, so the migrated keyword tests stay deterministic
(keyword ranking dominates; ties broken by the conversation-fold's
`(-score, conversation_id)` order). Semantic tests declare topics and assert
ordering/recall, never raw vectors (PRD Testing Decisions).

`Agent.search_recall` now lets `k` fall through to config instead of
hardcoding 6 (single source of truth; same principle as model names).

Tests: `tests/test_recall_semantic.py` (6 new — seal-gated paraphrase, RRF
"good in both", exact-token no-regression, token-ceiling drops whole hits,
top hit always returned, top-K after fusion). Existing Recall/agent/sealing
tests migrated to `TopicEmbedder`. Full suite **29 green**. The real
`FastEmbedEmbedder` stays untested glue (no model download in tests), as in
03; Compaction-time incremental embedding + cost logging remain Issue 06.

## Blocked by

- 03 — Keyword Recall, end-to-end
