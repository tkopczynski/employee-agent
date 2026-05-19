## Development

- Run tests with `uv run pytest`.
- Type-check with `uv run ty check` (ty is pinned in dev deps; ADR-0009).
  Whole-repo zero-baseline — not gated in pytest/CI, so run it before landing.
- Work directly on the `master` branch — no feature branches needed.

## Agent skills

### Issue tracker

Issues live as markdown files under `.scratch/<feature-slug>/` in this repo. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` live at the repo root. See `docs/agents/domain.md`.
