"""Sandbox — the real Docker-backed adapter, gated like Recall's real backing
store (ADR-0007 / Band-C Issue 04, PRD Testing Decisions).

Marked `docker` and skipped when no Docker daemon is reachable — the same
spirit as Recall's real-`sqlite-vec`/FTS5 integration test: the dependency is
real here, faked elsewhere. A session fixture builds the pinned image from the
repo Dockerfile so the test is self-contained and reproducible.

We assert observable contracts through the `Sandbox` interface only — never
the `docker` argv, never private state: stdout + exit code are captured; a
networked command fails; a host path outside the bind-mount is unreachable; a
command past its wall-clock comes back `timed_out`; a curated library is
present and an absent one fails *cleanly* (a result, not a raised exception).
The `DockerSandbox` is built from `Config`, so the configured image / CPU /
memory knobs are exercised end-to-end (AC#6), not just unit-checked.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from employee_agent.config import Config
from employee_agent.sandbox import DockerSandbox

_DOCKERFILE = Path(__file__).resolve().parents[1] / "docker" / "sandbox.Dockerfile"


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        not _docker_available(),
        reason="Docker unavailable; the real Sandbox is a real-Docker "
        "dependency (ADR-0007), faked in every other test",
    ),
]


@pytest.fixture(scope="session")
def sandbox_image() -> str:
    """Build the pinned curated image once per test session."""
    image = Config().sandbox_image
    build = subprocess.run(
        ["docker", "build", "-f", str(_DOCKERFILE), "-t", image, str(_DOCKERFILE.parent)],
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr
    return image


@pytest.fixture
def sandbox(tmp_path, sandbox_image):
    """A DockerSandbox over a fresh Workspace, built from Config (AC#6)."""
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = Config(workspace={"root": str(ws)}, sandbox={"image": sandbox_image})
    return DockerSandbox(ws, cfg), ws


def test_normal_command_captures_stdout_and_exit_code(sandbox):
    sbx, _ws = sandbox

    result = sbx.run("echo hello-from-sandbox", timeout=30)

    assert "hello-from-sandbox" in result.stdout
    assert result.exit_code == 0
    assert result.timed_out is False


def test_no_network_command_fails(sandbox):
    sbx, _ws = sandbox

    # A numeric IP so there is no DNS hang; with `--network none` the connect
    # fails fast and the command exits non-zero.
    result = sbx.run(
        "python -c \"import socket; socket.create_connection(('1.1.1.1', 80), 3)\"",
        timeout=30,
    )

    assert result.exit_code != 0
    assert result.timed_out is False
    assert result.stderr  # the failure is reported, not swallowed


def test_cannot_read_outside_the_bind_mount(sandbox, tmp_path):
    sbx, ws = sandbox
    # A host secret OUTSIDE the Workspace (sibling of the bind-mount source).
    secret = tmp_path / "secret-outside-workspace.txt"
    secret.write_text("TOP-SECRET-DO-NOT-LEAK")
    # A control file INSIDE the Workspace proves the mount itself works.
    (ws / "inside.txt").write_text("workspace-content")

    outside = sbx.run(f"cat {secret}", timeout=30)
    inside = sbx.run("cat inside.txt", timeout=30)

    # The host path outside the Workspace is simply not present in the
    # container — the airlock holds.
    assert outside.exit_code != 0
    assert "TOP-SECRET-DO-NOT-LEAK" not in outside.stdout
    # ...while the Workspace itself is readable, confirming the contrast.
    assert inside.exit_code == 0
    assert "workspace-content" in inside.stdout


def test_command_exceeding_wall_clock_times_out(sandbox):
    sbx, _ws = sandbox

    result = sbx.run("sleep 30", timeout=2)

    assert result.timed_out is True
    assert result.exit_code != 0


def test_curated_stack_present_and_absent_library_fails_cleanly(sandbox):
    sbx, _ws = sandbox

    present = sbx.run(
        "python -c \"import numpy, pandas; print('stack-ok', numpy.__version__)\"",
        timeout=30,
    )
    # `scipy` is deliberately NOT in the pinned image (see the Dockerfile).
    absent = sbx.run("python -c \"import scipy\"", timeout=30)

    # The curated libraries are present.
    assert present.exit_code == 0
    assert "stack-ok" in present.stdout

    # A needed-but-absent library is a clean, reported failure — a result the
    # Agent can relay, never a raised exception or a network-install attempt.
    assert absent.exit_code != 0
    assert absent.timed_out is False
    assert "ModuleNotFoundError" in absent.stderr
