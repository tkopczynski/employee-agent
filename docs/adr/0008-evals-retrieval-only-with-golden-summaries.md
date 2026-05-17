# Evals are retrieval-only, over hand-authored golden Summaries, outside the hermetic suite

Status: accepted

The accuracy eval measures **only `Recall.search` quality** — the real `FastEmbedEmbedder` + sqlite-vec + FTS5 + RRF over a known corpus — with **no LLM call at run time**. Each fixture Conversation is indexed exactly like production (the three ADR-0006 unit kinds: `user_turn`, `request`, `summary`), but the `request`/`summary` units are **hand-authored "golden" Summarizer output**, not generated. This isolates the retriever from Summarizer noise, keeps the eval deterministic and free, and makes the retrieval-quality-vs-cost knob (the project's stated learning goal) directly measurable when the embedding model / `rrf_k` / `recall_k` are swapped. The eval is a standalone `evals/` script (`uv run python -m evals`), deliberately outside `uv run pytest` because the real embedder is barred from the hermetic suite (model download, offline-by-construction test idiom).

## Considered options (rejected)

- **End-to-end eval (real LLM answers the User)** — measures the user-facing thing but is non-deterministic, costs money per run, needs LLM-as-judge grading, and conflates retrieval failure with reasoning failure. Deferred as a *later additive layer* on top of this one, not the starting point.
- **LLM-generated or frozen-snapshot corpus** — more production-faithful Summaries, but adds a refresh pipeline that costs API calls and silently mutates the dataset under the floor. A hand-authored static YAML is inspectable and stable; growing it is a deliberate edit.
- **Raw user-turns-only corpus** — simplest, but never exercises the `request`/`summary` units that ADR-0006 exists to make "when did I ask…" queries land. It would measure a retriever the real Agent never uses.
- **Marked pytest test (`-m eval`)** — stays in the pytest idiom but yields a poor scorecard and risks the real embedder leaking into the default suite. A script that prints a per-arm table is the better learning instrument.

## Consequences

- **The eval is only as honest as its authoring contract.** Because the same author writes corpus and probes, the dataset *must* be adversarial: semantic probes share zero content words with their target; keyword probes hinge on a rare exact token a distractor paraphrases but never uses verbatim; distractor clusters force ranking, not topical match. Without this the score is authoring symmetry, not retrieval quality.
- **The regression floor is empirical, not aspirational** — set a margin below the first observed score, stored in the dataset YAML, tunable as the corpus grows.
- The eval’s value depends on `FastEmbedEmbedder` being deterministic across runs (pinned model, CPU inference); first run downloads the model, thereafter offline and stable.
- Eval/tooling vocabulary ("probe", "distractor", "recall@k") is **not** added to `CONTEXT.md` — it is implementation language, not the Agent's domain glossary.
