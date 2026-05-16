# PRD: Band-C Sandboxed Workspace

Status: ready-for-agent

> Domain vocabulary follows `CONTEXT.md` (the `Workspace` term and its relationships). This PRD is the first **band-C** increment; it is governed by **ADR-0007** and partially supersedes **ADR-0001** (Docker for tool execution only) and the band-B MVP PRD (`.scratch/employee-agent-mvp/PRD.md`) user stories US-6/US-7/US-8 (arbitrary-path reads), US-12/US-13 (no machine changes / safe by construction), US-28 (no Docker), and its "no `shell` tool" decision. Those are deliberately retracted/reversed here, not violated — see ADR-0007.

## Problem Statement

The User can talk to the Agent and have it read files and the web, but the Agent cannot *do* anything: it cannot write a file or run code. When the User asks it to "create a script to compute something", the Agent can only describe the script — the User must copy it out and run it themselves. At the same time, the Agent's current filesystem reach is *unbounded* (any path on disk), which the User is unwilling to trust the moment writing and execution enter the picture. The User wants the Agent to actually perform computational work on their behalf, made safe by **containment** rather than by being crippled — with no ability to damage the machine, read arbitrary private files, or exfiltrate data.

## Solution

Introduce the **Workspace**: a single durable directory that is the Agent's *entire* filesystem surface and the only place it may read, write, or run code. Execution happens inside a Docker container with **no network** and the Workspace bind-mounted as the only visible, writable path, under CPU/memory/time limits. The Agent keeps its read-only web tools and bridges external data into the Workspace itself; code in the Workspace has no network of its own. The Workspace **persists across Conversations** (the Agent's "desk") and is independent of **Sealing** and **Recall**. There are **no confirmation prompts**: containment bounds the blast radius, so write/execute are as friction-free as the read-only tools — the band-C analogue of "read-only ⇒ zero risk". The User stages their own inputs by placing files into the Workspace; the Agent cannot reach anything else on disk (strict airlock).

## User Stories

1. As the User, I want the Agent to write a file into the Workspace, so that it can produce a script or artifact for me instead of only describing one.
2. As the User, I want the Agent to run a command in the Workspace, so that it can actually execute the script it wrote and give me the result.
3. As the User, I want to ask the Agent to "compute something" and get the computed answer, so that it does the work rather than handing me code to run.
4. As the User, I want to drop my own data file into the Workspace and have the Agent compute over it, so that I control exactly what data it can touch.
5. As the User, I want the Agent to clearly refuse and explain when I ask it to read a file outside the Workspace, so that the airlock boundary is predictable rather than a silent failure.
6. As the User, I want the Agent to fetch data from the web and write it into the Workspace for a script to use, so that computations needing external data still work despite the sandbox having no network.
7. As the User, I want code the Agent runs to have no network access, so that nothing it runs can exfiltrate my data even if the Agent is confused or prompt-injected.
8. As the User, I want the Workspace to persist across sessions, so that a script the Agent built yesterday is still there today.
9. As the User, I want Sealing a Conversation to never touch the Workspace, so that ending a session does not destroy my working files.
10. As the User, I want Recall to still answer "when did I ask you to build that script", so that the Workspace persisting and Recall remembering stay consistent with each other.
11. As the User, I want write and execute to run without confirmation prompts, so that building a script (many writes and runs) is not death by a hundred dialogs.
12. As the User, I want execution to be time- and resource-bounded, so that a runaway or looping script cannot hang my session or burn my machine.
13. As the User, I want a clear, honest failure when a needed library is not in the environment, so that the Agent stops cleanly instead of flailing or pretending.
14. As the User, I want the compute environment to be the same on macOS and Linux, so that the Agent and my scripts behave identically wherever I run the app.
15. As the User, I want the Workspace location, the image, and the resource/time limits to be configurable, so that I can tune cost vs capability the same way I tune the rest of the app.
16. As the User, I want to see how long an executed command took and whether it succeeded, so that execution cost stays observable in keeping with the project's cost-bounded ethos.
17. As the User, I want the Agent to keep its read-only web tools unchanged, so that web search and fetch still work exactly as before.
18. As the User, I want the Agent unable to read `~/.ssh`, `~/.aws`, or anything else outside the Workspace, so that a confused or injected Agent cannot harvest my secrets.
19. As the User, I want to understand that the Workspace is disposable by contract, so that I know to git-track or back up anything precious I keep there rather than expecting prompts to protect it.
20. As the User, I want the Agent to treat the Workspace as its working area it may overwrite or delete within, so that it can iterate on scripts without asking permission for each change.
21. As the User, I want grep and list to work within the Workspace, so that the Agent can orient itself among the files it and I have placed there.
22. As the User, I want the Agent to chain commands (pipelines, multi-step) inside the sandbox, so that real computational tasks are not hobbled by an artificially narrow execute tool.
23. As the User, I want the app itself to keep running as a single process with one SQLite file, so that only tool execution is containerized and the rest stays simple to run (ADR-0001 still holds for the app).
24. As the User, I want the Workspace to never be written into the SQLite database, so that my single inspectable data file stays about Conversations and Recall, not loose working files.
25. As a developer, I want the execution containment behind a thin `Sandbox` interface, so that the Docker reality is encapsulated and the agent loop can be tested with a fake.
26. As a developer, I want the path airlock behind a small `Workspace` module, so that the security-critical escape-rejection logic is unit-testable without Docker.
27. As a developer, I want the read/write/grep/list tools routed through the `Workspace` airlock, so that confinement is enforced in one place rather than scattered across tool handlers.
28. As a developer, I want the no-longer-read-only tool class renamed and its rationale comment rewritten, so that the code does not still claim "read-only ⇒ zero risk" when it now writes and executes.
29. As a developer, I want a real-Docker integration test for `Sandbox`, so that "no network", "no filesystem outside the mount", and "timeout enforced" are verified as actual behaviour, not assumed.
30. As a developer, I want an agent-loop integration test with a fake `Sandbox`, so that the write→run→reply vertical slice and the outside-read refusal are caught without requiring Docker in every test run.

