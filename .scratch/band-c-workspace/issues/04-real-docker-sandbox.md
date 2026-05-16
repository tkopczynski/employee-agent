# 04 — Real Docker-backed Sandbox + pinned image + containment

Status: ready-for-human

## Parent

PRD: `.scratch/band-c-workspace/PRD.md`

## What to build

Replace the fake `Sandbox` with a **real Docker-backed implementation** behind the same interface, plus a pinned image. Commands execute in a container built from a pinned Dockerfile shipping a curated stack (a fixed interpreter plus a small set of common compute libraries). The container runs with **no network**, the **Workspace bind-mounted as the only visible/writable path**, as a non-root user with dropped capabilities, under CPU / memory / wall-clock limits from configuration.

There are **no runtime package installs** (no network in the sandbox); a missing library is a clean, reported failure rather than a flailing retry. The compute environment is identical on macOS and Linux.

Governed by ADR-0007: Docker is chosen for cross-platform uniformity and a reproducible environment, **not** isolation strength; the threat model is a confused or prompt-injected Agent, not code actively escaping the sandbox. Do not "optimise away" the container believing it was a security boundary.

## Acceptance criteria

- [x] A real Docker-backed `Sandbox` runs commands behind the existing interface; a normal command's stdout and exit code are captured
- [x] The container has no network: a command attempting network access fails
- [x] The container's only filesystem is the Workspace: a command attempting to read outside the bind-mount cannot
- [x] A command exceeding the configured wall-clock limit returns `timed_out`
- [x] The image is pinned (fixed interpreter + curated library set); a needed-but-absent library produces a clean reported failure
- [x] Image tag and CPU / memory / wall-clock limits are read from configuration
- [x] Tests: a gated/marked real-Docker integration test (skipped when Docker is unavailable) asserting no-network, no-filesystem-escape, timeout, and stdout/exit capture — mirrors the Recall real-backing-store integration test pattern

## Blocked by

- 03 — run_command end-to-end via a fake Sandbox

## Comments

**2026-05-16 — implemented (TDD).** `DockerSandbox` added behind the existing
`Sandbox` protocol (`sandbox.py`); the fake stays for the agent-loop tests —
the same real/fake seam split as `LLMClient`/`WebClient`/`Embedder`. Each
command runs in a throwaway container from the pinned image with
`--network none`, the Workspace bind-mounted as the *only* host path
(`--volume <ws>:/workspace`, `--workdir /workspace`), as the host's own
non-root `uid:gid` with `--cap-drop ALL`, under config-driven `--cpus` /
`--memory` and a `subprocess` wall-clock; on `TimeoutExpired` the named
container is force-removed so a runaway cannot outlive its bound. `run` never
raises — a non-zero exit, stderr, missing library, or timeout are *results*
(ADR-0007 containment).

Non-root strategy: host `uid:gid` (not a baked-in image user) so the
bind-mounted Workspace stays writable on macOS + Linux — never container
root, no isolation chased beyond ADR-0007's threat model.

Pinned image: `docker/sandbox.Dockerfile` — `python:3.13-slim-bookworm` +
pinned `numpy`/`pandas`, no runtime installs (no network); `scipy` is absent
*by design* and is the missing-library probe. Config grew `image`/`cpus`/
`memory` (wall-clock already there); `__main__` wires the real
`DockerSandbox`; the `tools.py` docstring no longer says "Issue 04 is later".

Tests (vertical slices, one RED→GREEN each): `tests/test_config_sandbox.py`
(pure, Docker-free — image + cpu/mem/timeout default and overridable);
`tests/test_sandbox_integration.py` — `pytest.mark.docker` + skipif on no
reachable daemon (mirrors Recall's gated real-backing-store test), a
session fixture builds the pinned image, then one test each for stdout/exit
capture, no-network, no-filesystem-escape (host path outside the mount
unreachable while the Workspace reads fine), wall-clock `timed_out`, and
curated-stack present/absent. Suite: 60 passed (incl. the 5 real-Docker
tests — Docker was available, so they ran rather than skipped).
