# 02 — Fix the 3 real latent bugs ty surfaced (TDD)

Status: ready-for-agent

## Parent

Decision record: ADR-0009 (ty as the type checker). ty surfaced these three
as genuine latent runtime defects, not annotation gaps; ADR-0009's premise
("ty's value is catching this class of bug") depends on them being fixed, not
suppressed. Same family as the recorded latent `Recall.search` FTS5 defect.

## What to build

Fix the three real runtime bugs ty exposed, each test-first per the repo's TDD
norm (a failing regression test before the fix). These are behavioural
changes, independent of the seam/annotation work, and independent of each
other — different code paths.

1. **`Store.start_conversation` honest `int` return.** It returns the
   SQLite cursor `lastrowid`, which is `int | None`, while the signature
   promises `-> int`. Handle the `None` case explicitly (raise a clear error
   — a started Conversation with no id is unrecoverable) so the return is
   honestly an `int`. Regression test drives the contract.

2. **Sandbox timeout yields `str`, never `bytes`.** On a command wall-clock
   timeout, the `subprocess` exception's captured `stdout`/`stderr` are
   `bytes`, so the resulting `ExecResult` carries `bytes` where `str` is
   declared — corrupting the tool result the Agent sees on a timed-out
   command. Decode to text so `ExecResult.stdout`/`stderr` are always `str`.
   Regression test exercises the timeout path (containment semantics of
   ADR-0007 unchanged — a timeout is still a *result*, not a crash).

3. **`run_command` without a wired Sandbox is a clean tool error.**
   `Agent` accepts `sandbox=None`; invoking the `run_command` tool in that
   state currently calls `.run` on `None` and crashes the Turn with an
   `AttributeError`. It must instead return a clean tool-level error result
   so the Turn survives. Regression test asserts the clean error, not a
   raised exception.

After each fix the corresponding ty diagnostic disappears. No Protocol
extraction or signature-annotation work here — that is slice 01; this slice is
purely the three behavioural fixes plus their tests.

## Acceptance criteria

- [ ] Each fix is committed test-first: a regression test that fails before the change and passes after
- [ ] `Store.start_conversation` never returns `None`; the no-`lastrowid` case raises a clear, specific error; a test drives both the happy path and the failure contract
- [ ] On a command timeout, `ExecResult.stdout` and `ExecResult.stderr` are `str` (decoded), never `bytes`; a regression test exercises the timeout path and asserts text
- [ ] Invoking `run_command` with no Sandbox wired returns a clean tool-error result and the Turn completes; a regression test asserts this (no `AttributeError` escapes)
- [ ] The three corresponding ty diagnostics (`invalid-return-type` on `start_conversation`, `invalid-argument-type` in the sandbox timeout path, `unresolved-attribute` on the optional sandbox seam) are gone
- [ ] `uv run pytest` stays green; no signature/Protocol annotation changes in this slice

## Blocked by

None - can start immediately (parallel with slice 01). Note: the `run_command`
bug fix reads more cleanly once slice 01 types the seam as `Sandbox | None`
rather than `Unknown | None`, but the behavioural fix and its test do not
depend on it.
