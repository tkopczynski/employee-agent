"""Store contract regressions for the latent bugs ty surfaced (Issue 02).

Focused on `start_conversation`'s honest `-> int` contract: the happy path
returns a usable integer id, and the impossible-but-typed "INSERT produced no
lastrowid" case is an explicit, unrecoverable error rather than a silent
`None` leaking out under an `int` signature (ADR-0009).
"""

import pytest

from employee_agent.store import Store


def test_start_conversation_returns_a_usable_int_id(tmp_path):
    store = Store(tmp_path / "recall.sqlite")

    cid = store.start_conversation()

    # Honest `-> int`: a real integer, and it actually identifies the
    # Conversation that was just opened.
    assert isinstance(cid, int)
    conv = store.get_conversation(cid)
    assert conv is not None and conv.id == cid


def test_start_conversation_raises_when_no_lastrowid(tmp_path, monkeypatch):
    # The defensive contract: a started Conversation with no id is
    # unrecoverable, so `start_conversation` must raise — never return `None`
    # under its `-> int` signature. SQLite's AUTOINCREMENT always yields a
    # rowid, so this otherwise-impossible state is simulated by substituting
    # the connection; that is the only honest way to drive the invariant.
    store = Store(tmp_path / "recall.sqlite")

    class _NoRowidCursor:
        lastrowid = None

    class _NoRowidConn:
        def execute(self, *args, **kwargs):
            return _NoRowidCursor()

        def commit(self):
            pass

    monkeypatch.setattr(store, "_conn", _NoRowidConn())

    with pytest.raises(RuntimeError):
        store.start_conversation()
