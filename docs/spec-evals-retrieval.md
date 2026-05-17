# Spec — Retrieval-Quality Eval

Constrained by: ADR-0008 (retrieval-only, golden Summaries, outside the suite),
ADR-0006 (three indexed unit kinds), ADR-0005 (seal-gate), ADR-0002 (local
fastembed), ADR-0001 (single SQLite file), PRD "Recall retrieval" + US-18/19/20,
`CONTEXT.md` vocabulary.

## Goal

A standalone, deterministic, no-LLM eval that measures `Recall.search` quality
over a known corpus using the **real** `FastEmbedEmbedder` + sqlite-vec + FTS5 +
RRF. It prints a per-probe / per-arm scorecard and fails (nonzero exit) if a
tunable recall floor is breached. It is the measurement instrument for the
retrieval-quality-vs-cost learning goal: change embedding model / `rrf_k` /
`recall_k`, re-run, read the new trade-off.

## Not in scope (unchanged)

- Any LLM call at run time; end-to-end answer/agent-decision evals (a later
  additive layer, ADR-0008).
- The seal-gate / live-session-exclusion behaviour — already covered
  deterministically by `tests/test_recall_semantic.py`; not re-asserted here.
- Production source code (`src/employee_agent/**`) — the eval is read-only over
  the existing public interfaces (`Store`, `Recall`, `Unit`, `Config`,
  `FastEmbedEmbedder`). No production change.
- `CONTEXT.md` — eval vocabulary is implementation language (ADR-0008).

## File layout

```
evals/
├── __init__.py
├── __main__.py        # `uv run python -m evals` entry point
├── dataset.yaml        # the committed corpus + probes + floor (I draft it)
├── loader.py           # parse + validate dataset.yaml -> typed objects
└── runner.py           # build corpus, run probes, score, print, exit code
tests/
└── test_evals_scoring.py   # hermetic unit test of the scoring math only
```

`pyyaml` is added to the **dev** dependency group in `pyproject.toml` (never
`[project.dependencies]` — the Agent runtime never reads the dataset).

## Dataset schema (`evals/dataset.yaml`)

```yaml
floor:
  recall_at_k: 0.80      # overall recall@recall_k must be >= this
  hit_at_1: 0.55         # overall hit@1 must be >= this

conversations:
  - id: 1
    topic: "Q1 revenue report"          # human label, not indexed
    turns:
      - { role: user,  text: "..." }
      - { role: agent, text: "..." }    # agent turns are NOT indexed (ADR-0006)
    golden:
      requests: ["Prepare the Q1 revenue report"]   # 'request' units
      summary:  "User asked the Agent to ..."        # 'summary' unit (prose)
      outcomes: []                                    # stored, not indexed

probes:
  - query: "when did I ask you to put together that quarterly earnings write-up"
    arm: semantic            # semantic | keyword
    expect_conversation: 1   # exactly one correct Conversation id
```

`loader.py` validates: every `expect_conversation` exists; every `arm` is
`semantic|keyword`; floor keys present and in `[0,1]`; ids unique. A malformed
dataset is a hard error, not a silent skip.

## Corpus construction (per run, in a tmp dir — no production change)

Mirrors `tests/test_recall_semantic.py`, with the **real** embedder:

1. `store = Store(<tmpdir>/eval.sqlite)`; `recall = Recall(store,
   FastEmbedEmbedder(), Config())`.
2. For each `conversation`: `cid = store.start_conversation()`; append each
   `turn` via `store.add_turn(cid, seq, role, text)`;
   `store.seal_conversation(cid, golden.summary, golden.outcomes)`.
3. Index exactly the three production unit kinds (ADR-0006,
   `Agent._units_for`): one `Unit(cid,"user_turn",text)` per **user** turn, one
   `Unit(cid,"request",r)` per golden request, one
   `Unit(cid,"summary",golden.summary)`. Agent turns and `outcomes` are not
   indexed. `recall.add_units([...])` (one batched real embed per conversation).

The dataset's `conversation.id` is authored to equal the `Store`-assigned
`conversation_id` (corpus built in id order into a fresh db); `loader.py`
asserts this invariant after build so a probe's `expect_conversation` is
unambiguous.

## Scoring

For each probe: `hits = recall.search(probe.query)` (k falls through to
`Config().recall_k`, default 6 — exactly what the Agent sees). Let
`ids = [h.conversation_id for h in hits]`.

- `recall@k`  = mean over probes of `1 if expect in ids else 0`.
- `hit@1`     = mean over probes of `1 if ids and ids[0]==expect else 0`.
- `recall@1 / @3 / @6` = same as recall@k but truncating `ids` to 1/3/6
  (the curve; nearly free, shows ranking headroom).
- Per-arm: the above, partitioned by `probe.arm`, so the semantic vs keyword
  contribution is visible (the learning artifact).

`tests/test_evals_scoring.py` unit-tests this pure math against a fake
`search` returning canned id lists (hermetic, in the normal suite) — the
*scoring* is deterministic logic and belongs under pytest; the
*embedder-driven run* does not.

## Output (scorecard, always printed)

Plain-text table to stdout:

- Per-probe row: `arm | expect | rank-of-expect (or MISS) | top-3 ids | query`.
- Aggregates block: overall + per-arm `recall@1/3/6`, `hit@1`, n probes.
- Verdict line: `PASS` / `FAIL (recall@6 0.74 < floor 0.80)`.
- Active knobs echoed: embedding model name, `recall_k`, `rrf_k`,
  `recall_token_ceiling` — so a saved scorecard is self-describing when
  comparing trade-offs across runs.

Exit code 0 on PASS, 1 on FAIL or malformed dataset.

## Dataset authoring contract (ADR-0008 — the eval's honesty)

I author `dataset.yaml` (~20 conversations incl. several distractor clusters,
~35 probes) to this contract:

- **Semantic probes** share **zero content words** with their target's units;
  only meaning connects (genuinely exercises the embedder — US-19).
- **Keyword probes** hinge on a **rare exact token** (error code, project
  codename) the User would recall verbatim; a **distractor** discusses the same
  topic in paraphrase but never uses that exact token, so only the keyword arm
  disambiguates (US-20).
- **Distractor clusters**: ≥2 sibling topics (e.g. Q1-revenue / Q3-headcount /
  competitor-teardown "report" conversations) so a probe must return *one
  specific* Conversation — ranking under test, not mere topical match.

## Floor procedure

Floor is empirical: generate the dataset → run once → set `floor.recall_at_k`
and `floor.hit_at_1` a margin (~0.05–0.10) below the observed scores, committed
in `dataset.yaml`. Re-tuned by hand as the corpus or knobs change.

## Acceptance

| Want | Covered by |
|---|---|
| Retrieval measured with the real embedder, no LLM at run time | Corpus construction; runner |
| Corpus indexes the 3 ADR-0006 unit kinds like production | Corpus construction step 3 |
| Probes split + scored per arm (semantic/keyword) | Scoring; Output |
| Distractors make recall@k discriminating | Authoring contract |
| Always-printed scorecard + tunable failing floor | Output; Floor procedure |
| Runs outside the hermetic suite; scoring math still unit-tested | File layout; `test_evals_scoring.py` |
| No production / `CONTEXT.md` change | Not-in-scope |
