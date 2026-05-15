"""Agent-loop integration — Recall end-to-end with all adapters faked.

Drives real Agents (faked LLM + Embedder) across two sessions and asserts
observable contracts: Sealing indexes the right units, and a fresh launch
recalls a prior Sealed Conversation with its date. Never asserts on model
phrasing (PRD Testing Decisions).
"""

import json

from employee_agent.agent import Agent
from employee_agent.config import Config
from employee_agent.llm import ToolCall
from employee_agent.recall import Recall
from employee_agent.store import Store

from fakes import TopicEmbedder, FakeLLMClient

_SUMMARY = json.dumps(
    {
        "prose": "User asked for a Q1 revenue report; Agent agreed.",
        "requests": ["Prepare the Q1 revenue report"],
        "outcomes": [],
    }
)


def _sealed_session(store, recall):
    llm = FakeLLMClient(
        replies=["Sure, I'll get that drafted.", _SUMMARY]
    )
    agent = Agent(llm=llm, store=store, config=Config(), recall=recall)
    agent.send("please prepare a report on Q1 revenue")
    agent.seal()
    return agent.conversation_id


def test_seal_indexes_user_turns_requests_and_summary_not_agent_turns(tmp_path):
    store = Store(tmp_path / "recall.sqlite")
    recall = Recall(store, TopicEmbedder(), Config())

    past_id = _sealed_session(store, recall)

    # The raw User Turn is recallable.
    assert recall.search("please prepare", k=6)[0].conversation_id == past_id
    # The extracted Request is its own recallable unit (ADR-0006).
    assert recall.search("Prepare the Q1 revenue report", k=6)[
        0
    ].conversation_id == past_id
    # The Summary is recallable.
    assert recall.search("agreed", k=6)[0].conversation_id == past_id
    # The Agent Turn is NOT an indexed unit (only User Turns + Requests + the
    # Summary are — _units_for / ADR-0006). Hybrid recall now surfaces related
    # units for any query (semantic arm), so we no longer assert emptiness;
    # instead the Agent's reply text must never appear as a hit snippet,
    # whatever we search for.
    agent_reply = "Sure, I'll get that drafted."
    snippets = [
        h.snippet
        for q in ("please prepare", "drafted", "Q1 revenue", "agreed", "report")
        for h in recall.search(q, k=6)
    ]
    assert snippets  # hybrid recall does surface related units
    assert agent_reply not in snippets


def test_fresh_launch_recalls_a_prior_sealed_conversation_with_its_date(tmp_path):
    store = Store(tmp_path / "recall.sqlite")
    recall = Recall(store, TopicEmbedder(), Config())

    past_id = _sealed_session(store, recall)
    past_date = store.get_conversation(past_id).started_at[:10]

    # A fresh launch — a new Conversation, recall is cross-session (ADR-0005).
    s2 = FakeLLMClient(
        replies=[
            ToolCall(id="t1", name="search_recall", input={"query": "Q1 revenue"}),
            "Answered from a past session.",
        ]
    )
    a2 = Agent(llm=s2, store=store, config=Config(), recall=recall)
    reply = a2.send("when did I ask you to prepare a report on something?")

    assert a2.conversation_id != past_id  # fresh launch = new Conversation

    # The dated hit for the prior Sealed Conversation was fed back to the
    # model: seal -> index -> cross-session search end-to-end.
    fed_back = json.dumps(s2.calls[1][0])
    assert past_date in fed_back
    assert str(past_id) in fed_back

    # The tool loop completed and returned the model's post-tool answer.
    assert reply == "Answered from a past session."


def _tool_result(messages):
    return next(
        block["content"]
        for msg in messages
        if msg["role"] == "user" and isinstance(msg["content"], list)
        for block in msg["content"]
        if block.get("type") == "tool_result"
    )


def test_search_recall_result_frames_hits_as_dated_past_sessions(tmp_path):
    store = Store(tmp_path / "recall.sqlite")
    recall = Recall(store, TopicEmbedder(), Config())
    past_id = _sealed_session(store, recall)
    past_date = store.get_conversation(past_id).started_at[:10]

    s2 = FakeLLMClient(
        replies=[
            ToolCall(id="t1", name="search_recall", input={"query": "Q1 revenue"}),
            "ok",
        ]
    )
    a2 = Agent(llm=s2, store=store, config=Config(), recall=recall)
    a2.send("when did I ask about the report?")

    # The tool result the model reasons over explicitly scopes results to
    # PAST Sealed Conversations (never the current one, ADR-0005) and dates
    # every hit, so the Agent distinguishes past from current without
    # guessing — without us asserting on the model's phrasing.
    payload = json.loads(_tool_result(s2.calls[1][0]))
    assert payload["scope"] == "past_sealed_conversations"
    assert payload["hits"]
    for hit in payload["hits"]:
        assert hit["session"] == "past"
        assert hit["date"] == past_date
        assert hit["conversation_id"] == past_id
