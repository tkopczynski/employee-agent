"""Summarizer contract — driven by a deterministic faked LLMClient.

These tests assert the *structure* of the produced Summary (ADR-0006: prose
recap + discrete Requests + Outcomes) and that the cheaper `summarise` model
is used. They never assert model phrasing — the FakeLLMClient returns the
scripted JSON, so what is under test is the Summarizer's parse/normalise
contract, not wording.
"""

import json

from employee_agent.config import Config
from employee_agent.store import Turn
from employee_agent.summarizer import Summarizer

from fakes import FakeLLMClient


def _turns():
    return [
        Turn(seq=0, role="user", content="Draft a Q1 report", created_at="2026-05-15T00:00:00+00:00"),
        Turn(seq=1, role="agent", content="Done — drafted the Q1 one-pager", created_at="2026-05-15T00:00:01+00:00"),
    ]


def test_summarize_returns_summary_with_prose(tmp_path):
    llm = FakeLLMClient(
        replies=[json.dumps({"prose": "User asked for a Q1 report; Agent drafted it.", "requests": [], "outcomes": []})]
    )
    summarizer = Summarizer(llm=llm, config=Config())

    summary = summarizer.summarize(_turns())

    assert isinstance(summary.prose, str)
    assert summary.prose == "User asked for a Q1 report; Agent drafted it."


def test_summarize_uses_the_summarise_model_not_the_agent_loop_model():
    reply = json.dumps({"prose": "recap", "requests": [], "outcomes": []})

    llm = FakeLLMClient(replies=[reply])
    Summarizer(llm=llm, config=Config()).summarize(_turns())
    _, model_used = llm.calls[-1]
    assert model_used == "claude-haiku-4-5"  # default `summarise` model, not agent_loop

    # Overriding only the summarise entry changes the model — proves it is
    # resolved from the per-task map, never hardcoded.
    llm2 = FakeLLMClient(replies=[reply])
    cfg = Config(models={"summarise": "claude-haiku-4-5-cheap"})
    Summarizer(llm=llm2, config=cfg).summarize(_turns())
    _, model_used2 = llm2.calls[-1]
    assert model_used2 == "claude-haiku-4-5-cheap"


def test_requests_and_outcomes_are_always_lists_even_when_absent_or_null():
    # A Conversation with no requests: the model omits/ nulls the keys. The
    # Summary must still expose empty lists, never None or a bare string.
    reply = json.dumps({"prose": "Just small talk, nothing asked.", "requests": None})

    summary = Summarizer(llm=FakeLLMClient(replies=[reply]), config=Config()).summarize(_turns())

    assert summary.requests == []
    assert summary.outcomes == []
    assert isinstance(summary.requests, list)
    assert isinstance(summary.outcomes, list)


def test_requests_and_outcomes_are_discrete_and_normalised():
    # Raw model output is noisy: padded entries, blank/whitespace entries, and
    # exact duplicates. ADR-0006 wants discrete, normalised units so each one
    # is a clean Recall match — strip, drop empties, dedupe, preserve order.
    reply = json.dumps(
        {
            "prose": "  User asked for a report and a review.  ",
            "requests": ["  Draft the Q1 report  ", "Draft the Q1 report", "", "   ", "Schedule a review"],
            "outcomes": ["Q1 one-pager drafted", "Q1 one-pager drafted", "  Review booked  "],
        }
    )

    summary = Summarizer(llm=FakeLLMClient(replies=[reply]), config=Config()).summarize(_turns())

    assert summary.requests == ["Draft the Q1 report", "Schedule a review"]
    assert summary.outcomes == ["Q1 one-pager drafted", "Review booked"]
    assert summary.prose == "User asked for a report and a review."


def test_unparseable_model_output_degrades_gracefully():
    # If the summarise model ignores the JSON instruction, Sealing must still
    # complete — keep the raw text as prose, no structured lists, never raise.
    reply = "Sorry, I can't do JSON. Recap: user asked about Q1 and we talked."

    summary = Summarizer(llm=FakeLLMClient(replies=[reply]), config=Config()).summarize(_turns())

    assert summary.prose == reply
    assert summary.requests == []
    assert summary.outcomes == []
