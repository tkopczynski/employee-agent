# Single-process Python application with SQLite for Recall

The Employee Agent is a single-user pet project where the interesting work lives in domain logic — Conversation lifecycle, Recall, summarisation, hybrid search ranking, prompt design — not infrastructure. We chose Python 3 with Textual for the TUI, and a single SQLite database file (with `sqlite-vec` for vector search and FTS5 for keyword search) as the only datastore. This keeps the whole application in one process with no Docker dependency, makes Recall trivially inspectable and backup-able as a single file, and avoids learning a vector DB's ops model on top of the agent itself.

Rejected alternatives: Qdrant (purpose-built vector DB, but adds Docker + a network hop for no benefit at single-user scale); Postgres + pgvector (heaviest; adds two unrelated learning curves); FTS5-only without vectors (would miss fuzzy paraphrases like "draft a one-pager" matching "prepare a report").

Revisit when: Recall grows past tens of thousands of Turns and SQLite + sqlite-vec starts straining; or when the planned C-band capabilities (writes, side effects) require out-of-process tool sandboxing.

> Partially superseded by [ADR-0007](./0007-band-c-sandboxed-workspace.md): the "C-band sandboxing" trigger above has fired. The no-Docker clause is superseded **for tool execution only** — the application itself remains single-process Python + SQLite; only the Workspace's read/write/execute runs in a container.
