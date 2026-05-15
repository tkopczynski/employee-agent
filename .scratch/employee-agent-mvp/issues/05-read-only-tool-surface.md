# 05 — Read-only tool surface

Status: ready-for-human

## Parent

PRD: `.scratch/employee-agent-mvp/PRD.md`

## What to build

The Agent gains its band-B read-only local tool surface, wired into the loop with no confirmation prompts: `read_file`, `list_dir`, `grep`, `web_search`, `fetch_url`, `current_time`. The Agent decides when to call them (agent-pulled). No `shell` tool; nothing performs writes or side effects on the machine. Independent of Recall — runs in parallel off the chat spine.

## Acceptance criteria

- [x] All six tools are registered and invocable by the Agent within a Turn
- [x] Asking about a local file causes a `read_file` call and an answer grounded in its contents
- [x] A web-information question causes `web_search`, and following a result causes `fetch_url`
- [x] `current_time` is available so the Agent reasons correctly about recency
- [x] No tool performs writes or side effects; no confirmation prompts are shown (read-only ⇒ zero risk)
- [x] No `shell` tool exists
- [x] Tests: **Agent-loop integration** — a scripted request routes to the correct tool and its result is incorporated into the reply

## Comments

Implemented via TDD (`/tdd`). Six read-only tools added to the existing
agent tool loop in a new `src/employee_agent/tools.py` (`ReadOnlyTools`),
delegated to from `Agent._run_tool`; web tools go through a new thin
`WebClient` seam (`src/employee_agent/web.py`) — faked offline in tests,
real adapter uses the Anthropic server-side `web_search` tool + stdlib
`urllib` for `fetch_url` (no new deps). `read_file` is capped by a module
constant (cost-bound, consistent with the project's learning goal).
Integration tests in `tests/test_agent_read_only_tools.py` (6 tests, one
per vertical slice). Full suite green (35 tests). No `shell` tool.

## Blocked by

- 01 — Chat spine
