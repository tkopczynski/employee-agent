# PRD: Employee Agent — MVP

Status: ready-for-agent

> Domain vocabulary follows `CONTEXT.md`. Decisions are constrained by ADR-0001…0006. This PRD covers the band-B MVP only; band-C ("do stuff for me") is explicitly out of scope.

## Problem Statement

The User wants a single personal AI assistant they talk to in a terminal, that does not forget. Today, every chat tool either starts from zero each time or, when it does retain history, becomes slow and expensive because it drags the entire past into context. The User specifically wants to be able to ask, much later, *"when did I ask you to prepare a report on something?"* and get a precise answer — **without** the cost of loading their whole history every time. The deeper goal is to learn, hands-on, how to let an agent operate over a large and growing corpus cost-effectively.

## Solution

A TUI chat application — the **Agent** — built in Python with Textual. Each launch is one **Conversation** (a session); exiting **Seals** it. While a Conversation runs, **Compaction** keeps the live context bounded by condensing the oldest **Turns** into a running **Summary**. On Sealing, a final structured **Summary** is written and the Conversation enters **Recall** — a searchable store of all past Conversations backed by a single SQLite file (sqlite-vec for semantic search, FTS5 for keyword, RRF to fuse them). The Agent reaches into Recall through a `search_recall` tool and drills into specifics with `get_conversation`, so old history is pulled in deliberately and in bounded amounts rather than loaded wholesale. The Agent also has a small set of read-only local tools (read file, list dir, grep, web search, fetch URL, current time).

## User Stories

1. As the User, I want to launch the Agent from my terminal and immediately start chatting, so that there is no setup friction each time.
2. As the User, I want the interface to be chat-only, so that the experience stays simple and focused.
3. As the User, I want each launch to be a fresh Conversation, so that I have a clean, predictable mental model with no resume state to manage.
4. As the User, I want exiting the TUI to deterministically Seal the current Conversation, so that nothing is lost and the rule for "when is it saved" is unambiguous.
5. As the User, I want the Agent to answer general questions conversationally, so that it is useful as a day-to-day assistant.
6. As the User, I want the Agent to read a file I point it at, so that it can help me with my own work.
7. As the User, I want the Agent to list a directory, so that it can orient itself in my project.
8. As the User, I want the Agent to grep file contents, so that it can find things across my files.
9. As the User, I want the Agent to search the web, so that it is not frozen at its training cutoff.
10. As the User, I want the Agent to fetch and read a web page, so that it can act on search results.
11. As the User, I want the Agent to know the current date and time, so that it reasons correctly about "today", "last week", and recency.
12. As the User, I want read-only tools to run without confirmation prompts, so that there is no friction for zero-risk actions.
13. As the User, I want the Agent to never make changes to my machine in this version, so that I can trust it is safe by construction.
14. As the User, I want a long Conversation to stay responsive and not balloon in cost, so that I can keep chatting without watching a meter.
15. As the User, I want the Agent to retain the gist of earlier parts of a long Conversation after Compaction, so that it does not develop amnesia mid-session.
16. As the User, I want the live context budget to be bounded regardless of how long I chat, so that cost stays predictable.
17. As the User, I want to be able to observe how much hot context is in use and when Compaction fires, so that I can learn how the cost bound actually behaves.
18. As the User, I want to ask "when did I ask you to prepare a report on X" weeks later and get a date and what it was about, so that the Agent's memory is actually useful.
19. As the User, I want recall to find a past request even when I phrase it differently than I originally did, so that I do not have to remember my exact words.
20. As the User, I want recall to also find things by exact terms I do remember (a project name, an error string), so that precise lookups are not lost to fuzzy matching.
21. As the User, I want the Agent to pull only a bounded amount of past history into context when it recalls, so that recall does not reintroduce the cost problem it solves.
22. As the User, I want the Agent to be able to drill into the full transcript of a specific past Conversation when it needs detail, so that bounded recall does not mean lossy recall.
23. As the User, I want the Agent to decide on its own when recall is relevant, so that I can just ask naturally instead of issuing commands.
24. As the User, I want recall to search only my finished past sessions, so that behaviour is predictable and the current session does not confusingly match itself.
25. As the User, I want each Sealed Conversation to have a readable Summary, so that browsing my history (by asking the Agent) is meaningful.
26. As the User, I want the Summary to explicitly capture what I asked the Agent to do, so that request-shaped questions like "when did I ask…" land reliably.
27. As the User, I want all my data in a single inspectable SQLite file, so that I can open it and look at my own data and back it up by copying one file.
28. As the User, I want the whole thing to run as one process with no Docker, so that the project stays simple to run while learning.
29. As the User, I want the model used for the chat loop to be configurable, so that I can trade cost vs quality.
30. As the User, I want summarisation to use a cheaper model than the chat loop by default, so that a high-frequency operation does not dominate cost.
31. As the User, I want the per-task model mapping to be configurable, so that I can measure the recall-quality-vs-cost trade-off of cheap summaries myself.
32. As the User, I want embeddings generated locally, so that my memory does not depend on a second vendor and works offline.
33. As the User, I want the Agent to distinguish recalled past Conversations from the current one in how it phrases answers, so that it never says "in a past conversation" about something from this session.
34. As the User, I want the Agent's read-only tools to be safe even if it misbehaves, so that the worst case is a wasted call, not damage.
35. As a developer, I want Recall behind a small interface, so that the storage/search complexity is encapsulated and isolation-testable.
36. As a developer, I want Compaction behind a small interface, so that the cost-bounding logic can be tested deterministically.
37. As a developer, I want Summarisation behind a small interface, so that the structured-Summary contract can be tested without asserting on LLM wording.
38. As a developer, I want the LLM and Embedder access behind thin interfaces, so that they can be faked in tests and swapped later.
39. As a developer, I want an end-to-end test of the Agent loop with faked adapters, so that wiring bugs between modules are caught.

