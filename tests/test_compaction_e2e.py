"""End-to-end: a long session stays bounded, then Seals and is recallable.

Drives a real Agent (faked LLM + Embedder) through a long Turn stream with a
tight Compaction window, asserts the context actually sent to the model never
blows the configured bound, then Seals and proves a Turn that was *compacted
out* mid-session is recallable from a fresh launch (ADR-0003's spine end to
end). Never asserts on model phrasing (PRD Testing Decisions).
"""

import json

from employee_agent.agent import Agent
from employee_agent.compactor import _estimate_tokens
from employee_agent.config import Config
from employee_agent.llm import Response
from employee_agent.recall import Recall
from employee_agent.store import Store

from fakes import TopicEmbedder

_SUMMARISE_SENTINEL = "Summarise this finished Conversation"
_SEAL_SUMMARY = json.dumps(
    {"prose": "A long session about many topics.", "requests": [], "outcomes": []}
)


class BranchingLLM:
    """One scripted-by-shape LLM seam: any Summarizer prompt (running or final)
    gets canned structured JSON; every agent-loop call gets a short reply.
    This makes the test independent of exactly when Compaction fires, while
    recording calls so the bound can be checked on what we'd really send."""

    def __init__(self):
        self.calls = []

    def complete(self, messages, model, *, tools=None):
        self.calls.append((messages, model, tools or []))
        if (
            len(messages) == 1
            and isinstance(messages[0]["content"], str)
            and messages[0]["content"].startswith(_SUMMARISE_SENTINEL)
        ):
            return Response(text=_SEAL_SUMMARY)
        return Response(text="Noted.")


def test_long_session_stays_bounded_then_seals_and_is_recallable(tmp_path):
    cfg = Config(
        compaction={
            "context_window": 400,
            "trigger_fraction": 0.5,  # trigger = 200 tokens
            "tail_token_budget": 120,
            "summary_token_cap": 60,
        }
    )
    store = Store(tmp_path / "recall.sqlite")
    recall = Recall(store, TopicEmbedder(), cfg)
    llm = BranchingLLM()
    agent = Agent(llm=llm, store=store, config=cfg, recall=recall)

    agent.send(
        "Please remember the secret pangolin manifest for the audit later."
    )
    for i in range(40):
        agent.send(
            f"Turn {i}: here is a chunk of conversation with enough words "
            f"to push the running hot context past its budget repeatedly."
        )

    # The bound holds on what we actually sent the model: every agent-loop
    # call's assembled context is under trigger_fraction * context_window.
    trigger = 0.5 * 400
    agent_loop_calls = [
        msgs
        for (msgs, _model, _tools) in llm.calls
        if not (
            len(msgs) == 1
            and isinstance(msgs[0]["content"], str)
            and msgs[0]["content"].startswith(_SUMMARISE_SENTINEL)
        )
    ]
    assert agent_loop_calls
    for msgs in agent_loop_calls:
        hot = sum(_estimate_tokens(m["content"]) for m in msgs)
        assert hot <= trigger, f"hot context blew the bound: {hot} > {trigger}"

    # The distinctive early Turn was compacted out: by the last exchange it
    # is no longer in the context we send the model (it lives in Recall now).
    assert not any("pangolin" in m["content"] for m in agent_loop_calls[-1])

    # Sealing closes the Conversation and writes the final Summary.
    past_id = agent.conversation_id
    agent.seal()
    sealed = store.get_conversation(past_id)
    assert sealed is not None
    assert sealed.sealed_at is not None

    # A fresh launch recalls the Turn that was compacted away mid-session:
    # compaction -> incremental index -> Seal flips searchability -> recall.
    recall2 = Recall(store, TopicEmbedder(), cfg)
    hits = recall2.search("pangolin manifest", k=6)
    assert hits and hits[0].conversation_id == past_id
