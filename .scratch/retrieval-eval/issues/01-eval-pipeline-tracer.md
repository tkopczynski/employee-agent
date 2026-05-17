# 01 — Eval pipeline tracer bullet (end-to-end on a seed dataset)

Status: ready-for-agent

## Parent

PRD: `.scratch/retrieval-eval/PRD.md`
Constrained by: ADR-0008, ADR-0006, ADR-0005, ADR-0002, ADR-0001. Design
detail: `docs/spec-evals-retrieval.md`.

## What to build

The complete retrieval-quality eval pipeline, cutting through every layer on a
deliberately tiny **seed** dataset (2–3 Conversations, a handful of probes) so
the whole machine is proven before the real corpus is authored (that is
Issue 02).

End-to-end behaviour: `uv run python -m evals` loads and validates a committed
`dataset.yaml`; builds a corpus in a temporary SQLite database via the existing
`Store` / `Recall` / `Unit` public interfaces with the **real**
`FastEmbedEmbedder` (no LLM at run time), Sealing each fixture Conversation
with its hand-authored golden Summary and indexing exactly the three ADR-0006
Unit kinds (`user_turn` per User Turn, `request` per golden Request, one
`summary` for the golden Summary prose — Agent Turns and outcomes not indexed,
matching `Agent._units_for`); runs each probe through `Recall.search` with `k`
falling through to `Config().recall_k`; a pure `scoring` module turns the
per-probe ranked Conversation-id lists into a Scorecard (overall + per-arm
recall@1/3/6, hit@1, PASS/FAIL verdict against the dataset's floor); the
scorecard always prints in full with the active knobs echoed (embedding model,
`recall_k`, `rrf_k`, token ceiling); the process exits 0 on PASS, 1 on FAIL or
a malformed dataset.

`pyyaml` is added to the **dev** dependency group only (never a runtime
dependency). The corpus is built in id order into a fresh database so authored
ids equal the `Store`-assigned `conversation_id`; the loader asserts this
invariant so a probe's expected Conversation is unambiguous. No production
source change — the eval is strictly read-only over existing public interfaces.

`scoring` is the one deep module and is unit-tested hermetically under
`uv run pytest` with a fake search returning canned ranked id lists; the
embedder-driven run itself stays outside the pytest suite (ADR-0008).

## Acceptance criteria

- [ ] `uv run python -m evals` runs end-to-end on a committed seed `dataset.yaml` and prints a scorecard
- [ ] The corpus is built via `Store` / `Recall` / `Unit` with the real `FastEmbedEmbedder`; the three ADR-0006 Unit kinds are indexed; Agent Turns and outcomes are not
- [ ] No LLM is called at run time; no `src/employee_agent/**` change
- [ ] Probes are scored as recall@k at `Config().recall_k`, plus hit@1 and the recall@1/3/6 curve, partitioned per arm (`semantic`/`keyword`)
- [ ] The per-probe table shows the rank of the expected Conversation (or MISS) and the top returned ids
- [ ] The scorecard always prints in full (even on PASS) and echoes embedding model, `recall_k`, `rrf_k`, token ceiling
- [ ] A tunable floor in the dataset drives a PASS/FAIL verdict; exit code is 0 on PASS, 1 on FAIL
- [ ] A malformed dataset (bad arm, unknown expected id, missing/out-of-range floor, duplicate ids, id-invariant violation) is a hard error with nonzero exit, never a silent skip
- [ ] `pyyaml` is in the dev dependency group only, not `[project.dependencies]`
- [ ] Tests: a hermetic `tests/test_evals_scoring.py` drives the pure `scoring` module with a fake search and asserts recall@k, hit@1, the recall@1/3/6 curve, the per-arm partition, and that the verdict flips exactly at the floor; full `uv run pytest` suite stays green
- [ ] The embedder-driven eval run is outside the pytest suite

## Blocked by

None - can start immediately
