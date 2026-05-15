"""Recall — the searchable store of Sealed Conversations (CONTEXT.md).

Exercised through Recall's public interface against a temporary SQLite file
with real FTS5 and a deterministic FakeEmbedder. We assert observable
contracts (what search returns for a known corpus, the seal-gate), never SQL,
vectors, or private state (PRD Testing Decisions).
"""

from employee_agent.config import Config
from employee_agent.recall import Recall, Unit
from employee_agent.store import Store

from fakes import FakeEmbedder


def _recall(tmp_path):
    store = Store(tmp_path / "recall.sqlite")
    return Recall(store, FakeEmbedder(), Config()), store


def test_keyword_finds_a_sealed_conversations_user_turn(tmp_path):
    recall, store = _recall(tmp_path)
    conv_id = store.start_conversation()
    store.add_turn(conv_id, 0, "user", "Please prepare a report on Q1 revenue")
    store.add_turn(conv_id, 1, "agent", "Sure, drafting it now.")
    store.seal_conversation(
        conv_id,
        "User asked for a Q1 revenue report; Agent drafted it.",
        ["Q1 one-pager drafted"],
    )
    recall.add_units(
        [
            Unit(
                conversation_id=conv_id,
                kind="user_turn",
                text="Please prepare a report on Q1 revenue",
                source_turn_id=0,
            )
        ]
    )

    hits = recall.search("revenue", k=6)

    assert len(hits) == 1
    hit = hits[0]
    assert hit.conversation_id == conv_id
    assert "revenue" in hit.snippet
    assert hit.summary_line == "User asked for a Q1 revenue report; Agent drafted it."
    # The Conversation's date (when the session happened), not sealed time.
    assert hit.date == store.get_conversation(conv_id).started_at[:10]


def test_units_are_not_searchable_until_the_conversation_is_sealed(tmp_path):
    recall, store = _recall(tmp_path)
    conv_id = store.start_conversation()
    store.add_turn(conv_id, 0, "user", "Please prepare a report on Q1 revenue")
    recall.add_units(
        [
            Unit(
                conversation_id=conv_id,
                kind="user_turn",
                text="Please prepare a report on Q1 revenue",
                source_turn_id=0,
            )
        ]
    )

    # Unsealed (the live session) — the seal-gate keeps it out of Recall.
    assert recall.search("revenue", k=6) == []

    store.seal_conversation(conv_id, "User asked for a Q1 revenue report.", [])

    # Same query, same units — searchable only now that it is Sealed.
    hits = recall.search("revenue", k=6)
    assert [h.conversation_id for h in hits] == [conv_id]


def test_request_and_summary_units_are_searchable_not_only_user_turns(tmp_path):
    recall, store = _recall(tmp_path)
    conv_id = store.start_conversation()
    store.seal_conversation(conv_id, "Recap of the session.", [])
    recall.add_units(
        [
            Unit(conv_id, "request", "Draft the quarterly compliance audit"),
            Unit(conv_id, "summary", "User discussed onboarding the new vendor"),
        ]
    )

    # The extracted Request is retrievable on its own (ADR-0006).
    assert "compliance" in recall.search("compliance", k=6)[0].snippet
    # So is the Summary unit.
    assert "vendor" in recall.search("vendor", k=6)[0].snippet


def test_get_conversation_returns_full_ordered_transcript_both_roles(tmp_path):
    recall, store = _recall(tmp_path)
    conv_id = store.start_conversation()
    store.add_turn(conv_id, 0, "user", "what is our refund policy")
    store.add_turn(conv_id, 1, "agent", "30 days, no questions asked")
    store.add_turn(conv_id, 2, "user", "and for digital goods")
    store.add_turn(conv_id, 3, "agent", "14 days for digital goods")
    store.seal_conversation(conv_id, "Discussed refund policy.", [])

    transcript = recall.get_conversation(conv_id)

    # Full transcript: both roles, in seq order — bounded recall is not lossy.
    assert [(t.role, t.content) for t in transcript] == [
        ("user", "what is our refund policy"),
        ("agent", "30 days, no questions asked"),
        ("user", "and for digital goods"),
        ("agent", "14 days for digital goods"),
    ]


def _seal(store, *unit_texts, prose="recap"):
    conv_id = store.start_conversation()
    store.seal_conversation(conv_id, prose, [])
    return conv_id


def test_search_yields_one_ranked_hit_per_conversation(tmp_path):
    recall, store = _recall(tmp_path)
    # Conversation A: the term appears across two units (more relevant).
    a = _seal(store, prose="Scaling work")
    recall.add_units(
        [
            Unit(a, "user_turn", "how do I scale kubernetes pods"),
            Unit(a, "request", "set up kubernetes autoscaling"),
        ]
    )
    # Conversation B: the term appears once, buried in a long unit.
    b = _seal(store, prose="Misc planning")
    recall.add_units(
        [
            Unit(
                b,
                "user_turn",
                "a long note about budgets travel logistics scheduling "
                "and kubernetes among many other unrelated topics here",
            )
        ]
    )

    hits = recall.search("kubernetes", k=6)

    # One hit per Conversation — A is not returned twice for its two units.
    assert [h.conversation_id for h in hits] == [a, b]
    # The more-relevant Conversation ranks first; its snippet is a matching
    # unit from that Conversation.
    assert hits[0].conversation_id == a
    assert "kubernetes" in hits[0].snippet


def test_k_caps_the_number_of_conversations_returned(tmp_path):
    recall, store = _recall(tmp_path)
    for _ in range(3):
        cid = _seal(store)
        recall.add_units([Unit(cid, "user_turn", "deploy the staging environment")])

    # Three Sealed Conversations match, but the budget asks for two.
    hits = recall.search("staging", k=2)

    assert len(hits) == 2
    assert len({h.conversation_id for h in hits}) == 2
