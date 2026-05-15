# 04 — Semantic Recall + RRF

Status: ready-for-agent

## Parent

PRD: `.scratch/employee-agent-mvp/PRD.md`

## What to build

Add semantic retrieval and fuse it with the existing keyword index. The **Embedder** (fastembed `bge-small-en-v1.5`, 384-dim, ADR-0002) embeds the same `search_units` into a sqlite-vec index. `search_recall` now runs both the sqlite-vec semantic query and the FTS5 keyword query and fuses their **rankings** with Reciprocal Rank Fusion (k≈60, no score normalisation or weight tuning), then applies the K / token-ceiling budget. The headline paraphrase query now lands: "prepare a report" finds a Conversation that said "draft a one-pager".

## Acceptance criteria

- [ ] Each indexed unit is embedded locally via the `Embedder` interface into a sqlite-vec index; no hosted embedding provider; works offline
- [ ] `search_recall` fuses sqlite-vec and FTS5 results via RRF; ordering rewards "good in both lists" over "good in one"
- [ ] A paraphrased query retrieves a Conversation that used different wording (semantic match)
- [ ] An exact-token query still retrieves its keyword match (no regression from 03)
- [ ] The result budget (top-K, token ceiling) is honoured after fusion
- [ ] Tests: **Recall** hybrid retrieval + RRF ordering with a deterministic fake Embedder (assert ordering/recall behaviour, not raw vectors)

## Blocked by

- 03 — Keyword Recall, end-to-end
