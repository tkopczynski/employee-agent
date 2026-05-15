"""Sealing — the transition that closes a Conversation (CONTEXT.md).

Exercised as external behaviour: drive the Agent with a faked LLMClient, then
read the persisted Conversation back through the Store. We assert the Sealed
state and the readable structured Summary row, never model phrasing.
"""

import datetime as dt
import json

from employee_agent.agent import Agent
from employee_agent.config import Config
from employee_agent.recall import Recall
from employee_agent.store import Store

from fakes import TopicEmbedder, FakeLLMClient


def _make(tmp_path, summary_payload):
    store = Store(tmp_path / "recall.sqlite")
    llm = FakeLLMClient(replies=["Drafting the Q1 report now.", json.dumps(summary_payload)])
    recall = Recall(store, TopicEmbedder(), Config())
    agent = Agent(llm=llm, store=store, config=Config(), recall=recall)
    return agent, store, llm


def test_seal_sets_sealed_at(tmp_path):
    agent, store, _ = _make(tmp_path, {"prose": "User asked for Q1; Agent drafted it.", "requests": [], "outcomes": []})
    agent.send("draft the Q1 report")

    assert store.get_conversation(agent.conversation_id).sealed_at is None

    agent.seal()

    sealed_at = store.get_conversation(agent.conversation_id).sealed_at
    assert sealed_at is not None
    dt.datetime.fromisoformat(sealed_at)  # ISO-8601 (ADR-0001)


def test_seal_persists_readable_summary_and_is_idempotent(tmp_path):
    payload = {
        "prose": "User asked for the Q1 report; Agent drafted it.",
        "requests": ["Draft the Q1 report"],
        "outcomes": ["Q1 one-pager drafted", "Shared with finance"],
    }
    agent, store, llm = _make(tmp_path, payload)
    agent.send("draft the Q1 report")

    agent.seal()

    conv = store.get_conversation(agent.conversation_id)
    # Readable Summary row: prose as text, outcomes as a real list (ADR-0006).
    assert conv.summary_prose == "User asked for the Q1 report; Agent drafted it."
    assert conv.summary_outcomes == ["Q1 one-pager drafted", "Shared with finance"]

    calls_after_first_seal = len(llm.calls)
    agent.seal()  # a deterministic exit hook may fire again — harmless no-op

    # No second summarise call (cost), and the Sealed Summary is unchanged.
    assert len(llm.calls) == calls_after_first_seal
    conv2 = store.get_conversation(agent.conversation_id)
    assert conv2.summary_prose == conv.summary_prose
    assert conv2.sealed_at == conv.sealed_at
