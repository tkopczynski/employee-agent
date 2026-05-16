# 04 — Real Docker-backed Sandbox + pinned image + containment

Status: ready-for-agent

## Parent

PRD: `.scratch/band-c-workspace/PRD.md`

## What to build

Replace the fake `Sandbox` with a **real Docker-backed implementation** behind the same interface, plus a pinned image. Commands execute in a container built from a pinned Dockerfile shipping a curated stack (a fixed interpreter plus a small set of common compute libraries). The container runs with **no network**, the **Workspace bind-mounted as the only visible/writable path**, as a non-root user with dropped capabilities, under CPU / memory / wall-clock limits from configuration.

There are **no runtime package installs** (no network in the sandbox); a missing library is a clean, reported failure rather than a flailing retry. The compute environment is identical on macOS and Linux.

Governed by ADR-0007: Docker is chosen for cross-platform uniformity and a reproducible environment, **not** isolation strength; the threat model is a confused or prompt-injected Agent, not code actively escaping the sandbox. Do not "optimise away" the container believing it was a security boundary.

## Acceptance criteria

- [ ] A real Docker-backed `Sandbox` runs commands behind the existing interface; a normal command's stdout and exit code are captured
- [ ] The container has no network: a command attempting network access fails
- [ ] The container's only filesystem is the Workspace: a command attempting to read outside the bind-mount cannot
- [ ] A command exceeding the configured wall-clock limit returns `timed_out`
- [ ] The image is pinned (fixed interpreter + curated library set); a needed-but-absent library produces a clean reported failure
- [ ] Image tag and CPU / memory / wall-clock limits are read from configuration
- [ ] Tests: a gated/marked real-Docker integration test (skipped when Docker is unavailable) asserting no-network, no-filesystem-escape, timeout, and stdout/exit capture — mirrors the Recall real-backing-store integration test pattern

## Blocked by

- 03 — run_command end-to-end via a fake Sandbox
