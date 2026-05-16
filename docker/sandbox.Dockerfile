# The pinned Sandbox image (ADR-0007 / Band-C Issue 04).
#
# This containerises ONLY tool execution (`run_command`), never the
# application — the app stays single-process Python + SQLite on the host
# (ADR-0001 still holds; ADR-0007 supersedes it for tool execution only).
#
# Docker here buys cross-platform uniformity (macOS + Linux) and a
# reproducible compute environment, NOT isolation strength: the threat model
# is a confused or prompt-injected Agent, not code actively escaping (see
# ADR-0007). Do not "optimise away" this image believing it was the security
# boundary.
#
# The stack is curated and version-pinned. There are NO runtime installs (the
# sandbox runs with `--network none`), so a library not listed here is absent
# *by design*: code needing it fails cleanly with a reported
# ModuleNotFoundError rather than a flailing network install. The stack grows
# only by a human-driven rebuild of this file, which is what keeps the
# environment reproducible.
FROM python:3.13-slim-bookworm

# Curated compute libraries, pinned for reproducibility. Grow this set only
# by a deliberate, reviewed edit + image rebuild — never at runtime.
RUN pip install --no-cache-dir numpy==2.2.3 pandas==2.2.3

# The Workspace is bind-mounted here at run time as the container's only
# visible/writable host path; commands execute from it.
WORKDIR /workspace
