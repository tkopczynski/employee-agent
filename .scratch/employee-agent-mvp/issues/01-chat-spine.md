# 01 — Chat spine

Status: ready-for-agent

## Parent

PRD: `.scratch/employee-agent-mvp/PRD.md`

## What to build

A Textual TUI where the User chats with the Agent end-to-end. User input is sent to Claude through a thin `LLMClient` interface; the reply renders in a chat-only view. Each launch opens a new Conversation; every Turn (User and Agent) is persisted to the single SQLite file. A per-task model map exists in config (default `{ agent_loop: claude-sonnet-4-6, summarise: claude-haiku-4-5 }`) and the agent-loop model is resolved from it. No tools, no Compaction, no Recall yet — this is the spine everything else hangs off.

## Acceptance criteria

- [ ] Launching the app creates a `conversations` row and presents a chat-only TUI
- [ ] Sending a message returns a Claude-generated reply rendered in the TUI
- [ ] Each User and Agent Turn is written to `turns` with order preserved
- [ ] The agent-loop model is read from a configurable per-task model map, never hardcoded
- [ ] `LLMClient` is a thin interface with a deterministic fake usable in tests
- [ ] Tests: a faked `LLMClient` drives a scripted exchange; Conversation/Turn persistence is asserted as external behaviour (not wording)
- [ ] Runs as a single process, no Docker; all data in one inspectable SQLite file with ISO-8601 timestamps (ADR-0001)

## Blocked by

None - can start immediately
