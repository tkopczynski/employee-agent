# Band-C sandboxed Workspace: contained read/write/execute surface

Status: accepted — supersedes the no-Docker clause of ADR-0001 (for tool execution only); retracts/reverses PRD US-6/7/8, US-13, and "no `shell` tool" for band-C.

The Agent gains a **Workspace**: its *entire* filesystem surface and the only place it may read, write, or execute. Tool execution runs in a Docker container with **no network** and the Workspace bind-mounted as the only visible/writable path. This deliberately retires the band-B "safe by construction" guarantee (US-13) and replaces it with **safe by containment**: blast radius is bounded to the Workspace, so write/execute run **prompt-free** — the band-C analogue of "read-only ⇒ zero risk" (US-12/US-34). A general `run_command` tool is added; this knowingly reverses the PRD's "no `shell` tool", because that ban's precondition (no containment) no longer holds.

## Threat model

Defends against a **confused or prompt-injected Agent**, *not* code actively escaping the sandbox. Hardened isolation (VM/gVisor/Firecracker) is deliberately out of scope. **Docker is chosen for cross-platform uniformity (macOS + Linux) and a reproducible compute environment — explicitly NOT for isolation strength.** Do not "optimise away" the container believing it was a security boundary; under this threat model its isolation is deliberately under-used.

## Considered options (rejected)

- **Path-prefix confinement, no sandbox** — confines writes but *not* execution: executed code is unconfined and is the whole risk. Insufficient.
- **macOS Seatbelt (`sandbox-exec`)** — proportionate and dependency-free, but macOS-only (cannot give the required Linux parity) and Apple-deprecated/opaque. Docker's portability + reproducible environment won over ADR-0001's no-Docker simplicity.
- **Broad arbitrary-path reads (status quo, US-6/7/8)** — rejected for a **strict airlock**: the Agent has zero filesystem surface outside the Workspace. Inputs enter only by the User staging files into it or the Agent writing fetched web data into it. This also bounds the residual `fetch_url` exfil blast radius to Workspace contents.
- **A confirmation/trust subsystem** — rejected; containment *is* the trust model. Per-write prompts would fire dozens of times building one script and defeat the use case. The PRD's deferral of a confirmation/trust model stands — none is built.
- **Runtime package installs / Agent-bridged wheels** — impossible/fragile given no network in the sandbox. The image ships a pinned curated stack; a missing library is a clean reported failure; the stack grows only by a human-driven image rebuild (reproducibility preserved).

## Consequences

- **Residual, consciously deferred:** a prompt-injected Agent can still exfiltrate *Workspace contents* via the pre-existing `fetch_url` (GET to an arbitrary URL). The airlock bounds the blast radius to the Workspace; closing this channel is a separate later increment, not this one.
- The Workspace is **disposable / version-controlled by contract**: the Agent may overwrite or delete files in it without prompting. It is not protected by confirmation — protect anything precious with git/backup.
- The application itself remains single-process Python + SQLite (ADR-0001 stands); **only tool execution** is containerized.
- Network stays an *Agent* capability (`web_search`/`fetch_url` unchanged), never a *Workspace* one.
