# 03 — Keyword Recall, end-to-end

Status: ready-for-agent

## Parent

PRD: `.scratch/employee-agent-mvp/PRD.md`

## What to build

Recall becomes searchable by exact terms, end-to-end. On Sealing, indexed units (User Turns, extracted Requests, the Summary) are written to `search_units` and an FTS5 keyword index; the seal-gate guarantees only Sealed Conversations are searchable. The Agent gets two tools wired into its loop: `search_recall(query, k)` returning bounded Conversation hits (`{date, summary line, snippet, conversation_id}`) and `get_conversation(id)` returning the full ordered transcript. The Agent decides when to call them (agent-pulled, Q8). Because `search_recall` is scoped to Sealed Conversations (ADR-0005), every hit is a past session and the Agent phrases it as past — never confusing it with the current session.

## Acceptance criteria

- [ ] On Seal, User Turns + Request items + the Summary are indexed into `search_units` + FTS5
- [ ] Units from an unsealed Conversation never appear in `search_recall`; they appear only after Seal (seal-gate)
- [ ] `search_recall` returns ranked Conversation hits with date + summary line + best snippet, honouring the result budget (fewer complete hits over more truncated ones)
- [ ] `get_conversation(id)` returns the full ordered transcript including both roles
- [ ] In a fresh launch, asking about an exact term from a prior Sealed Conversation makes the Agent call `search_recall` and answer with the date
- [ ] The Agent's phrasing distinguishes a recalled past Conversation from the current session
- [ ] Tests: **Recall** (seal-gate, keyword retrieval, `get_conversation`, budget cap) with a deterministic fake Embedder placeholder; **Agent-loop integration** (recall-shaped query triggers the tool; past-vs-current phrasing)

## Blocked by

- 02 — Sealing + structured Summary
