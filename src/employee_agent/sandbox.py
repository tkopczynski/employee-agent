"""The execution seam for `run_command` (PRD "Modules", ADR-0007).

`Sandbox` is the entire contract the execute tool depends on: run one
command, get back what it produced. No Docker types leak out. Two
implementations sit behind it — the same seam pattern as
`LLMClient`/`WebClient`/`Embedder`:

- `DockerSandbox` — the real, Docker-backed adapter (this issue, 04):
  the pinned image, `--network none`, the Workspace bind-mounted as the only
  visible/writable host path, a non-root user with dropped capabilities, and
  config-driven CPU / memory / wall-clock limits.
- the test `FakeSandbox` — a structural, in-process double so the agent loop
  is tested without Docker in every run.

`run` never raises for a command that merely fails or times out — a non-zero
exit, output on stderr, a missing library, or a wall-clock timeout are
*results*, not errors, so the Turn is never crashed by a misbehaving command
(containment bounds the blast radius — ADR-0007).
"""

import os
import subprocess
import uuid
from dataclasses import dataclass
from typing import Protocol

from .config import Config


@dataclass(frozen=True)
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


def _as_text(raw: bytes | str | None) -> str:
    # A timed-out subprocess surfaces its partial output as bytes (even under
    # text=True), and may capture nothing at all. ExecResult.stdout/stderr are
    # str by contract, so decode defensively — same lenient decode as the
    # read_file tool, so a timed-out command's output is never corrupting.
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return raw


class Sandbox(Protocol):
    def run(self, command: str, timeout: float) -> ExecResult: ...


class DockerSandbox:
    """Real Docker-backed Sandbox (ADR-0007 / Issue 04).

    Each command runs in a throwaway container from the pinned image with
    `--network none`, the Workspace bind-mounted as the only visible/writable
    host path, as the host's own non-root uid:gid with all capabilities
    dropped, under config-driven CPU / memory / wall-clock caps. Docker is
    chosen for cross-platform uniformity + a reproducible environment, *not*
    isolation strength (threat model: a confused/injected Agent, not code
    fighting to escape) — its isolation is deliberately under-used and must
    not be "optimised away" as if it were the security boundary.
    """

    def __init__(
        self, workspace_root: str | os.PathLike[str], config: Config
    ) -> None:
        # The bind-mount source: canonicalised so the airlock the file tools
        # enforce on the host and the only path visible in the container are
        # the same directory.
        self._workspace_root = os.path.realpath(workspace_root)
        # Every knob is configuration (ADR-0007 / PRD US-15), never hardcoded.
        self._image = config.sandbox_image
        self._cpus = config.sandbox_cpus
        self._memory = config.sandbox_memory

    def run(self, command: str, timeout: float) -> ExecResult:
        name = f"ea-sandbox-{uuid.uuid4().hex}"
        argv = [
            "docker", "run", "--rm",
            "--name", name,
            # No network at all: executed code cannot fetch or exfiltrate —
            # network is an Agent capability, never a Workspace one (ADR-0007).
            "--network", "none",
            # Non-root: the host's own uid:gid. Never container root, yet the
            # bind-mounted Workspace stays writable on macOS + Linux so
            # write_file -> run_command works (ADR-0007 module spec).
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--cap-drop", "ALL",
            "--cpus", str(self._cpus),
            "--memory", str(self._memory),
            # The Workspace is the container's ONLY visible/writable host
            # path — the airlock. Nothing else from the host is mounted.
            "--volume", f"{self._workspace_root}:/workspace",
            "--workdir", "/workspace",
            self._image,
            "sh", "-c", command,
        ]
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired as exc:
            # subprocess killed the `docker run` client, but the container
            # outlives it — force-remove it so a runaway command cannot
            # exceed its wall-clock bound (ADR-0007 cost/time containment).
            subprocess.run(
                ["docker", "rm", "--force", name], capture_output=True
            )
            return ExecResult(
                stdout=_as_text(exc.stdout),
                stderr=_as_text(exc.stderr),
                exit_code=-1,
                timed_out=True,
            )
        return ExecResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            timed_out=False,
        )
