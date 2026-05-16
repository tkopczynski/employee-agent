# 01 — Confine the Agent's filesystem reads to the Workspace

Status: ready-for-agent

## Parent

PRD: `.scratch/band-c-workspace/PRD.md`

## What to build

Introduce the **Workspace** as the Agent's only filesystem surface for reads. A new `Workspace` module owns the Workspace root (from configuration) and resolves a Workspace-relative path to an absolute path, refusing any path that escapes the root — parent-directory traversal, absolute paths, and symlinks that resolve outside the root. The existing `read_file`, `list_dir`, and `grep` tools are routed through this resolver so they can only ever touch the Workspace; an attempt to reach anything outside it returns a clear refusal the Agent relays to the User instead of crashing the Turn.

This is the strict airlock from ADR-0007 applied to reads first: it directly delivers the original concern that the Agent's disk reach was too permissive. No SQLite schema change — the Workspace is files, not Recall.

## Acceptance criteria

- [ ] A `Workspace` module resolves a Workspace-relative path to an absolute path under the configured Workspace root
- [ ] `..` traversal, absolute paths, and symlinks resolving outside the root are all refused
- [ ] `read_file` / `list_dir` / `grep` operate only within the Workspace: an in-Workspace path works; an outside path is refused
- [ ] A refused path comes back as a tool result the Agent relays — the Turn does not crash
- [ ] The Workspace root is read from configuration, never hardcoded
- [ ] No SQLite schema change; nothing about the Workspace is persisted to the database
- [ ] Tests: pure unit tests for the airlock — `..`, absolute, and symlink-out all refused; an in-bounds relative path resolves under the root (no Docker)

## Blocked by

None - can start immediately
