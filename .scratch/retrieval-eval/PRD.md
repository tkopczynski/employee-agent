# PRD: Retrieval-Quality Eval

Status: ready-for-agent

> Domain vocabulary follows `CONTEXT.md`. Constrained by ADR-0008 (evals are
> retrieval-only, over hand-authored golden Summaries, outside the hermetic
> suite), ADR-0006 (three indexed Unit kinds), ADR-0005 (seal-gate), ADR-0002
> (local fastembed), ADR-0001 (single SQLite file). Design detail lives in
> `docs/spec-evals-retrieval.md`. This PRD covers the retrieval-quality eval
> only; an end-to-end (real-LLM) eval is an explicitly deferred later layer.

## Problem Statement

The User has built Recall — hybrid keyword + semantic search over Sealed
Conversations — but has no way to know whether it actually works. Every existing
test uses a toy `TopicEmbedder` where the User *dictates* which texts are
"similar", so the tests prove the plumbing (RRF fuses, the seal-gate holds) but
never that real embeddings retrieve the right past Conversation for a real
question. The deeper need: the project's whole point is learning cost-effective
operation over a growing corpus, and the per-task model map / `rrf_k` /
`recall_k` are the knobs that trade quality for cost — but the User cannot
*measure* what happens to retrieval quality when a knob moves. They want a
simple, deterministic, free instrument that answers "if I ask the Agent about
something weeks later, does the right Conversation come back — and did changing
a knob make that better or worse?"

## Solution

A standalone eval — `uv run python -m evals` — that builds a known corpus of
Sealed Conversations using the **real** `FastEmbedEmbedder` + sqlite-vec + FTS5
+ RRF (no LLM at run time), runs a set of probe queries through
`Recall.search`, and prints a per-probe / per-arm scorecard plus a PASS/FAIL
verdict against a tunable recall floor. The corpus is one committed, human-
editable `dataset.yaml`: per Conversation, the raw Turns plus a hand-authored
*golden* Summary and Request list (the ideal Summarizer output, pinned by hand
so retrieval quality is isolated from Summarizer quality), indexed exactly like
production (the three ADR-0006 Unit kinds). Probes are tagged `semantic` or
`keyword` so the scorecard breaks the score down per arm, making the value of
the semantic arm and of RRF directly visible. The eval lives outside
`uv run pytest` because the real embedder is barred from the hermetic suite;
only its pure scoring math is unit-tested under pytest. Changing an embedding
model or `rrf_k`/`recall_k` and re-running yields a new, comparable scorecard —
the measurement instrument the learning goal needs.

## User Stories

1. As the User, I want to run one command and get a verdict on whether Recall
   retrieves the right past Conversation, so that I know my memory feature
   actually works rather than just compiling.
2. As the User, I want the eval to use the real local embedder, not the toy
   `TopicEmbedder`, so that it measures genuine retrieval and not my own fixture
   assumptions.
3. As the User, I want the eval to never call an LLM at run time, so that it is
   free, fast, deterministic, and runnable offline as often as I like.
4. As the User, I want each fixture Conversation indexed exactly like a real
   Sealed Conversation — raw User Turns plus the extracted Requests plus the
   Summary — so that the eval exercises the retrieval path the Agent actually
   uses, not a stunted one.
5. As the User, I want the golden Requests and Summary hand-authored rather than
   LLM-generated, so that a retrieval miss is unambiguously a retrieval
   problem, not a Summarizer problem.
6. As the User, I want a probe that phrases a request completely differently
   from how it was originally said to still recall the right Conversation, so
   that the semantic arm is genuinely proven (US-19 of the MVP).
7. As the User, I want a probe using an exact rare term I would actually
   remember (an error code, a project codename) to recall the Conversation that
   used that exact token, even when a similar Conversation paraphrases the same
   topic, so that the keyword arm is genuinely proven (US-20 of the MVP).
8. As the User, I want distractor Conversations on adjacent topics in the
   corpus, so that recall@k measures ranking, not just "is the topic present",
   and can fail informatively.
9. As the User, I want each probe scored as recall@k at the configured
   `recall_k`, so that the number means exactly "would the Agent have had the
   right Conversation in front of it".
10. As the User, I want a stricter hit@1 number alongside, so that I can see
    ranking regressions that recall@k would hide.
11. As the User, I want recall@1 / @3 / @6 reported, so that I can see how much
    ranking headroom exists, not just a single pass/fail.
12. As the User, I want the score broken down by arm (semantic vs keyword), so
    that I can see whether each arm and RRF earn their complexity.
