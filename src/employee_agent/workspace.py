"""The Workspace airlock — the Agent's only filesystem surface for reads.

The Workspace is a single durable directory that is the Agent's *entire*
filesystem reach (CONTEXT.md, ADR-0007): it may read nowhere else. This module
is the one place that confinement is enforced. `resolve` turns a
Workspace-relative path into an absolute path under the configured root and
refuses every escape — absolute paths, `..` traversal, and symlinks that
resolve outside the root. Pure and deterministic; no Docker.
"""

import os
from pathlib import Path


class WorkspaceError(Exception):
    """A path tried to escape the Workspace airlock."""


class Workspace:
    def __init__(self, root):
        self._root = Path(os.path.realpath(root))

    @property
    def root(self) -> Path:
        """The canonical (symlink-resolved) Workspace root."""
        return self._root

    def resolve(self, relpath: str) -> Path:
        if os.path.isabs(relpath):
            raise WorkspaceError(
                f"{relpath!r} is an absolute path; the Workspace only "
                "accepts paths relative to its root"
            )
        # realpath collapses `..` and follows symlinks, so one containment
        # check against the canonical root rejects every escape route.
        candidate = Path(os.path.realpath(self._root / relpath))
        if not candidate.is_relative_to(self._root):
            raise WorkspaceError(
                f"{relpath!r} resolves outside the Workspace; the Agent "
                "has no filesystem access beyond it"
            )
        return candidate
