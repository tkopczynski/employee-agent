"""The read-only local tool surface (PRD Q9, Issue 05; confined in Issue 01).

These tools never write or cause side effects, so they run with no
confirmation prompts (read-only ⇒ zero risk). The filesystem tools
(`read_file`/`list_dir`/`grep`) are confined to the **Workspace**: every path
is interpreted relative to the Workspace root and routed through the
`Workspace` airlock, so the Agent has no filesystem reach outside it
(ADR-0007). A refused path is returned as an ordinary tool result, not a
crash. Web/clock tools are unchanged; web goes through the thin `WebClient`
seam. There is deliberately no `shell` tool. This surface hangs off the same
tool loop as Recall and is independent of it.
"""

import datetime as dt
import json
import os
import re

from .workspace import WorkspaceError

# A single read can pull an unbounded file into the model's context — a cost
# hazard this whole project is about bounding. Cap it (mirrors the agent
# loop's _MAX_TOOL_STEPS bound) and tell the model when it truncated.
_MAX_FILE_BYTES = 64_000

# grep over a tree can return an unbounded match set — same cost hazard.
_MAX_GREP_MATCHES = 200


class ReadOnlyTools:
    def __init__(self, web, workspace):
        self._web = web
        self._workspace = workspace

    SCHEMAS = [
        {
            "name": "read_file",
            "description": (
                "Read the contents of a local text file by path. Read-only."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "list_dir",
            "description": (
                "List the entries of a local directory by path. Directory "
                "names are suffixed with '/'. Read-only."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "grep",
            "description": (
                "Search file contents for a regular-expression pattern under "
                "a path (a file, or a directory searched recursively). "
                "Returns matching lines as 'relpath:lineno:line'. Read-only."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["pattern", "path"],
            },
        },
        {
            "name": "web_search",
            "description": (
                "Search the web for a query. Returns a list of results, each "
                "with a title, url and snippet. Read-only."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
        {
            "name": "fetch_url",
            "description": (
                "Fetch the contents of a web page by URL, e.g. to follow up "
                "on a web_search result. Read-only."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
        {
            "name": "current_time",
            "description": (
                "Get the current date and time as an ISO-8601 timestamp, so "
                "you can reason correctly about 'today' and recency."
            ),
            "input_schema": {"type": "object", "properties": {}},
        },
    ]

    def run(self, name: str, tool_input: dict) -> str:
        # A read-only tool must never crash the Turn — the worst case is a
        # wasted call, not damage (PRD user story 34). Any failure (a 403, a
        # missing path, a bad regex) comes back as a result the Agent can
        # read and react to, just like a successful one.
        try:
            return self._dispatch(name, tool_input)
        except Exception as exc:  # noqa: BLE001
            return f"{name} failed: {type(exc).__name__}: {exc}"

    def _dispatch(self, name: str, tool_input: dict) -> str:
        if name == "read_file":
            return self._read_file(tool_input["path"])
        if name == "list_dir":
            return self._list_dir(tool_input["path"])
        if name == "grep":
            return self._grep(tool_input["pattern"], tool_input["path"])
        if name == "web_search":
            return self._web_search(tool_input["query"])
        if name == "fetch_url":
            return self._web.fetch(tool_input["url"])
        if name == "current_time":
            return dt.datetime.now(dt.timezone.utc).isoformat()
        return f"unknown tool: {name}"

    def _read_file(self, path: str) -> str:
        resolved = self._workspace.resolve(path)
        with open(resolved, "rb") as f:
            raw = f.read(_MAX_FILE_BYTES + 1)
        if len(raw) > _MAX_FILE_BYTES:
            text = raw[:_MAX_FILE_BYTES].decode("utf-8", errors="replace")
            return f"{text}\n\n[truncated at {_MAX_FILE_BYTES} bytes]"
        return raw.decode("utf-8", errors="replace")

    def _list_dir(self, path: str) -> str:
        resolved = self._workspace.resolve(path)
        entries = []
        for name in sorted(os.listdir(resolved)):
            full = os.path.join(resolved, name)
            entries.append(name + "/" if os.path.isdir(full) else name)
        return "\n".join(entries)

    def _grep(self, pattern: str, path: str) -> str:
        rx = re.compile(pattern)
        base = self._workspace.resolve(path)
        if base.is_dir():
            files = [
                os.path.join(root, f)
                for root, _dirs, names in os.walk(base)
                for f in names
            ]
        else:
            files = [str(base)]
        root = self._workspace.root
        matches = []
        for fpath in sorted(files):
            # Defence in depth: a symlinked file inside the tree that points
            # out of the Workspace is skipped — confinement stays the
            # airlock's single responsibility, even mid-walk.
            try:
                self._workspace.resolve(os.path.relpath(fpath, root))
            except WorkspaceError:
                continue
            try:
                with open(fpath, encoding="utf-8", errors="replace") as fh:
                    for lineno, line in enumerate(fh, 1):
                        if rx.search(line):
                            rel = os.path.relpath(fpath, base)
                            matches.append(f"{rel}:{lineno}:{line.rstrip()}")
                            if len(matches) >= _MAX_GREP_MATCHES:
                                matches.append("[truncated]")
                                return "\n".join(matches)
            except OSError:
                continue
        return "\n".join(matches)

    def _web_search(self, query: str) -> str:
        results = self._web.search(query)
        return json.dumps(
            [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results]
        )