13. As the User, I want a per-probe table showing the rank of the expected
    Conversation (or MISS) and the top few returned ids, so that I can see
    *where* retrieval breaks, not just that it did.
14. As the User, I want a tunable recall floor stored in the dataset file, so
    that the eval is a real regression test, not just a report.
15. As the User, I want the eval to exit nonzero when the floor is breached, so
    that I (or CI later) can treat a retrieval regression as a failure.
16. As the User, I want the scorecard to always print in full even on PASS, so
    that it is a learning instrument I read, not just a green checkmark.
17. As the User, I want the active knobs (embedding model, `recall_k`,
    `rrf_k`, token ceiling) echoed in the scorecard, so that a saved run is
    self-describing when I compare trade-offs across runs.
18. As the User, I want the dataset to be one human-readable, hand-editable
    file, so that I can inspect it, tweak a probe, or grow the corpus without a
    pipeline.
19. As the User, I want a malformed dataset to fail loudly rather than silently
    skip cases, so that I never get a falsely-passing run from a typo.
20. As the User, I want the eval physically outside `uv run pytest`, so that the
    hermetic, offline test suite stays hermetic and the model download never
    leaks into it.
21. As the User, I want the pure scoring math unit-tested under pytest with a
    fake search, so that the metric logic is trustworthy even though the
    embedder-driven run is not in the suite.
22. As the User, I want the eval to make no change to production code, so that
    adding a measurement instrument cannot regress the Agent.
23. As the User, I want to ask the agent to grow the corpus later by editing
    one YAML file, so that the eval can deepen over time without re-architecting.
24. As the User, I want the floor set empirically from a first observed run, so
    that the threshold reflects reality rather than an arbitrary aspiration.
25. As a developer, I want scoring behind a small pure interface, so that the
    metric math is isolation-testable without an embedder, an LLM, or a
    database.
26. As a developer, I want the corpus built through the existing `Store` /
    `Recall` / `Unit` public interfaces only, so that the eval rides the real
    indexing path and cannot drift from production behaviour.

## Implementation Decisions

**Scope & posture** (ADR-0008): retrieval-only. The eval measures
`Recall.search` quality with the real `FastEmbedEmbedder` + sqlite-vec + FTS5 +
RRF and **no LLM at run time**. An end-to-end (real-LLM answer/agent-decision)
eval is a deliberately deferred *later additive layer*, not this work. No
production source changes — the eval is read-only over existing public
interfaces (`Store`, `Recall`, `Unit`, `Config`, `FastEmbedEmbedder`).

**Modules** (confirmed with the User):

- **loader** — shallow plumbing. `load(path) → Dataset`: parse and validate the
  committed dataset file into typed objects. Validates that every probe's
  expected Conversation id exists, every probe arm is `semantic|keyword`, floor
  values are present and in `[0,1]`, ids are unique, and (after corpus build)
  that authored ids equal the `Store`-assigned `conversation_id`. A malformed
  dataset is a hard error, never a silent skip. Not unit-tested (schema
  plumbing, not a deep module).
- **scoring** — the one **deep module**. A pure function from probes,
  expected Conversation ids, per-probe ranked id lists, and the floor → a
  Scorecard (per-probe rows, per-arm aggregates, overall recall@1/3/6, hit@1,
  and the PASS/FAIL verdict). No I/O, no embedder, no database. This is the
  Recall/Compactor analogue: simple stable interface, all metric logic behind
  it, isolation-testable.
- **runner** — thin impure glue. Builds the corpus (a temp SQLite via `Store`,
  a `Recall` over the real `FastEmbedEmbedder`), runs each probe through
  `Recall.search` (k falls through to `Config().recall_k`, exactly what the
  Agent sees), hands ranked ids to **scoring**, formats and prints the
  scorecard, sets the exit code. Not unit-tested — the project's established
  "untested adapter glue" pattern (cf. `FastEmbedEmbedder`, the Anthropic
  client).
- **entry point** — `uv run python -m evals`: load → build → run → score →
  print → exit (0 PASS, 1 FAIL or malformed dataset).

**Corpus construction** (ADR-0006, ADR-0005): per fixture Conversation, mirror
`tests/test_recall_semantic.py` but with the real embedder — start a
Conversation, append each Turn, Seal it with the golden Summary prose and
golden outcomes, then index exactly the three production Unit kinds: one
`user_turn` Unit per User Turn, one `request` Unit per golden Request, one
`summary` Unit for the golden Summary prose. Agent Turns and outcomes are not
indexed (matches `Agent._units_for`). Corpus is built in id order into a fresh
database so authored ids align with `Store`-assigned ids; the loader asserts
this invariant so a probe's expected Conversation is unambiguous.

