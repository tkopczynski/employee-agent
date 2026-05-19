"""Sandbox unit regressions (no Docker) for the latent bugs ty surfaced.

The Docker-backed contract is exercised in `test_sandbox_integration.py`
(gated on a real daemon). This file pins one defect ty caught without needing
Docker: on a wall-clock timeout the `subprocess` exception carries the partial
output as `bytes`, so the resulting `ExecResult` was leaking `bytes` where
`str` is declared — corrupting the tool result the Agent reads on a timed-out
command. A timeout is still a *result*, not a crash (containment, ADR-0007).
"""

import subprocess

from employee_agent.config import Config
from employee_agent.sandbox import DockerSandbox


def test_timeout_yields_decoded_str_output_never_bytes(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    sbx = DockerSandbox(ws, Config())

    def fake_run(argv, *args, **kwargs):
        # The `docker run` invocation times out with partial output captured
        # as bytes — exactly how CPython's subprocess.run surfaces a timeout
        # even under text=True (the real, verified behaviour).
        if argv[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(
                argv, kwargs.get("timeout", 1),
                output=b"partial out\n", stderr=b"partial err\n",
            )
        # The force-remove cleanup of the runaway container — benign.
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    # A timeout is contained: a result, never a raised exception.
    result = sbx.run("sleep 99", timeout=1)

    assert result.timed_out is True
    assert result.exit_code == -1
    # The contract under test: stdout/stderr are decoded str, never bytes.
    assert isinstance(result.stdout, str)
    assert isinstance(result.stderr, str)
    assert result.stdout == "partial out\n"
    assert result.stderr == "partial err\n"


def test_timeout_with_no_captured_output_is_empty_str(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    sbx = DockerSandbox(ws, Config())

    def fake_run(argv, *args, **kwargs):
        if argv[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout", 1))
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = sbx.run("sleep 99", timeout=1)

    assert result.timed_out is True
    assert result.stdout == "" and result.stderr == ""
    assert isinstance(result.stdout, str) and isinstance(result.stderr, str)
