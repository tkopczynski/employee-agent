"""The thin execution seam for `run_command` (PRD "Modules", ADR-0007).

`Sandbox` is the entire contract the execute tool depends on: run one
command, get back what it produced. No Docker types leak out — the real
Docker-backed adapter (the pinned image, `--network none`, the Workspace
bind-mounted as the only writable path, dropped capabilities, CPU/memory/
wall-clock limits) is a *later* issue (04); this slice proves the whole
agent-loop path with a structural fake, the same seam pattern as
`LLMClient`/`WebClient`/`Embedder`. Tests substitute the fake; no Docker in
the test run.

`run` never raises for a command that merely fails or times out — a non-zero
exit, output on stderr, or a wall-clock timeout are *results*, not errors, so
the Turn is never crashed by a misbehaving command (containment bounds the
blast radius — ADR-0007).
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


class Sandbox(Protocol):
    def run(self, command: str, timeout: float) -> ExecResult: ...
