"""Agent tool loop — the agent-pulled recall surface (PRD Q8).

End-to-end through Agent.send with a faked LLMClient that scripts a tool
call. We assert the observable wiring contract: the recall tools are offered,
a tool call is executed and its result fed back, and Turn semantics are
preserved. We never assert on model phrasing.
"""

import json

from employee_agent.agent import Agent
from employee_agent.config import Config
from employee_agent.llm import ToolCall
from employee_agent.recall import Recall, Unit
from employee_agent.store import Store

from fakes import FakeEmbedder, FakeLLMClient


def _seed_past_conversation(store, recall):
    cid = store.start_conversation()
    store.add_turn(cid, 0, "user", "please prepare a report on Q1 revenue")
    store.add_turn(cid, 1, "agent", "done")
    store.seal_conversation(cid, "User asked for a Q1 revenue report.", [])
    recall.add_units(
        [Unit(cid, "user_turn", "please prepare a report on Q1 revenue", 0)]
    )
    return cid


def test_agent_offers_recall_tools_and_executes_a_tool_call(tmp_path):
    store = Store(tmp_path / "recall.sqlite")
    recall = Recall(store, FakeEmbedder(), Config())
    past_id = _seed_past_conversation(store, recall)

    llm = FakeLLMClient(
        replies=[
            ToolCall(id="t1", name="search_recall", input={"query": "revenue"}),
            "You asked about that earlier.",
        ]
    )
    agent = Agent(llm=llm, store=store, config=Config(), recall=recall)

    reply = agent.send("when did I ask about revenue?")

    # The model's post-tool text is what the User gets.
    assert reply == "You asked about that earlier."

    # Both recall tools are offered to the model on every call.
    offered = [{t["name"] for t in tools} for (_m, _model, tools) in llm.calls]
    assert offered and all(
        {"search_recall", "get_conversation"} <= names for names in offered
    )

    # The search_recall result was fed back into the follow-up call.
    followup_blob = json.dumps(llm.calls[1][0])
    assert str(past_id) in followup_blob and "revenue" in followup_blob

    # Turn semantics preserved: exactly the User Turn + the final Agent Turn.
    # Tool round-trips are intra-Turn hot-context mechanics, not Turns.
    turns = store.turns_of(agent.conversation_id)
    assert [(t.role, t.content) for t in turns] == [
        ("user", "when did I ask about revenue?"),
        ("agent", "You asked about that earlier."),
    ]
