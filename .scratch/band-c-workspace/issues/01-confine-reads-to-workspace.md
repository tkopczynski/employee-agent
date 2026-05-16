# 01 — Confine the Agent's filesystem reads to the Workspace

Status: ready-for-human

## Parent

PRD: `.scratch/band-c-workspace/PRD.md`

## What to build

Introduce the **Workspace** as the Agent's only filesystem surface for reads. A new `Workspace` module owns the Workspace root (from configuration) and resolves a Workspace-relative path to an absolute path, refusing any path that escapes the root — parent-directory traversal, absolute paths, and symlinks that resolve outside the root. The existing `read_file`, `list_dir`, and `grep` tools are routed through this resolver so they can only ever touch the Workspace; an attempt to reach anything outside it returns a clear refusal the Agent relays to the User instead of crashing the Turn.

This is the strict airlock from ADR-0007 applied to reads first: it directly delivers the original concern that the Agent's disk reach was too permissive. No SQLite schema change — the Workspace is files, not Recall.

## Acceptance criteria

- [x] A `Workspace` module resolves a Workspace-relative path to an absolute path under the configured Workspace root
- [x] `..` traversal, absolute paths, and symlinks resolving outside the root are all refused
- [x] `read_file` / `list_dir` / `grep` operate only within the Workspace: an in-Workspace path works; an outside path is refused
- [x] A refused path comes back as a tool result the Agent relays — the Turn does not crash
- [x] The Workspace root is read from configuration, never hardcoded
- [x] No SQLite schema change; nothing about the Workspace is persisted to the database
- [x] Tests: pure unit tests for the airlock — `..`, absolute, and symlink-out all refused; an in-bounds relative path resolves under the root (no Docker)

## Blocked by

None - can start immediately

## Comments

**2026-05-16 — implemented (TDD).** New `src/employee_agent/workspace.py`:
`Workspace(root).resolve(relpath) -> Path` rejects absolute paths, refuses any
`realpath` that escapes the canonical root (one check subsumes `..` and
symlink-out), and exposes a read-only `root`. `WorkspaceError` propagates
through the existing `ReadOnlyTools.run` try/except, so a refusal is relayed
as a tool result and never crashes the Turn. `read_file`/`list_dir`/`grep`
route every path through the airlock; `grep` additionally re-resolves each
walked file so a symlinked-out file inside the tree is skipped mid-walk
(hardened now per design discussion, not deferred). Workspace root is
`Config.workspace_root` (`DEFAULT_WORKSPACE = {"root": "workspace"}`), wired in
`__main__` via `EMPLOYEE_AGENT_WORKSPACE` (mirrors `EMPLOYEE_AGENT_DB`). No
`store.py` / schema change.

Tests: `tests/test_workspace.py` — 5 pure unit tests (in-bounds resolves
under root; absolute / `..`-escape / symlink-out refused; in-bounds `a/../b`
still resolves, proving containment not a substring ban). `tests/
test_agent_read_only_tools.py` migrated to a configured Workspace root +
relative paths, plus two new agent-loop tests: an outside read is refused and
relayed without crashing the Turn, and `grep` does not leak a symlinked-out
file's contents into context. Full suite: 49 passed.

Scope held to reads: no `write_file` / `Sandbox` / `run_command`, and the
`ReadOnlyTools` class and its "read-only ⇒ zero risk" rationale are
deliberately unchanged (still accurate this slice; the rename + rationale
rewrite belong to the later `run_command` issue per the PRD spine).
