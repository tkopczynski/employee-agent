# 06 — Compaction + cost observability

Status: ready-for-agent

## Parent

PRD: `.scratch/employee-agent-mvp/PRD.md`

## What to build

The **Compactor** bounds the live Conversation's hot context (ADR-0003, Q17). When hot context exceeds a configurable fraction (~50%) of the active model's context window, the oldest Turns are condensed into a running Summary kept under its own token cap, a configurable verbatim tail (~4k tokens) is retained, and the compacted raw Turns are written incrementally into Recall storage — seal-gated, so searchable only once the Conversation is Sealed (ADR-0004/0005). Structured logging exposes hot-token counts before/after each Compaction, `search_recall` result sizes, and per-task model usage, so the cost bound can be observed holding (the project's core learning payoff — see project memory `learning-goal-big-data-cost`).

**HITL:** a human tunes the trigger fraction / tail constants against the real model and confirms the bound holds before sign-off.

## Acceptance criteria

- [ ] Hot context never exceeds the configured fraction of the active model's context window across a long Turn stream
- [ ] The verbatim tail is preserved up to its configured token budget
- [ ] The running Summary is regenerated to fit its own token cap and does not grow unbounded (the "summary is the leak" failure mode is prevented)
- [ ] Compacted Turns are written into Recall storage exactly once and stay unsearchable until the Conversation is Sealed
- [ ] Structured logs record hot-token counts pre/post Compaction, `search_recall` result sizes, and per-task model usage
- [ ] HITL sign-off: a human has reviewed the trigger fraction and tail constants against the real model and confirmed the cost bound holds
- [ ] Tests: **Compactor** (bound holds across a synthetic long session; running-Summary cap enforced; cold Turns handed to Recall exactly once); final end-to-end (long session stays bounded, then Seals and becomes recallable)

## Blocked by

- 04 — Semantic Recall + RRF
