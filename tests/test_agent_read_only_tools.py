"""Agent read-only tool surface (PRD Q9, Issue 05).

End-to-end through Agent.send with a faked LLMClient that scripts a tool
call, mirroring test_agent_tools.py. We assert the observable wiring
contract: the read-only tools are offered, a scripted tool call is executed
and its result fed back into the follow-up call, and the model's post-tool
text is what the User gets. Network tools go through a faked WebClient so
tests stay offline (PRD Testing Decisions). We never assert on model phrasing.
"""

import datetime as dt
import json

from employee_agent.agent import Agent
from employee_agent.config import Config
from employee_agent.llm import ToolCall
from employee_agent.recall import Recall
from employee_agent.store import Store

from fakes import TopicEmbedder, FakeLLMClient, FakeWebClient


def _make_agent(tmp_path, replies, web=None):
    store = Store(tmp_path / "recall.sqlite")
    cfg = Config()
    recall = Recall(store, TopicEmbedder(), cfg)
    llm = FakeLLMClient(replies=replies)
    agent = Agent(
        llm=llm, store=store, config=cfg, recall=recall, web=web or FakeWebClient()
    )
    return agent, store, llm


def test_local_file_question_routes_to_read_file_and_grounds_the_reply(tmp_path):
    doc = tmp_path / "notes.txt"
    doc.write_text("the launch code is hunter2")

    agent, store, llm = _make_agent(
        tmp_path,
        replies=[
            ToolCall(id="t1", name="read_file", input={"path": str(doc)}),
            "Your notes say the launch code is hunter2.",
        ],
    )

    reply = agent.send("what does notes.txt say?")

    assert reply == "Your notes say the launch code is hunter2."

    # read_file is offered to the model on every call.
    offered = [{t["name"] for t in tools} for (_m, _model, tools) in llm.calls]
    assert offered and all("read_file" in names for names in offered)

    # The file's contents were fed back into the follow-up call.
    followup_blob = json.dumps(llm.calls[1][0])
    assert "the launch code is hunter2" in followup_blob

    # Turn semantics preserved: only the User Turn + final Agent Turn persist.
    turns = store.turns_of(agent.conversation_id)
    assert [(t.role, t.content) for t in turns] == [
        ("user", "what does notes.txt say?"),
        ("agent", "Your notes say the launch code is hunter2."),
    ]


def test_list_dir_routes_and_feeds_entries_back(tmp_path):
    (tmp_path / "alpha.txt").write_text("a")
    (tmp_path / "sub").mkdir()

    agent, _store, llm = _make_agent(
        tmp_path,
        replies=[
            ToolCall(id="t1", name="list_dir", input={"path": str(tmp_path)}),
            "The directory has alpha.txt and a sub folder.",
        ],
    )

    reply = agent.send("what's in that folder?")

    assert reply == "The directory has alpha.txt and a sub folder."
    followup_blob = json.dumps(llm.calls[1][0])
    assert "alpha.txt" in followup_blob and "sub" in followup_blob


def test_grep_routes_and_feeds_matching_lines_back(tmp_path):
    (tmp_path / "a.txt").write_text("nothing here\nTODO: fix the bug\nmore\n")
    (tmp_path / "b.txt").write_text("clean file\n")

    agent, _store, llm = _make_agent(
        tmp_path,
        replies=[
            ToolCall(
                id="t1",
                name="grep",
                input={"pattern": "TODO", "path": str(tmp_path)},
            ),
            "There is one TODO, in a.txt.",
        ],
    )

    reply = agent.send("any TODOs in my files?")

    assert reply == "There is one TODO, in a.txt."
    followup_blob = json.dumps(llm.calls[1][0])
    assert "a.txt" in followup_blob and "TODO: fix the bug" in followup_blob
    # Non-matching content is not dragged into context.
    assert "clean file" not in followup_blob


