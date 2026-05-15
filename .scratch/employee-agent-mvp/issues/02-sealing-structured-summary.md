# 02 — Sealing + structured Summary

Status: ready-for-agent

## Parent

PRD: `.scratch/employee-agent-mvp/PRD.md`

## What to build

On exiting the TUI, the current Conversation is **Sealed**: the **Summarizer** condenses its Turns into a structured **Summary** — a short prose recap plus explicit `Requests` and `Outcomes` lists (ADR-0006) — `sealed_at` is set, and the prose + outcomes are persisted on the Conversation. Summarisation uses the cheaper model resolved from the per-task model map (Q19), distinct from the agent-loop model. This gives every finished session a durable, structured Summary — the first half of Recall's value.

## Acceptance criteria

- [ ] Exiting the TUI deterministically Seals the current Conversation (sets `sealed_at`)
- [ ] A structured Summary is produced and persisted: prose recap, a (possibly empty) Requests list, an Outcomes list
- [ ] Summarisation uses the `summarise` entry of the per-task model map, not the agent-loop model
- [ ] `Summarizer` is a deep module with a `summarize(turns) -> Summary` interface, used for both running and final Summaries
- [ ] Tests: Summarizer contract with a faked `LLMClient` — asserts Summary structure (prose present; requests/outcomes are lists; requests are discrete, normalised entries); does not assert phrasing
- [ ] Opening the SQLite file shows a readable Summary row for a Sealed Conversation

## Blocked by

- 01 — Chat spine
