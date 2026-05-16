# 03 — run_command end-to-end via a fake Sandbox

Status: ready-for-agent

## Parent

PRD: `.scratch/band-c-workspace/PRD.md`

## What to build

The Agent gains a `run_command` tool that executes a command in the **Workspace** through a new thin `Sandbox` interface. This slice delivers the entire agent-loop path using a **fake `Sandbox`** (no Docker yet) — the same fake-adapter pattern as the existing `LLMClient` / `WebClient` / `Embedder` seams, so the loop wiring is provable without the Docker dependency.

The `Sandbox` interface is `run(command, timeout) → ExecResult{ stdout, stderr, exit_code, timed_out }`. `run_command` is wired into the tool loop, runs with **no confirmation prompt** (containment is the trust model, ADR-0007), and its wall-clock duration and exit status are logged — execution is a cost surface, consistent with the project's cost-observability discipline.

End-to-end demo via the fake: the User asks the Agent to write a script and run it; the Agent calls `write_file` then `run_command` and the output appears in the reply.

## Acceptance criteria

- [ ] A `Sandbox` interface exists: `run(command, timeout) → ExecResult{ stdout, stderr, exit_code, timed_out }`
- [ ] A fake `Sandbox` implementation exists for tests — deterministic, no Docker
- [ ] A `run_command` tool delegates to `Sandbox.run` and is invocable by the Agent within a Turn
- [ ] `run_command` runs with no confirmation prompt
- [ ] Executed-command wall-clock duration and exit status are logged
- [ ] Tests: agent-loop integration with the fake `Sandbox` — a scripted "write a script then run it" routes `write_file` → `run_command` and the result is incorporated into the reply

## Blocked by

- 02 — write_file into the Workspace
