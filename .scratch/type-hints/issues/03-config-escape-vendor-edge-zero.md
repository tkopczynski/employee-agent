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

- [ ] `Config` backing dicts annotated `dict[str, Any]`; the eight Config `invalid-return-type` diagnostics are gone; the `Config` property return annotations are unchanged
- [ ] The `WebClient` web-search path narrows on the Anthropic block type properly; no `# ty: ignore` on the inbound vendor path
- [ ] The outbound `Messages.create` call has exactly one `# ty: ignore[...]` with an explanatory comment; a repo-wide search confirms it is the **only** ty-ignore present
- [ ] The three `Conversation | None` test sites guard the optional before attribute access
- [ ] All remaining bare signatures across `src`, `tests`, and `evals` are annotated
- [ ] Whole-repo `uv run ty check` exits 0 with zero diagnostics
- [ ] `uv run pytest` stays green

## Blocked by

- `.scratch/type-hints/issues/01-ty-toolchain-and-seam-protocols.md`
- `.scratch/type-hints/issues/02-fix-three-latent-bugs.md`

(The zero baseline cannot hold until the seam annotations and the three bug
fixes have resolved their diagnostics.)