## Implementation Decisions

**Governing records.** ADR-0007 is the canonical decision record (threat model, rejected alternatives, residual risks). `CONTEXT.md` holds the `Workspace` vocabulary and relationships. ADR-0001 is partially superseded: the application remains single-process Python + SQLite; **only tool execution is containerized**.

**Threat model (from ADR-0007).** Defends against a confused or prompt-injected Agent — *not* code actively escaping the sandbox. Docker is chosen for cross-platform uniformity and a reproducible environment, **not** isolation strength; its isolation is deliberately under-used and must not be "optimised away" as if it were the security point.

**Modules.**

- **`Sandbox`** — new deep module. Interface: `run(command, timeout) → ExecResult{ stdout, stderr, exit_code, timed_out }`. Encapsulates the entire Docker reality: the pinned image, `--network none`, the Workspace bind-mounted as the only visible/writable path, non-root user, dropped capabilities, and CPU/memory/wall-clock limits. Callers never see Docker. Two implementations behind the interface: a real Docker-backed one, and a fake (in-process / canned) one for agent-loop tests — the same seam pattern as the existing `LLMClient`/`WebClient`/`Embedder`.
- **`Workspace`** — new small, security-critical module. Owns the Workspace root and the airlock: `resolve(relpath) → Path` that rejects every escape (`..` traversal, absolute paths, and symlinks that resolve outside the root). Pure, deterministic, no Docker. It is the single confinement point for the file tools.
- **Tool surface** — the existing band-B tool class is no longer read-only. `read_file` / `list_dir` / `grep` are routed through `Workspace.resolve` (paths are interpreted Workspace-relative; escapes are refused with a clear message the Agent can relay). New `write_file` (Workspace-relative). New `run_command` → `Sandbox.run`. `web_search` / `fetch_url` / `current_time` are unchanged. The class is renamed away from "read-only", and its module rationale comment is rewritten from "read-only ⇒ zero risk" to the containment rationale.
- **Config** — Workspace root path, image name/tag, and the CPU/memory/wall-clock limits are configuration, consistent with the project's existing cost-bound, everything-configurable ethos (mirrors the existing `_MAX_*` caps).
- **Image** — a pinned Dockerfile shipping a curated stack (e.g. a fixed Python plus a small set of common compute libraries). No runtime installs (the sandbox has no network); a missing library is a clean, reported failure. The stack grows only by a human-driven image rebuild, which preserves reproducibility.

**Execute tool shape.** A single general `run_command(command)` executed inside the sandbox (arbitrary commands, pipelines, multi-step). This deliberately reverses the MVP PRD's "no `shell` tool"; under containment, a narrower `run_script` would buy ≈0 safety and only handicap the Agent (ADR-0007).

**Trust model.** Containment *is* the trust model. Write and execute run **prompt-free**, exactly like the read-only tools. No confirmation/trust subsystem is built — the MVP PRD's deferral of one stands.

**Airlock semantics.** The Agent has *no* filesystem access outside the Workspace — not even read. Inputs enter the Workspace only by (a) the User placing files in it, or (b) the Agent writing fetched web data into it. The Agent never copies files in from elsewhere on disk (no outside-read import path).

