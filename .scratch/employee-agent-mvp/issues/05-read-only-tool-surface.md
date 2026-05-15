# 05 — Read-only tool surface

Status: ready-for-agent

## Parent

PRD: `.scratch/employee-agent-mvp/PRD.md`

## What to build

The Agent gains its band-B read-only local tool surface, wired into the loop with no confirmation prompts: `read_file`, `list_dir`, `grep`, `web_search`, `fetch_url`, `current_time`. The Agent decides when to call them (agent-pulled). No `shell` tool; nothing performs writes or side effects on the machine. Independent of Recall — runs in parallel off the chat spine.

## Acceptance criteria

- [ ] All six tools are registered and invocable by the Agent within a Turn
- [ ] Asking about a local file causes a `read_file` call and an answer grounded in its contents
- [ ] A web-information question causes `web_search`, and following a result causes `fetch_url`
- [ ] `current_time` is available so the Agent reasons correctly about recency
- [ ] No tool performs writes or side effects; no confirmation prompts are shown (read-only ⇒ zero risk)
- [ ] No `shell` tool exists
- [ ] Tests: **Agent-loop integration** — a scripted request routes to the correct tool and its result is incorporated into the reply

## Blocked by

- 01 — Chat spine
