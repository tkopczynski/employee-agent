# ty as the type checker

We type-check the whole repo (`src` + `tests` + `evals`) with **ty** (Astral),
chosen over mypy — the obvious default — for its uv-native fit and Rust speed,
accepting that ty is pre-1.0/preview as of 2026-05. The bare seam constructors
get annotated; `tests/fakes.py` is in scope so a Fake drifting from the real
seam is caught.

## Considered Options

- **mypy** — the de-facto standard, stable, mature `# type: ignore[code]`
  ecosystem. Rejected as primary because the uv-native ergonomics and speed of
  ty mattered more here than maturity for a 2k-LOC single-user repo; recorded
  because picking a preview tool over the standard is otherwise surprising.
- **pyright** — fast, strong inference, but drags a Node/npm toolchain into an
  otherwise pure-Python/uv repo.

## Consequences

- **Pinned, not floating.** ty is preview and churns; it is pinned in
  `[dependency-groups] dev` (not run via `uvx`) so validation is reproducible.
  Expect periodic pin bumps and occasional re-triage as ty evolves.
- **ty has no `--strict` umbrella.** "Proper type hints" means *annotate the
  bare signatures and hold a clean zero baseline*, not satisfy a strict switch.
- **Zero baseline, but non-enforced by choice.** Validation is a standalone
  `uv run ty check` documented in CLAUDE.md — deliberately *not* gated in
  pytest/CI (no CI exists; single-user repo, work-on-master house style). The
  zero baseline can therefore rot between manual runs; folding ty into
  `uv run pytest` later is a one-file add if that becomes painful.
- **`Config` backing dicts are `dict[str, Any]`.** The eight `Config` property
  return annotations (`-> int/float/str`) are consequently *unverified
  assertions* — a wrong-typed config value surfaces downstream at the use site,
  not the cause. Accepted as a localized concession: the `Config` property
  facade isolates it, so upgrading to typed config sections later needs zero
  caller changes.
- **The seam's vendor isolation wins over zero ignores.** Inbound Anthropic
  blocks are narrowed properly; the outbound `Messages.create` call carries a
  localized `# ty: ignore[...]` rather than leaking `MessageParam` types into
  the `LLMClient` seam, whose stated contract is that no Anthropic types leak.
