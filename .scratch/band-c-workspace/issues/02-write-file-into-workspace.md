# 02 — write_file into the Workspace

Status: ready-for-human

## Parent

PRD: `.scratch/band-c-workspace/PRD.md`

## What to build

The Agent gains the ability to write a file into the **Workspace**. A new `write_file` tool creates or overwrites a file at a Workspace-relative path, routed through the same `Workspace` airlock as the read tools (escapes refused identically). Writing runs with **no confirmation prompt** — containment is the trust model (ADR-0007).

Because the tool surface is no longer read-only, the tool class is renamed off its "read-only" name and its module rationale comment is rewritten from "read-only ⇒ zero risk" to the containment rationale from ADR-0007, so the code no longer claims a guarantee it no longer provides.

End-to-end: the User asks the Agent to save something, and the file appears in the Workspace.

## Acceptance criteria

- [x] A `write_file` tool writes a file at a Workspace-relative path; the file appears in the Workspace
- [x] Write paths go through the same airlock; an escaping write path is refused exactly like the read tools
- [x] Writing runs with no confirmation prompt
- [x] The tool class is renamed off "read-only" and the module rationale comment reflects the containment rationale (ADR-0007), not "read-only ⇒ zero risk"
- [x] No SQLite schema change
- [x] Tests: agent-loop integration — a scripted request to save a file routes to `write_file` and the file is created in the Workspace; an escaping write is refused

## Blocked by

- 01 — Confine the Agent's filesystem reads to the Workspace

## Comments

**2026-05-16 — implemented (TDD).** `write_file` added to the local tool
surface: resolves the path through the existing `Workspace` airlock (same
confinement point as the reads — PRD US-27), auto-creates missing parent dirs
under the Workspace, then writes UTF-8. Runs prompt-free via the existing
agent loop (containment is the trust model, ADR-0007). Escaping-write refusal
fell out for free because writes route through the same `Workspace.resolve` +
`LocalTools.run` try/except as the reads.

`ReadOnlyTools` renamed to `LocalTools` (`tools.py`, `agent.py`); the module
docstring and the in-`run` rationale comment rewritten from "read-only ⇒ zero
risk" to the ADR-0007 containment rationale, so the code no longer claims a
guarantee it no longer provides. No `store.py` touch — no schema change.

Tests (vertical slices, one RED→GREEN each) in
`tests/test_agent_read_only_tools.py`: save-request → `write_file` → file in
Workspace; nested path auto-mkdir; escaping write refused + relayed + nothing
written outside + Turn persists. The read-only-era
"no write-shaped tool" assertion was retired to the post-issue-02 contract
(write present; still no `shell`/`run_command`/`exec` — execution is a later
issue). Full suite: 52 passed. Test filename kept (rename not in scope);
its docstring updated so it doesn't lie.
