# 02 — write_file into the Workspace

Status: ready-for-agent

## Parent

PRD: `.scratch/band-c-workspace/PRD.md`

## What to build

The Agent gains the ability to write a file into the **Workspace**. A new `write_file` tool creates or overwrites a file at a Workspace-relative path, routed through the same `Workspace` airlock as the read tools (escapes refused identically). Writing runs with **no confirmation prompt** — containment is the trust model (ADR-0007).

Because the tool surface is no longer read-only, the tool class is renamed off its "read-only" name and its module rationale comment is rewritten from "read-only ⇒ zero risk" to the containment rationale from ADR-0007, so the code no longer claims a guarantee it no longer provides.

End-to-end: the User asks the Agent to save something, and the file appears in the Workspace.

## Acceptance criteria

- [ ] A `write_file` tool writes a file at a Workspace-relative path; the file appears in the Workspace
- [ ] Write paths go through the same airlock; an escaping write path is refused exactly like the read tools
- [ ] Writing runs with no confirmation prompt
- [ ] The tool class is renamed off "read-only" and the module rationale comment reflects the containment rationale (ADR-0007), not "read-only ⇒ zero risk"
- [ ] No SQLite schema change
- [ ] Tests: agent-loop integration — a scripted request to save a file routes to `write_file` and the file is created in the Workspace; an escaping write is refused

## Blocked by

- 01 — Confine the Agent's filesystem reads to the Workspace
