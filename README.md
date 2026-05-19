# Employee Agent

A single-user personal AI assistant you talk to through a terminal (TUI) chat
interface. It can search its own memory of past sessions, work with files, run
code in a contained sandbox, and fetch from the web — while keeping the active
context (and therefore cost) bounded.

The "employee" name is product framing only. Architecturally this is a
**one-user** assistant — no teams, roles, or multi-actor hierarchy.

## What it does

- **Chat TUI** — a thin Textual shell; all behaviour lives in the agent loop.
- **Agent-pulled Recall** — the model decides when to `search_recall` /
  `get_conversation` over *past, finished* sessions. The live session is never
  in Recall until it ends.
- **Bounded context (Compaction)** — once hot context crosses a fraction of the
  model's window, the oldest turns are condensed into a running Summary and
  written toward Recall incrementally, so cost stays capped.
- **Sealing** — when you exit, the Conversation is closed, a final structured
  Summary is written, and remaining turns are indexed. Only Sealed
  Conversations become searchable.
- **Workspace** — the Agent's entire filesystem surface: a single durable
  directory it may read, write, and execute in, and nowhere else.
- **Sandboxed execution** — `run_command` runs in a pinned, network-less Docker
  container bind-mounted to the Workspace (containment, not isolation strength).

See `CONTEXT.md` for the precise domain language and `docs/adr/` for the
architectural decisions (single-process Python + SQLite, local embeddings,
RRF recall fusion, the sandbox model, etc.).

## Architecture at a glance

Single-process Python 3.13 + SQLite (`sqlite-vec` for vector search,
`fastembed` for local embeddings — no embedding API calls). The Anthropic API
drives the agent loop and summarisation; Docker contains only tool execution.

```
src/employee_agent/
  __main__.py   entrypoint: one launch == one new Conversation
  tui.py        Textual chat shell
  agent.py      the agent loop (the spine)
  compactor.py  bounded hot-context + incremental indexing
  summarizer.py structured Summary (prose + Requests + Outcomes)
  recall.py     seal-scoped search (vector + FTS, RRF fusion)
  store.py      SQLite persistence
  workspace.py  Workspace-confined file access
  sandbox.py    Docker-backed run_command
  tools.py      local tool surface (file/web/clock/run_command)
  config.py     all knobs (models, recall, compaction, sandbox) — nothing hardcoded
  llm.py / web.py / embedder.py   Anthropic + fastembed adapters
```

## Requirements

- Python **3.13** (`>=3.13,<3.14`)
- [`uv`](https://docs.astral.sh/uv/) for dependency / env management
- An `ANTHROPIC_API_KEY`
- Docker (only needed for `run_command` and the Docker-marked integration test;
  the app otherwise runs without it)

## Setup

```sh
uv sync                       # install runtime + dev dependencies

# Build the pinned sandbox image (tag must match Config.DEFAULT_SANDBOX["image"]).
docker build -t employee-agent-sandbox:1 -f docker/sandbox.Dockerfile docker/
```

## Running it

```sh
export ANTHROPIC_API_KEY=sk-...
uv run employee-agent
```

Exiting the TUI Seals the Conversation deterministically (final Summary written
+ indexed) before the process ends.

Environment overrides (all optional, sensible defaults):

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | — (required) | Anthropic API key; the app exits if unset |
| `EMPLOYEE_AGENT_DB` | `employee_agent.sqlite` | SQLite DB path (Recall + transcripts) |
| `EMPLOYEE_AGENT_WORKSPACE` | `workspace` | Workspace root (the Agent's only filesystem surface) |

Per-task models, recall budget (`k`, token ceiling, RRF `k`), compaction
thresholds, and sandbox limits (image tag, timeout, CPU, memory) are all in
`config.py` — never hardcoded in the loop.

## Testing

```sh
uv run pytest                 # full suite (74 tests)
uv run pytest -m "not docker" # skip the real-Docker integration test
uv run ty check               # whole-repo type check, zero-baseline
```

Notes:

- The single `docker`-marked test needs a reachable Docker daemon; it's
  auto-skipped otherwise.
- `ty` (pinned, ADR-0009) is **not** gated in pytest/CI — run it before
  landing. It checks `src/`, `tests/`, and `evals/` together so a test double
  can't silently drift from its real seam.

### Retrieval eval

A dev-only retrieval-quality harness lives outside the hermetic pytest suite
(ADR-0008). It builds a corpus from `evals/dataset.yaml` via the *real*
Store/Recall with real local embeddings (no LLM), runs probes, and prints a
scorecard with a pass/fail floor:

```sh
uv run python -m evals          # exit 0 = PASS, 1 = FAIL or malformed dataset
```

## Development

- Work directly on `master` — no feature branches.
- Issues are markdown files under `.scratch/<feature-slug>/`
  (`docs/agents/issue-tracker.md`).
- Domain language is single-source in `CONTEXT.md`; decisions in `docs/adr/`.
