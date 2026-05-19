# 03 — Config Any-escape + vendor edge + drive ty to zero

Status: ready-for-agent

## Parent

Decision record: ADR-0009 (ty as the type checker) — this slice realises its
recorded consequences: the `Config` `dict[str, Any]` escape, the
"narrow inbound / ignore outbound" vendor-boundary policy, and the clean
zero baseline that makes `uv run ty check` meaningful.

## What to build

Close out every remaining diagnostic and land the whole-repo zero baseline.

End-to-end behaviour: the `Config` backing dicts are annotated
`dict[str, Any]` (the eight `invalid-return-type` Config diagnostics vanish);
the `Config` property return annotations (`-> int` / `-> float` / `-> str`)
are deliberately **unchanged** — ADR-0009 records that the property facade
localizes and isolates this escape, so a future upgrade to typed config
sections needs no caller changes. The `WebClient` web-search path narrows on
the Anthropic block type properly — mirroring the inbound `b.type == ...`
pattern the `LLMClient` adapter already uses — so the inbound vendor edge is
type-checked with **no** suppression. The single outbound
`Messages.create` call carries exactly one localized `# ty: ignore[...]`
with an explanatory comment; this preserves the `LLMClient` seam's documented
contract that no Anthropic types leak into it, and is the only ty-ignore in
the entire repo. The three `Conversation | None` sites in the test suite
guard the optional before attribute access. Every remaining bare signature
across `src`, `tests`, and `evals` is annotated. The result is a whole-repo
`uv run ty check` that exits 0 with zero diagnostics.

## Acceptance criteria

- [x] `Config` backing dicts annotated `dict[str, Any]`; the eight Config `invalid-return-type` diagnostics are gone; the `Config` property return annotations are unchanged
- [x] The `WebClient` web-search path narrows on the Anthropic block type properly; no `# ty: ignore` on the inbound vendor path
- [x] The outbound `Messages.create` call has exactly one `# ty: ignore[...]` with an explanatory comment; a repo-wide search confirms it is the **only** ty-ignore present
- [x] The three `Conversation | None` test sites guard the optional before attribute access
- [x] All remaining bare signatures across `src`, `tests`, and `evals` are annotated — see Comments re: user-scoped test-body hold (convention-faithful resolution)
- [x] Whole-repo `uv run ty check` exits 0 with zero diagnostics
- [x] `uv run pytest` stays green

## Blocked by

- `.scratch/type-hints/issues/01-ty-toolchain-and-seam-protocols.md`
- `.scratch/type-hints/issues/02-fix-three-latent-bugs.md`

(The zero baseline cannot hold until the seam annotations and the three bug
fixes have resolved their diagnostics.)

## Comments

**Done (2026-05-19).** TDD, vertical slices, one commit each; diagnostic
burn-down 13 → 12 → 5 → 4 → 1 → 0. `uv run ty check` = "All checks passed!"
(exit 0); `uv run pytest` = 67 passed, 5 skipped (Docker).

- **Config Any-escape.** The five backing-dict *attributes* annotated
  `dict[str, Any]`; `__init__` fully annotated. ty 0.0.37 reports **seven**
  Config `invalid-return-type`, not eight — the bare `compaction: dict`
  param had masked one; annotating the param resolved it too, so all are
  gone. The 13 property return annotations (`-> int/float/str`) are
  byte-for-byte unchanged, exactly as ADR-0009 records.

- **Inbound vendor edge — spec-detail resolved (user-approved,
  "Narrowing only, no test").** The issue asks to mirror the LLMClient
  `b.type == "..."` pattern. ty 0.0.37 does **not** narrow this concrete
  15-member Anthropic content-block union on the `.type` literal
  discriminant (verified: both `!=`+`continue` and positive `==` failed;
  the llm.py precedent only type-checks because its `resp` is `Unknown`
  from an unresolved overload). Convention-faithful resolution per the
  ADR's intent ("inbound blocks narrowed properly ... no suppression"):
  `isinstance(block, WebSearchToolResultBlock)` — the tool-supported
  equivalent — plus an `isinstance` off the `WebSearchToolResultError`
  arm; result fields read directly (no `getattr`). No `# ty: ignore`.
  Behaviour-preserving for well-formed responses; a
  `WebSearchToolResultError` is now skipped cleanly rather than crashing
  the iteration.

- **Outbound suppression.** One `# ty: ignore[no-matching-overload]` on
  the llm.py `Messages.create` call, with the ADR-0009 rationale in a
  comment. Repo-wide grep confirms it is the **only** ty-ignore directive.
  Gotcha recorded: ty's directive scanner treats *any* `# ty: ignore`
  substring in prose as a real directive, so the explanatory comment
  avoids the literal token (a phantom directive otherwise injected a
  spurious `invalid-argument-type`).

- **Bare-signature sweep — scope resolved (user-approved, "src + evals +
  diagnostic only").** Criterion 5's literal text says *src, tests, and
  evals*. Per explicit user direction the ~109 purely-mechanical test
  bodies (`test_*(tmp_path) -> None`) were left bare; the 22 `src` + 5
  `evals` signatures + `FakeLLMClient` (the lone diagnostic site,
  `fakes.py:35`) are annotated. `FakeLLMClient` is now typed to
  structurally satisfy the `LLMClient` Protocol seam. scoring.py's
  docstring-documented Probe/Floor duck types were formalized as
  co-located Protocols (the house seam pattern). **Scope held** on
  `Summarizer.summarize(turns)` / `SummarizerLike.summarize(turns)`:
  their in-code rationale (lines 40–41 — Store `Turn`s and transient
  `_Msg`s passed interchangeably) deliberately keeps `turns` bare;
  annotating it needs a new shared type (out of scope), mirroring
  Issue 01's `token_counter` scope-hold precedent.

- **4th latent bug surfaced & fixed test-first.** Honestly typing
  `LocalTools.web: WebClient | None` made ty surface a bug of the exact
  `run_command`/no-Sandbox family (ADR-0009's whole premise): `fetch_url`
  / `web_search` with no `WebClient` wired leaked
  `AttributeError: 'NoneType'` as the tool result and corrupted the Turn.
  Fixed per the repo's TDD norm — failing regression test
  (`test_web_tools_with_no_web_client_wired_are_clean_tool_errors`),
  then the Issue-02-pattern clean tool-level error guards (no
  suppression). `_fetch_url` extracted so both web tools follow the
  one-method-per-tool house style. This is why pytest is 67, not 66.