def test_web_search_then_fetch_url_follows_a_result(tmp_path):
    web = FakeWebClient(
        results={
            "textual python release": [
                ("Textual 1.0", "https://example.com/textual", "released"),
            ]
        },
        pages={"https://example.com/textual": "Textual 1.0 shipped on 2026-04-01."},
    )
    agent, _store, llm = _make_agent(
        tmp_path,
        web=web,
        replies=[
            ToolCall(id="s1", name="web_search", input={"query": "textual python release"}),
            ToolCall(
                id="f1",
                name="fetch_url",
                input={"url": "https://example.com/textual"},
            ),
            "Textual 1.0 shipped on 2026-04-01.",
        ],
    )

    reply = agent.send("when did Textual 1.0 ship?")

    assert reply == "Textual 1.0 shipped on 2026-04-01."
    # Both web tools routed through the WebClient seam (offline).
    assert web.searched == ["textual python release"]
    assert web.fetched == ["https://example.com/textual"]
    # The search result URL was visible to the model, and the fetched page
    # text was fed back before the final reply.
    after_search = json.dumps(llm.calls[1][0])
    assert "https://example.com/textual" in after_search
    after_fetch = json.dumps(llm.calls[2][0])
    assert "Textual 1.0 shipped on 2026-04-01." in after_fetch


def test_current_time_feeds_back_a_parseable_iso_timestamp(tmp_path):
    agent, _store, llm = _make_agent(
        tmp_path,
        replies=[
            ToolCall(id="c1", name="current_time", input={}),
            "It's the 15th today.",
        ],
    )

    before = dt.datetime.now(dt.timezone.utc)
    reply = agent.send("what's today's date?")
    after = dt.datetime.now(dt.timezone.utc)

    assert reply == "It's the 15th today."
    # The tool result fed back is a real, current, ISO-8601 timestamp so the
    # Agent can reason about recency (ADR-0001 timestamp format).
    result = llm.calls[1][0][-1]["content"][0]["content"]
    now = dt.datetime.fromisoformat(result)
    assert before <= now <= after


class _BoomWebClient:
    """A WebClient whose fetch always fails, like a 403 from a real site."""

    def search(self, query):
        return []

    def fetch(self, url):
        raise RuntimeError("HTTP Error 403: Forbidden")


def test_a_failing_tool_is_fed_back_as_an_error_not_a_crashed_turn(tmp_path):
    agent, store, llm = _make_agent(
        tmp_path,
        web=_BoomWebClient(),
        replies=[
            ToolCall(id="f1", name="fetch_url", input={"url": "https://x.test"}),
            "I couldn't fetch that page.",
        ],
    )

    # A read-only tool failure must be a wasted call, not a killed Turn.
    reply = agent.send("read https://x.test for me")

    assert reply == "I couldn't fetch that page."
    # The failure was fed back to the model as the tool result, surfacing
    # what went wrong, so it could still answer.
    followup_blob = json.dumps(llm.calls[1][0])
    assert "403" in followup_blob
    # The Turn still persisted cleanly.
    turns = store.turns_of(agent.conversation_id)
    assert [(t.role, t.content) for t in turns] == [
        ("user", "read https://x.test for me"),
        ("agent", "I couldn't fetch that page."),
    ]


def test_full_read_only_surface_is_registered_and_has_no_shell(tmp_path):
    agent, _store, llm = _make_agent(tmp_path, replies=["hello"])

    agent.send("hi")

    offered = {t["name"] for t in llm.calls[0][2]}
    # All six band-B read-only tools, alongside the recall surface.
    assert {
        "read_file",
        "list_dir",
        "grep",
        "web_search",
        "fetch_url",
        "current_time",
    } <= offered
    assert {"search_recall", "get_conversation"} <= offered
    # No shell tool exists, and nothing write-shaped is on the surface.
    assert "shell" not in offered
    assert not any(
        bad in name
        for name in offered
        for bad in ("write", "exec", "delete", "shell")
    )
