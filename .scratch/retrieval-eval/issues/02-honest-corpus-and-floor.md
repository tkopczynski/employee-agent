# 02 — Honest corpus + empirical floor

Status: ready-for-agent

## Parent

PRD: `.scratch/retrieval-eval/PRD.md`
Constrained by: ADR-0008 (the dataset authoring contract). Design detail:
`docs/spec-evals-retrieval.md`.

## What to build

Replace the seed `dataset.yaml` from Issue 01 with the full, discriminating
corpus authored to the ADR-0008 honesty contract, then calibrate the
regression floor from a real observed run. The pipeline already works (Issue
01); this slice delivers the corpus that makes the score *mean* something and a
floor grounded in reality.

Author ~20 fixture Conversations including several distractor clusters, and
~35 probes tagged `semantic` or `keyword`. The authoring contract:

- **Semantic probes** share zero content words with their target Conversation's
  Units — only meaning connects, so the semantic arm is genuinely exercised
  (US-19 of the MVP).
- **Keyword probes** hinge on a rare exact token the User would recall verbatim
  (an error code, a project codename), while a distractor Conversation
  discusses the same topic in paraphrase but never uses that exact token, so
  only the keyword arm can disambiguate (US-20 of the MVP).
- **Distractor clusters** are ≥2 sibling topics so a probe must return one
  specific Conversation — ranking under test, not mere topical match.

Each Conversation keeps the production-faithful shape: ordered Turns plus a
hand-authored golden `requests` list and `summary` prose (the ideal Summarizer
output, pinned by hand so a miss is unambiguously a retrieval problem).

Then run the eval once, observe overall `recall@k` and `hit@1`, and commit the
floor a small margin (~0.05–0.10) below the observed values in `dataset.yaml`,
so the run PASSes and the floor reflects reality rather than an arbitrary
aspiration.

## Acceptance criteria

- [ ] `dataset.yaml` contains ~20 Conversations including several distractor clusters and ~35 probes, each probe tagged `semantic` or `keyword`
- [ ] Every semantic probe shares zero content words with its target Conversation's Units
- [ ] At least one keyword cluster: a probe's rare exact token appears verbatim only in its target, while a distractor paraphrases the same topic without that token
- [ ] At least one distractor cluster of ≥2 sibling topics where a probe must resolve to one specific Conversation
- [ ] Every Conversation has hand-authored golden `requests` and `summary` prose; ids satisfy the loader's id-invariant
- [ ] The scorecard shows a meaningful per-arm (semantic vs keyword) breakdown over the discriminating corpus
- [ ] The empirical floor (`recall_at_k`, `hit_at_1`) is committed in `dataset.yaml`, set ~0.05–0.10 below the observed first-run scores, and the run PASSes
- [ ] No production source change; the scoring test and full `uv run pytest` suite stay green

## Blocked by

- Issue 01 (`.scratch/retrieval-eval/issues/01-eval-pipeline-tracer.md`) — the pipeline, loader, scoring, and dataset schema must exist before the full corpus and empirical floor can be authored and calibrated
