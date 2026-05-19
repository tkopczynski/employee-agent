# 01 — ty toolchain + seam-Protocol vertical (tracer)

Status: ready-for-agent

## Parent

Decision record: ADR-0009 (ty as the type checker). Seam-typing convention:
"a seam gets a `typing.Protocol` iff it has a substituted Fake double;
otherwise consumers are annotated with the concrete class" — the ADR for this
rule was deliberately declined, so it is recorded only in agent memory, not
in-repo. This tracer slice establishes the tool and the convention end to end.

## What to build

The architecturally load-bearing slice: stand up ty as the pinned, configured
checker and drive the seam vertical — the central abstraction of this codebase
— to clean, with the test doubles in scope so a Fake drifting from its real
seam is a type error.

End-to-end behaviour: ty is pinned at an exact version in the `dev` dependency
group (not run via floating `uvx` — ADR-0009 requires reproducible
validation) and `[tool.ty]` in `pyproject.toml` scopes a whole-repo check
(`src` + `tests` + `evals`) on the project's Python 3.13 environment.
`Recall` and `Summarizer` each gain a one-method-surface `typing.Protocol`
co-located with the class (the house seam pattern already used for
`LLMClient`/`WebClient`/`Sandbox`/`Embedder`), and their concrete classes
structurally satisfy it. The bare consumer constructors `Agent.__init__`,
`Recall.__init__`, and `Compactor.__init__` get their seam parameters
annotated: the Protocol type for `llm` / `web` / `sandbox` / `embedder` /
`recall` / `summarizer`, and the concrete class for `store` / `config` (no
Fake double exists for those — real instances are used in tests, so there is
nothing to keep in sync). Because `tests/fakes.py` is in ty's scope,
`FakeRecall` and `FakeSummarizer` are now checked against the new Protocols:
a deliberate drift between a Fake and its real seam becomes a ty diagnostic,
which is the highest-value catch this whole effort buys.

ADR-0009 and the CLAUDE.md `uv run ty check` line already exist (uncommitted
from the design session) — verify they are present and correct rather than
duplicating them. This slice intentionally does **not** reach a zero baseline:
the Config typed-escape, the vendor-boundary items, the test `None`-guards, and
the three latent bug fixes are out of scope here (slices 02 and 03). It also
does **not** do the typed-config-sections refactor — ADR-0009 records the
`dict[str, Any]` escape as the chosen path (slice 03).

## Acceptance criteria

- [x] ty is pinned at an exact version in `[dependency-groups] dev`; it is **not** invoked via `uvx` anywhere
- [x] `[tool.ty]` in `pyproject.toml` configures a whole-repo check over `src` + `tests` + `evals` on Python 3.13; `uv run ty check` runs the pinned tool
- [x] ADR-0009 exists and the CLAUDE.md `uv run ty check` line is present (verified, not duplicated)
- [x] `Recall` and `Summarizer` each have a `typing.Protocol` co-located with the class, per the house seam pattern; the concrete classes structurally satisfy them
- [x] `Agent.__init__`, `Recall.__init__`, `Compactor.__init__` have all seam parameters annotated: Protocol for `llm`/`web`/`sandbox`/`embedder`/`recall`/`summarizer`; concrete class for `store`/`config` — see Comments re: `Agent.recall` (convention-faithful resolution of a spec ambiguity)
- [x] `FakeRecall` and `FakeSummarizer` structurally satisfy the new Protocols under ty; a hand-introduced signature drift on either Fake produces a ty diagnostic (sanity-checked, then reverted)
- [x] Zero seam-related diagnostics remain (no `unresolved-attribute` / `invalid-argument-type` on annotated seam parameters); the remaining non-seam diagnostic categories are still present and explicitly allowed at this slice
- [x] No typed-config-sections refactor, no vendor-edge change, no bug fix, no test `None`-guard in this slice
- [x] `uv run pytest` stays green

## Blocked by

None - can start immediately

## Comments

**Done (2026-05-19).** Implemented TDD, vertical slices: (1) pinned
`ty==0.0.37` in `[dependency-groups] dev` + `[tool.ty]` (`environment.python-version
= "3.13"`, `src.include = ["src","tests","evals"]`); (2) `SummarizerLike`
co-located in `summarizer.py`; (3) `RecallSink` co-located in `recall.py`;
(4) annotated the three constructors. For slices 2–3 the seam contract's teeth
were proven the TDD way: a deliberate return-type drift on `FakeSummarizer`
and `FakeRecall` each produced a fresh `invalid-argument-type` at the
`Compactor(...)` substitution site ("type `FakeRecall` is not assignable to
protocol `RecallSink`"), then reverted.

**Spec ambiguity resolved (user-approved, "Convention-faithful").** The
acceptance bullet lists `recall` under "Protocol", but the issue also requires
a single co-located *one-method-surface* Protocol that `FakeRecall` (which
implements only `add_units`) satisfies, with zero seam diagnostics. Those
can't all hold literally: `Agent` calls `recall.search`/`get_conversation`, so
a one-method Protocol on `Agent.recall` would be `unresolved-attribute`. Per
the **Parent** convention ("Protocol iff a substituted Fake exists; otherwise
the concrete class"), `Agent` never substitutes a Fake for `recall` (always a
real `Recall`), so `Agent.recall: Recall` (concrete); `Compactor.recall:
RecallSink` (Protocol — that's where `FakeRecall` lives). `RecallSink` is
narrow (`add_units` only) as the issue states. Naming: concrete classes keep
`Recall`/`Summarizer` (no rename — out of scope), so the Protocols are
`RecallSink`/`SummarizerLike`.

**Scope held.** `conversation_id`/`token_counter` left bare (not seam params;
annotating `token_counter` over-constrained the injected `len` counter and
regressed — reverted). Final: `uv run ty check` = 17 diagnostics, all
pre-existing non-seam categories (Config typed-escape, vendor boundary,
test/Fake None-guards) explicitly deferred to slices 02/03; zero on any
annotated seam parameter. `uv run pytest` = 61 passed, 5 skipped (Docker).