**Persistence & schema.** The Workspace is a directory on disk that persists across Conversations and is unaffected by Sealing. **No schema change**: nothing about the Workspace is written to the SQLite database; it is files, not Recall. Network remains an *Agent* capability (`web_search`/`fetch_url` unchanged), never a *Workspace* one.

**Observability.** Executed-command wall-clock duration and exit status are logged, consistent with the project's existing cost-observability discipline (hot-token logging around Compaction). Execution is a cost surface and must be observable, not just bounded.

## Testing Decisions

A good test asserts **external behaviour through the module's interface**, never implementation detail. Tests must not assert on LLM wording, on Docker CLI internals, or on private state — they assert observable contracts (an escaping path is refused; a networked command fails inside the sandbox; a write→run sequence produces a reply grounded in the output).

Modules to be tested (confirmed with the User): **`Workspace`, `Sandbox`, and the Agent loop (integration).**

- **`Workspace`** — pure unit tests, no Docker. Assert the airlock: `..` traversal refused; absolute paths refused; a symlink that resolves outside the root refused; an in-bounds relative path resolves under the root. This is the security boundary — highest value-per-effort.
- **`Sandbox`** — a real-Docker integration test, marked/gated so it is skipped when Docker is unavailable (the same spirit as Recall's real-`sqlite-vec`/FTS5 integration test with a fake Embedder). Assert: a command that tries to reach the network fails; a command that tries to read outside the bind-mount cannot; a command exceeding the wall-clock limit comes back `timed_out`; stdout and exit code are captured for a normal command.
- **Agent loop (integration)** — end-to-end with a **fake `Sandbox`** and the existing faked LLM/Web adapters. Assert: a scripted "write a script and run it" request routes `write_file` → `run_command` and the result is incorporated into the reply; a request to read a path outside the Workspace is refused and the Agent relays the refusal. One test per vertical slice.

Prior art: `tests/test_agent_read_only_tools.py` (one integration test per tool vertical slice) is the direct model for the agent-loop tests; the Recall test suite (real backing store + fake adapter, gated where it needs the real dependency) is the model for the `Sandbox` real/fake split.

## Out of Scope

- **Sandbox-escape hardening** (VM, gVisor, Firecracker) — the threat model explicitly excludes code actively fighting to escape (ADR-0007).
- **Closing the `fetch_url` → Workspace-contents exfil residual** — a prompt-injected Agent can still exfiltrate *Workspace contents* via the pre-existing `fetch_url`. The airlock bounds the blast radius to the Workspace; closing the channel itself is a deliberately deferred, separate later increment (ADR-0007).
- **Runtime package installs / Agent-bridged wheels** — no network in the sandbox; the curated image is the environment; missing libraries fail cleanly.
- **A confirmation / trust / approval subsystem** — containment is the trust model; none is built.
- **Multiple or per-Conversation Workspaces** — exactly one persistent Workspace; it does not branch per session.
- **Making the Workspace searchable via Recall** — the Workspace is files, not memory; it is never indexed.
- **A networked or selectively-egressed sandbox** — executed code gets no network, full stop.
- **Windows support; a GUI file manager for the Workspace** — input staging is plain filesystem (cp/Finder/terminal).
- **Re-litigating the band-B MVP** — Recall, Compaction, Summarisation, Sealing, the chat spine are unchanged.

## Further Notes

The project's real purpose is learning **cost-effective, bounded, observable operation** of an agent. The Workspace must respect that: execution is time- and resource-capped and its duration/exit logged, mirroring the Compaction cost-observability discipline — execution is just another cost surface to keep bounded and watchable.

The Workspace is **disposable by contract**: the Agent may overwrite or delete files within it without prompting. It is not protected by confirmation. Keeping anything precious there is the User's responsibility (git-track or back up the Workspace) — this is a conscious trade made to keep the build-a-script loop friction-free, recorded in ADR-0007.

This PRD retracts/reverses specific band-B MVP user stories and decisions (US-6/7/8/12/13/28, "no `shell` tool"); ADR-0007 is the authoritative record of *why* and a future reader confused by the contradiction with `.scratch/employee-agent-mvp/PRD.md` should be pointed there. ADR-0001's own "Revisit when" anticipated this trigger.

Recommended follow-up: run `/to-issues` against this PRD to slice it into tracer-bullet vertical issues (suggested spine: pinned image + `Sandbox` Docker runner; `Workspace` airlock; Workspace-confined file tools + `write_file`; `run_command` wiring + tool-class rename; agent-loop integration).
