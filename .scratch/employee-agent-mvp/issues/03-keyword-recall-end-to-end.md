# 03 — Keyword Recall, end-to-end

Status: ready-for-human

## Parent

PRD: `.scratch/employee-agent-mvp/PRD.md`

## What to build

Recall becomes searchable by exact terms, end-to-end. On Sealing, indexed units (User Turns, extracted Requests, the Summary) are written to `search_units` and an FTS5 keyword index; the seal-gate guarantees only Sealed Conversations are searchable. The Agent gets two tools wired into its loop: `search_recall(query, k)` returning bounded Conversation hits (`{date, summary line, snippet, conversation_id}`) and `get_conversation(id)` returning the full ordered transcript. The Agent decides when to call them (agent-pulled, Q8). Because `search_recall` is scoped to Sealed Conversations (ADR-0005), every hit is a past session and the Agent phrases it as past — never confusing it with the current session.

## Acceptance criteria

- [x] On Seal, User Turns + Request items + the Summary are indexed into `search_units` + FTS5
- [x] Units from an unsealed Conversation never appear in `search_recall`; they appear only after Seal (seal-gate)
- [x] `search_recall` returns ranked Conversation hits with date + summary line + best snippet — **K cap only** this issue; the result-budget *ceiling* ("fewer complete hits over more truncated ones") is deferred (see Comments)
- [x] `get_conversation(id)` returns the full ordered transcript including both roles
- [x] In a fresh launch, asking about an exact term from a prior Sealed Conversation makes the Agent call `search_recall` and answer with the date (deterministic contract: the tool result is seal-scoped, dated and past-framed; model phrasing not asserted, per PRD Testing Decisions)
- [x] The Agent's phrasing distinguishes a recalled past Conversation from the current session (guaranteed structurally: `search_recall` is seal-scoped per ADR-0005 and the tool result/description frame every hit as a past session)
- [x] Tests: **Recall** (seal-gate, keyword retrieval, `get_conversation`) with a deterministic fake Embedder placeholder; **Agent-loop integration** (recall-shaped query triggers the tool; past-vs-current framing). **`budget cap` test deferred** (see Comments)

## Comments

**2026-05-15 — implemented via TDD (8 red→green cycles).**

Delivered: `Recall` deep module (`src/employee_agent/recall.py`) over the
single SQLite file (ADR-0001) with `search_units` + an FTS5 keyword index;
the seal-gate is a live join on `conversations.sealed_at` (so Issue 06's
incremental indexing stays additive). The thin `Embedder` seam
(`src/employee_agent/embedder.py`, `FastEmbedEmbedder` glue + `FakeEmbedder`)
is wired but dormant — keyword recall does not embed. The agent loop gained a
general agentic tool-use spine: `LLMClient.complete(messages, model, *,
tools=None) → Response{text, tool_calls}`; `Agent.send` runs an iterative
tool loop registering `search_recall` + `get_conversation` (Issue 05 adds
more tools to the same surface — additive). `Agent.seal` now indexes User
Turns + extracted Requests + the Summary into Recall (Agent Turns excluded).

Tests: `tests/test_recall.py` (6), `tests/test_agent_tools.py` (1),
`tests/test_recall_integration.py` (3); full suite 23 green.

**Scope decision (User, before implementation): result budget = K-only.**
`search_recall(query, k)` returns at most K hits (default 6). The result-size
*ceiling* and the "drop whole hits over truncated ones" behaviour — and the
associated **budget-cap test** — are **deferred to a later issue**.
Acceptance criterion #3's budget clause is therefore only partially met by
design, not by omission.

**Design note:** the PRD lists `Recall.seal(conversation_id)`. It was
**deliberately omitted** — with the live seal-gate join it would be a
redundant no-op, and the join-based gate is exactly what ADR-0005 describes
and what keeps Issue 06 additive. Sealing is orchestrated by `Agent.seal`
(`Store.seal_conversation` flips `sealed_at`; `Recall.add_units` indexes).

## Blocked by

- 02 — Sealing + structured Summary