## Implementation Decisions

**Stack & topology** (ADR-0001): Python 3 + Textual TUI. Single process, no Docker. One SQLite database file is the only datastore, using the `sqlite-vec` extension and built-in FTS5.

**LLM** (Q10, Q19): Anthropic Claude behind a thin `LLMClient` interface. Per-task model configuration (a map, not a scalar), default `{ agent_loop: claude-sonnet-4-6, summarise: claude-haiku-4-5 }`. Model names live in config, never hardcoded.

**Embeddings** (ADR-0002): local via `fastembed` (`bge-small-en-v1.5`, 384-dim) behind an `Embedder` interface. No hosted embedding provider. Consequence: changing the embedding model is a full Recall re-index, not a config tweak.

**Conversation lifecycle** (ADR-0005): a Conversation is exactly one session. Starts on launch, Sealed deterministically on exit. No resume, no `/new`.

**Compaction** (ADR-0003, Q17): rolling compaction within a live session. Trigger when hot context exceeds a configurable fraction (~50%) of the active model's context window. Keep a configurable verbatim tail (~4k tokens). The running Summary has its own token cap and is regenerated to fit (lossy by design, transient). **Every growing thing is capped — the Turn tail and the running Summary** — otherwise the bound leaks.

**Recall scope & indexing** (ADR-0003, ADR-0004 partially superseded by ADR-0005): Compaction writes compacted Turns into Recall *storage* incrementally during a session (amortised embedding cost), but they are not *searchable* until the Conversation is Sealed. `search_recall` is scoped to Sealed Conversations only. Consequence: the current-vs-past hit provenance problem does not exist — `search_recall` can never return a current-Conversation hit.

**Summary format** (ADR-0006): a Summary is a short prose recap **plus** structured `Requests` and `Outcomes` lists. Each `Requests` item is embedded as its own Recall unit alongside raw User Turns (deliberate, beneficial redundancy). Consequence: the Summary format is sticky — changing it is a full-corpus re-summarisation.

**Recall retrieval** (Q12, Q20): hybrid search — sqlite-vec semantic + FTS5 keyword, fused with Reciprocal Rank Fusion (k≈60, no score normalisation/weight tuning). `search_recall(query, k)` returns top-K Conversation hits (default K≈6), each `{date, summary line, best-matching snippet, conversation_id}`, under a hard token ceiling (~1.5–2k); when over budget, return fewer *complete* hits rather than more truncated ones. `get_conversation(id)` is a separate drill-in tool returning the full ordered transcript. K and the ceiling are config.

**Tool surface** (Q9): read-only only, no confirmations — `read_file`, `list_dir`, `grep`, `web_search`, `fetch_url`, `current_time`, plus `search_recall` and `get_conversation`. No `shell` tool.

**Recall access pattern** (Q8): agent-pulled. The Agent has `search_recall`/`get_conversation` as tools and decides when to use them; no automatic per-Turn RAG injection.

**Module interfaces** (deep modules, simple stable interfaces):
- **Recall**: `add_units(units)`, `seal(conversation_id)`, `search(query, k) → Hits`, `get_conversation(id) → Turns`. Encapsulates SQLite, sqlite-vec, FTS5, RRF, and the seal-gate. Callers never see vectors or SQL.
- **Compactor**: `observe(turn)`, `hot_context() → messages`. Encapsulates token budgeting, the compaction trigger, the verbatim-tail and running-Summary caps, and handing cold Turns to Recall.
- **Summarizer**: `summarize(turns) → Summary{prose, requests[], outcomes[]}`. Used for both running and final Summaries.
- **Embedder**: `embed(texts) → vectors`. **LLMClient**: `complete(messages, tools, model) → Response`. Thin, fakeable.
- **Agent loop**: orchestrates input → context assembly (Compactor hot context + system prompt + tools) → LLM → tool execution → reply. **TUI**: Textual presentation over the loop.