**Dataset** (ADR-0008): one committed `dataset.yaml`. Top-level: a `floor`
block (`recall_at_k`, `hit_at_1`); a `conversations` list (each with an id, a
human topic label, ordered Turns with role+text, and a `golden` block of
`requests`, `summary` prose, `outcomes`); a `probes` list (each with the query
text, an `arm` of `semantic|keyword`, and exactly one expected Conversation
id). `pyyaml` is added to the **dev** dependency group only — never a runtime
dependency, since the Agent runtime never reads the dataset.

**Authoring contract** (ADR-0008 — the eval's honesty): ~20 Conversations
including several distractor clusters, ~35 probes. Semantic probes share zero
content words with their target's Units (only meaning connects). Keyword probes
hinge on a rare exact token the User would recall verbatim, while a distractor
discusses the same topic in paraphrase but never uses that exact token, so only
the keyword arm can disambiguate. Distractor clusters are ≥2 sibling topics so
a probe must return one specific Conversation — ranking under test, not topical
match.

**Metrics**: recall@k at the configured `recall_k` (default 6) is primary;
hit@1 is the stricter secondary; recall@1/3/6 is the curve; every metric is
also reported partitioned by probe arm. The scorecard echoes the active knobs.

**Floor procedure**: empirical. Generate the dataset, run once, set the floor a
small margin (~0.05–0.10) below the observed scores, commit it in the dataset
file, re-tune by hand as the corpus or knobs change.

## Testing Decisions

A good test asserts external behaviour through a module's interface, never
implementation internals, and is deterministic and offline (the project's
established ethos — PRD "Testing Decisions" of the MVP). The embedder-driven
eval run is itself *not* a pytest test: it needs a model download and is a
manual measurement instrument, deliberately outside `uv run pytest`
(ADR-0008), exactly as `FastEmbedEmbedder` and the Anthropic client are
untested glue.

**Module tested: scoring only** (confirmed with the User). A single hermetic
pytest test drives the pure scoring function with a fake search returning
canned ranked id lists and asserts the observable contract: recall@k and hit@1
computed correctly, the recall@1/3/6 curve correct, the per-arm partition
correct, and the PASS/FAIL verdict flips exactly at the floor. It asserts
returned metrics and verdict, never internal state or formatting wording.

Prior art: `tests/test_recall_semantic.py` and `tests/test_compactor.py` —
deterministic, fake doubles, asserting observable contracts (what `search`
returns for a known corpus; that a bound holds) rather than internals. The
scoring test follows the same shape with a fake `search`.

Not tested: `loader` (schema plumbing, not a deep module), `runner` (impure
adapter glue), the entry point. This matches the project's deep-module-only
test policy.

## Out of Scope

- Any LLM call at run time; an end-to-end (real-LLM) answer-accuracy or
  agent-decision eval — a deliberately deferred later additive layer
  (ADR-0008).
- Re-asserting the seal-gate / live-session-exclusion behaviour — already
  covered deterministically by `tests/test_recall_semantic.py`; the eval
  measures retrieval *quality*, not the gate.
- LLM-generated or frozen-snapshot corpora and any dataset-refresh pipeline
  (rejected in ADR-0008 — the dataset is a hand-authored static artifact).
- Changes to production source (`src/employee_agent/**`) — the eval is strictly
  read-only over existing public interfaces.
- Additions to `CONTEXT.md` — "probe", "distractor", "recall@k" are
  implementation/tooling vocabulary, not the Agent's domain glossary
  (ADR-0008).
- A YAML runtime dependency for the Agent — `pyyaml` is dev-group only.
- CI wiring — the eval is runnable from CI later (nonzero exit on FAIL) but
  setting that up is not this work.

## Further Notes

The real purpose is the same as the project's: learning cost-effective
operation over a growing corpus. This eval is the measurement instrument for
the retrieval half of that — it makes the recall-quality-vs-cost trade-off
*observable* when the embedding model, `rrf_k`, or `recall_k` change, which is
the single most valuable thing a retrieval eval can do here. The honesty of the
number depends entirely on the authoring contract: because one author writes
both corpus and probes, adversarial authoring (zero shared content words for
semantic probes; rare-exact-token disambiguation for keyword probes;
ranking-forcing distractor clusters) is what separates a meaningful score from
authoring symmetry. The eval is intentionally a small, legible artifact: one
YAML file, one pure scoring module, one thin runner — deepenable later (more
fixtures, then an end-to-end layer) as additive change, not a rewrite.
