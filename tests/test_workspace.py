"""The Workspace airlock — pure unit tests, no Docker (Issue 01).

The Workspace is the Agent's entire filesystem surface (CONTEXT.md): the only
place it may read. These tests assert the security boundary through the
module's one public method, `resolve` — an in-bounds relative path resolves to
an absolute path under the configured root; every escape (absolute, `..` out,
symlink out) is refused. We never assert on private state.
"""

import os

import pytest

from employee_agent.workspace import Workspace, WorkspaceError


def test_in_bounds_relative_path_resolves_to_an_absolute_path_under_root(tmp_path):
    ws = Workspace(tmp_path)

    resolved = ws.resolve("notes/report.txt")

    assert resolved.is_absolute()
    assert resolved == tmp_path / "notes" / "report.txt"
    assert resolved.is_relative_to(os.path.realpath(tmp_path))


def test_absolute_path_is_refused(tmp_path):
    ws = Workspace(tmp_path)

    with pytest.raises(WorkspaceError):
        ws.resolve("/etc/passwd")


def test_parent_traversal_escaping_the_root_is_refused(tmp_path):
    ws = Workspace(tmp_path / "root")

    with pytest.raises(WorkspaceError):
        ws.resolve("../../etc/passwd")


def test_symlink_resolving_outside_the_root_is_refused(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("top secret")
    # A symlink that lives inside the Workspace but points out of it.
    (root / "escape").symlink_to(outside)
    ws = Workspace(root)

    with pytest.raises(WorkspaceError):
        ws.resolve("escape/secret.txt")


def test_in_bounds_parent_traversal_still_resolves(tmp_path):
    # `a/../b` never leaves the root, so the airlock must allow it: the rule
    # is containment, not a blunt ban on the characters `..`.
    ws = Workspace(tmp_path)

    resolved = ws.resolve("a/../b/data.csv")

    assert resolved == tmp_path / "b" / "data.csv"