**Schema** (single SQLite file):
- `conversations(id, started_at, sealed_at NULLABLE, summary_prose NULLABLE, summary_outcomes JSON NULLABLE)` — `sealed_at` is the searchability gate.
- `turns(id, conversation_id, seq, role, content, created_at, compacted)` — verbatim transcript, both roles; only User Turns are indexed.
- `search_units(id, conversation_id, kind ['user_turn'|'request'|'summary'], source_turn_id NULLABLE, text, created_at)` — the indexed corpus (≠ the set of Turns).
- `vec_search_units` — sqlite-vec virtual table, `rowid = search_units.id`, `float[384]`.
- `fts_search_units` — FTS5 virtual table mirroring `search_units.text`, keyed by `search_units.id`.
- Seal-gate enforced by joining `search_units → conversations` and filtering `sealed_at IS NOT NULL`.
- Timestamps stored as ISO-8601 TEXT (keeps the single file human-inspectable, consistent with ADR-0001).

**Deliberately not stored**: running Compaction Summaries (transient in-process; no resume ⇒ no recovery need), API keys / model config (environment/config file), assembled hot context (computed per Turn at runtime).

## Testing Decisions

A good test asserts **external behaviour through the module's interface**, not internal implementation. Tests must not assert on LLM wording, exact embeddings, or private state — they assert on observable contracts (what `search` returns given a known corpus, that hot context stays under budget, that a Summary has the required structure). Embedder and LLMClient are replaced with fakes so tests are deterministic and offline.

Modules to be tested (confirmed with the User): **Recall, Compactor, Summarizer, and the Agent loop (integration).**

- **Recall** — against a temporary SQLite file with a real `sqlite-vec`/FTS5 and a *fake deterministic Embedder*. Assert: the seal-gate (units from an unsealed Conversation never appear in `search`; appear after `seal`); hybrid retrieval finds a paraphrased match (semantic) and an exact-token match (keyword); RRF ordering rewards "good in both"; `get_conversation` returns the full ordered transcript; result budget caps are honoured (fewer complete hits over truncated ones).
- **Compactor** — with injected fake token counts and a fake Summarizer. Assert: hot context never exceeds the configured fraction of the window across a long synthetic Turn stream; the verbatim tail is preserved; the running Summary stays under its own cap (the "summary is the leak" failure mode); cold Turns are handed to Recall storage exactly once.
- **Summarizer** — with a fake LLMClient returning canned structured output. Assert the *contract*: a Summary always has prose, a (possibly empty) `requests` list, and an `outcomes` list; request items are extracted as discrete normalised entries. Do not assert on phrasing.
- **Agent loop (integration)** — end-to-end with all adapters faked: a scripted user input that should trigger `search_recall` results in the tool being called and a reply that distinguishes a recalled *past* Conversation from the current session; a read-only tool request routes to the right tool; Sealing on exit writes the final Summary and flips searchability.

Prior art: none — the repo is greenfield. Establish `pytest` as the test runner; these tests become the prior art for later work.

## Out of Scope

- **Band-C capabilities** ("do stuff for me"): writes, side effects, arbitrary shell, multi-step actuation, and any tool-confirmation/trust model. Architecture must not foreclose them, but they are not built here.
- **Conversation resume** across sessions, a resume picker, lazy-seal-after-inactivity, `/new` (explicitly reversed in ADR-0005).
- **Searching the live session's own cold tail** via `search_recall` (ADR-0005); within-session recall rides on hot context only.
- **Multi-user / multi-tenant**, auth, sharing, sync.
- **Production deployment**, packaging for distribution, observability/monitoring stacks, scaling beyond a single user's tens-of-thousands of Turns.
- **A separate history-browser UI**: browsing past Conversations is done by asking the Agent, not a dedicated screen (interface is chat-only).
- **Provider abstraction layer** (e.g. LiteLLM): only the thin internal `LLMClient` interface, not a multi-provider framework.
- **Deduplicating** the running-Summary vs raw-Turn overlap (accepted as harmless redundancy).

## Further Notes

The real purpose of this project is **learning cost-effective operation over a growing corpus inside an agent**, not memory as a feature (see project memory `learning-goal-big-data-cost`). Implementation should therefore make token cost **bounded and observable**: log hot-token counts before/after each Compaction, the size of every `search_recall` result, and per-task model usage, so the cost bound can be watched holding (User story 17). The single most valuable learning artifact is the configurable per-task model map (Q19) — it lets the recall-quality-vs-cost trade-off of cheap summaries be measured empirically; favour designs that keep that measurable.

ADR-0003's "one mechanism at three time-scales" is the architectural spine: Compaction condenses + indexes incrementally, Sealing finalises + flips searchability, Recall searches. Keep these as one coherent subsystem rather than three features, so the band-C-era evolution (making the live session's cold tail searchable) remains a later additive change, not a rewrite.
