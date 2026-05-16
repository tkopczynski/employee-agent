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
    # The Workspace is the Agent's entire filesystem surface (Issue 01): all
    # file-tool paths are interpreted relative to this configured root, and
    # nothing outside it is reachable.
    ws = tmp_path / "ws"
    ws.mkdir()
    store = Store(tmp_path / "recall.sqlite")
    cfg = Config(workspace={"root": str(ws)})
    recall = Recall(store, TopicEmbedder(), cfg)
    llm = FakeLLMClient(replies=replies)
    agent = Agent(
        llm=llm, store=store, config=cfg, recall=recall, web=web or FakeWebClient()
    )
    return agent, store, llm, ws


def test_local_file_question_routes_to_read_file_and_grounds_the_reply(tmp_path):
    agent, store, llm, ws = _make_agent(
        tmp_path,
        replies=[
            ToolCall(id="t1", name="read_file", input={"path": "notes.txt"}),
            "Your notes say the launch code is hunter2.",
        ],
    )
    (ws / "notes.txt").write_text("the launch code is hunter2")

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
    agent, _store, llm, ws = _make_agent(
        tmp_path,
        replies=[
            ToolCall(id="t1", name="list_dir", input={"path": "."}),
            "The directory has alpha.txt and a sub folder.",
        ],
    )
    (ws / "alpha.txt").write_text("a")
    (ws / "sub").mkdir()

    reply = agent.send("what's in that folder?")

    assert reply == "The directory has alpha.txt and a sub folder."
    followup_blob = json.dumps(llm.calls[1][0])
    assert "alpha.txt" in followup_blob and "sub" in followup_blob


def test_grep_routes_and_feeds_matching_lines_back(tmp_path):
    agent, _store, llm, ws = _make_agent(
        tmp_path,
        replies=[
            ToolCall(
                id="t1",
                name="grep",
                input={"pattern": "TODO", "path": "."},
            ),
            "There is one TODO, in a.txt.",
        ],
    )
    (ws / "a.txt").write_text("nothing here\nTODO: fix the bug\nmore\n")
    (ws / "b.txt").write_text("clean file\n")

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
    agent, _store, llm, _ws = _make_agent(
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
    agent, _store, llm, _ws = _make_agent(
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
    agent, store, llm, _ws = _make_agent(
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


def test_outside_workspace_read_is_refused_and_relayed_not_a_crashed_turn(tmp_path):
    # The classic airlock ask (CONTEXT.md example dialogue): a path that
    # escapes the Workspace must come back as a tool result the Agent relays,
    # not an exception that kills the Turn.
    agent, store, llm, _ws = _make_agent(
        tmp_path,
        replies=[
            ToolCall(
                id="t1", name="read_file", input={"path": "../../etc/passwd"}
            ),
            "I can't read files outside the Workspace.",
        ],
    )

    reply = agent.send("read ../../etc/passwd for me")

    assert reply == "I can't read files outside the Workspace."
    # The refusal — not a stack trace — was fed back to the model, naming the
    # Workspace so the Agent can explain the boundary to the User.
    followup_blob = json.dumps(llm.calls[1][0])
    assert "WorkspaceError" in followup_blob
    assert "Workspace" in followup_blob
    # The Turn still persisted cleanly: User input + the relayed refusal.
    turns = store.turns_of(agent.conversation_id)
    assert [(t.role, t.content) for t in turns] == [
        ("user", "read ../../etc/passwd for me"),
        ("agent", "I can't read files outside the Workspace."),
    ]


def test_grep_skips_a_symlinked_file_that_points_out_of_the_workspace(tmp_path):
    # os.walk yields symlinked files even though it won't descend symlinked
    # dirs. A symlink inside the Workspace pointing at an outside secret must
    # NOT leak that secret into context — confinement holds mid-walk.
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("SECRET exfiltrated payload\n")

    agent, _store, llm, ws = _make_agent(
        tmp_path,
        replies=[
            ToolCall(id="t1", name="grep", input={"pattern": "SECRET", "path": "."}),
            "Found one in-Workspace match.",
        ],
    )
    (ws / "inside.txt").write_text("a harmless SECRET marker\n")
    (ws / "leak.txt").symlink_to(outside / "secret.txt")

    reply = agent.send("grep SECRET")

    assert reply == "Found one in-Workspace match."
    followup_blob = json.dumps(llm.calls[1][0])
    # The genuine in-Workspace match is returned...
    assert "inside.txt" in followup_blob and "harmless SECRET marker" in followup_blob
    # ...but the symlinked-out secret is never dragged into context.
    assert "exfiltrated payload" not in followup_blob


def test_full_read_only_surface_is_registered_and_has_no_shell(tmp_path):
    agent, _store, llm, _ws = _make_agent(tmp_path, replies=["hello"])

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
