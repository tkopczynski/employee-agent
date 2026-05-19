"""Agent local tool surface (PRD Q9, Issue 05; Workspace-confined in Issue 01;
write_file added in Issue 02).

End-to-end through Agent.send with a faked LLMClient that scripts a tool
call, mirroring test_agent_tools.py. We assert the observable wiring
contract: the tools are offered, a scripted tool call is executed and its
result fed back into the follow-up call, and the model's post-tool text is
what the User gets — including write_file creating a file in the Workspace
and an escaping write being refused by the same airlock as the reads.
Network tools go through a faked WebClient so tests stay offline (PRD Testing
Decisions). We never assert on model phrasing.
"""

import datetime as dt
import json

from employee_agent.agent import Agent
from employee_agent.config import Config
from employee_agent.llm import ToolCall
from employee_agent.recall import Recall
from employee_agent.store import Store

from employee_agent.sandbox import ExecResult

from fakes import TopicEmbedder, FakeLLMClient, FakeWebClient, FakeSandbox


def _make_agent(tmp_path, replies, web=None, sandbox=None):
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
        llm=llm,
        store=store,
        config=cfg,
        recall=recall,
        web=web or FakeWebClient(),
        sandbox=sandbox,
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


def test_save_request_routes_to_write_file_and_file_appears_in_workspace(tmp_path):
    # The PRD's first user story: the User asks the Agent to save something
    # and the file appears in the Workspace. Write runs prompt-free —
    # containment is the trust model (ADR-0007), so the loop just runs it.
    agent, store, llm, ws = _make_agent(
        tmp_path,
        replies=[
            ToolCall(
                id="w1",
                name="write_file",
                input={"path": "hello.py", "content": "print('hi')\n"},
            ),
            "Saved hello.py for you.",
        ],
    )

    reply = agent.send("save a hello world script as hello.py")

    assert reply == "Saved hello.py for you."
    # The file actually appears in the Workspace with the given content.
    assert (ws / "hello.py").read_text() == "print('hi')\n"
    # write_file is offered to the model on every call.
    offered = [{t["name"] for t in tools} for (_m, _model, tools) in llm.calls]
    assert offered and all("write_file" in names for names in offered)
    # Turn semantics preserved: only the User Turn + final Agent Turn persist
    # (the write round-trip is intra-Turn hot-context mechanics, not a Turn).
    turns = store.turns_of(agent.conversation_id)
    assert [(t.role, t.content) for t in turns] == [
        ("user", "save a hello world script as hello.py"),
        ("agent", "Saved hello.py for you."),
    ]


def test_write_file_creates_missing_parent_dirs_under_the_workspace(tmp_path):
    # The build-a-script loop should not need a separate mkdir step: writing
    # a nested Workspace-relative path creates its parent dirs in the
    # Workspace (still routed through the same airlock).
    agent, _store, llm, ws = _make_agent(
        tmp_path,
        replies=[
            ToolCall(
                id="w1",
                name="write_file",
                input={"path": "reports/q2/out.txt", "content": "42\n"},
            ),
            "Wrote reports/q2/out.txt.",
        ],
    )

    reply = agent.send("save the result under reports/q2/out.txt")

    assert reply == "Wrote reports/q2/out.txt."
    assert (ws / "reports" / "q2" / "out.txt").read_text() == "42\n"


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


def test_outside_workspace_write_is_refused_by_the_same_airlock(tmp_path):
    # A write must hit the SAME airlock as the reads (Issue 01): an escaping
    # write path is refused identically — relayed as a tool result naming the
    # Workspace, the Turn persists cleanly, and nothing is written outside.
    agent, store, llm, _ws = _make_agent(
        tmp_path,
        replies=[
            ToolCall(
                id="w1",
                name="write_file",
                input={"path": "../outside_secret", "content": "exfil"},
            ),
            "I can't write outside the Workspace.",
        ],
    )

    reply = agent.send("write exfil to ../outside_secret")

    assert reply == "I can't write outside the Workspace."
    # Nothing was written outside the Workspace.
    assert not (tmp_path / "outside_secret").exists()
    # The refusal — not a stack trace — was fed back, naming the Workspace so
    # the Agent can explain the boundary, exactly like the read refusal.
    followup_blob = json.dumps(llm.calls[1][0])
    assert "WorkspaceError" in followup_blob
    assert "Workspace" in followup_blob
    # The Turn still persisted cleanly: User input + the relayed refusal.
    turns = store.turns_of(agent.conversation_id)
    assert [(t.role, t.content) for t in turns] == [
        ("user", "write exfil to ../outside_secret"),
        ("agent", "I can't write outside the Workspace."),
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


def test_full_tool_surface_is_registered_with_write_and_execute(tmp_path):
    agent, _store, llm, _ws = _make_agent(tmp_path, replies=["hello"])

    agent.send("hi")

    offered = {t["name"] for t in llm.calls[0][2]}
    # The band-B file/web/clock tools, write_file and run_command, alongside
    # recall.
    assert {
        "read_file",
        "list_dir",
        "grep",
        "write_file",
        "run_command",
        "web_search",
        "fetch_url",
        "current_time",
    } <= offered
    assert {"search_recall", "get_conversation"} <= offered
    # The surface is no longer read-only and no longer write-only: it can
    # write into and execute within the Workspace (containment, not
    # read-only-ness, is the trust model — ADR-0007). Execution is a single
    # general run_command (PRD): there is deliberately no separate `shell`,
    # `exec` or `delete` tool.
    assert "shell" not in offered
    assert not any(
        bad in name for name in offered for bad in ("exec", "delete", "shell")
    )


def test_write_then_run_command_routes_through_sandbox_and_grounds_the_reply(
    tmp_path,
):
    # PRD US-2/US-3 headline: the User asks for a script *and a result*; the
    # Agent writes the script then runs it through the Sandbox seam, and the
    # command's output grounds the reply. run_command is prompt-free —
    # containment is the trust model (ADR-0007), so the loop just runs it.
    sandbox = FakeSandbox(
        results={
            "python3 sum.py": ExecResult(
                stdout="42\n", stderr="", exit_code=0, timed_out=False
            )
        }
    )
    agent, store, llm, ws = _make_agent(
        tmp_path,
        sandbox=sandbox,
        replies=[
            ToolCall(
                id="w1",
                name="write_file",
                input={"path": "sum.py", "content": "print(40 + 2)\n"},
            ),
            ToolCall(
                id="r1",
                name="run_command",
                input={"command": "python3 sum.py"},
            ),
            "The script printed 42.",
        ],
    )

    reply = agent.send("write a script that sums 40 and 2, then run it")

    assert reply == "The script printed 42."
    # write_file actually created the script in the Workspace...
    assert (ws / "sum.py").read_text() == "print(40 + 2)\n"
    # ...and run_command was delegated to the Sandbox seam exactly once (no
    # Docker here), honouring the run(command, timeout) contract.
    assert [cmd for cmd, _t in sandbox.calls] == ["python3 sum.py"]
    assert sandbox.calls[0][1] > 0  # a positive timeout was passed through
    # The command's stdout was fed back into the follow-up call so it could
    # ground the reply.
    after_run = json.dumps(llm.calls[2][0])
    assert "42" in after_run
    # Prompt-free: exactly request -> write -> run -> reply. No confirmation
    # round-trip was injected before the command ran (ADR-0007).
    assert len(llm.calls) == 3
    # run_command is offered to the model on every call.
    offered = [{t["name"] for t in tools} for (_m, _model, tools) in llm.calls]
    assert offered and all("run_command" in names for names in offered)
    # Turn semantics preserved: only the User Turn + final Agent Turn persist
    # (the write+run round-trips are intra-Turn hot-context mechanics).
    turns = store.turns_of(agent.conversation_id)
    assert [(t.role, t.content) for t in turns] == [
        ("user", "write a script that sums 40 and 2, then run it"),
        ("agent", "The script printed 42."),
    ]


def test_web_tools_with_no_web_client_wired_are_clean_tool_errors(tmp_path):
    # Same family as the no-Sandbox latent bug (ADR-0009): an Agent built
    # without a WebClient still offers web_search/fetch_url; invoking them
    # must be a clean tool-level *result*, not an AttributeError on a None
    # seam that crashes the Turn. `web` defaults to None — the unwired state
    # ty surfaced once LocalTools.web was honestly typed `WebClient | None`.
    ws = tmp_path / "ws"
    ws.mkdir()
    store = Store(tmp_path / "recall.sqlite")
    cfg = Config(workspace={"root": str(ws)})
    recall = Recall(store, TopicEmbedder(), cfg)
    llm = FakeLLMClient(
        replies=[
            ToolCall(id="w1", name="web_search", input={"query": "anything"}),
            ToolCall(id="f1", name="fetch_url", input={"url": "https://x"}),
            "I can't browse the web — no web client is configured.",
        ]
    )
    agent = Agent(llm=llm, store=store, config=cfg, recall=recall)  # web=None

    reply = agent.send("look something up")

    # The Turn completed: the model's post-tool text reaches the User and no
    # exception escaped the loop across either web tool.
    assert reply == "I can't browse the web — no web client is configured."
    # Both tool results are clean, intentional errors — not a leaked Python
    # AttributeError about NoneType.
    for call in llm.calls:
        blob = json.dumps(call[0])
        assert "AttributeError" not in blob
    followup_blob = json.dumps(llm.calls[-1][0])
    assert "web_search unavailable" in followup_blob
    assert "fetch_url unavailable" in followup_blob
    # The Turn persisted cleanly: User input + the relayed explanation.
    turns = store.turns_of(agent.conversation_id)
    assert [(t.role, t.content) for t in turns] == [
        ("user", "look something up"),
        ("agent", "I can't browse the web — no web client is configured."),
    ]


def test_run_command_with_no_sandbox_wired_is_a_clean_tool_error(tmp_path):
    # An Agent constructed without a Sandbox still offers run_command; the
    # band-C contract says invoking it must be a clean tool-level *result*,
    # not an AttributeError on a None seam that leaks out as the tool result
    # and corrupts the Turn. The Turn must complete normally (latent bug 3,
    # ADR-0009) — sandbox defaults to None here, exactly the unwired state.
    agent, store, llm, _ws = _make_agent(
        tmp_path,
        replies=[
            ToolCall(
                id="r1",
                name="run_command",
                input={"command": "python3 sum.py"},
            ),
            "I can't run commands — no execution sandbox is configured.",
        ],
    )

    reply = agent.send("run sum.py")

    # The Turn completed: the model's post-tool text reaches the User, no
    # exception escaped the loop.
    assert reply == "I can't run commands — no execution sandbox is configured."
    followup_blob = json.dumps(llm.calls[1][0])
    # The tool result is a clean, intentional error — not a leaked Python
    # AttributeError about NoneType.
    assert "AttributeError" not in followup_blob
    assert "run_command unavailable" in followup_blob
    # The Turn persisted cleanly: User input + the relayed explanation.
    turns = store.turns_of(agent.conversation_id)
    assert [(t.role, t.content) for t in turns] == [
        ("user", "run sum.py"),
        ("agent", "I can't run commands — no execution sandbox is configured."),
    ]


def test_run_command_nonzero_exit_is_relayed_not_a_crashed_turn(tmp_path):
    # Band-C error contract, the same as a failing web fetch: a command that
    # exits non-zero is a *result* the Agent reads and relays, not an
    # exception that kills the Turn. stderr and the exit code are surfaced so
    # the Agent can explain what went wrong.
    sandbox = FakeSandbox(
        results={
            "python3 broken.py": ExecResult(
                stdout="",
                stderr="NameError: name 'foo' is not defined\n",
                exit_code=1,
                timed_out=False,
            )
        }
    )
    agent, store, llm, _ws = _make_agent(
        tmp_path,
        sandbox=sandbox,
        replies=[
            ToolCall(
                id="r1",
                name="run_command",
                input={"command": "python3 broken.py"},
            ),
            "The script failed with a NameError.",
        ],
    )

    reply = agent.send("run broken.py")

    assert reply == "The script failed with a NameError."
    # The non-zero exit and stderr were fed back so the Agent could explain;
    # the run still happened (it is not refused, just reported failed).
    assert [cmd for cmd, _t in sandbox.calls] == ["python3 broken.py"]
    followup_blob = json.dumps(llm.calls[1][0])
    assert "NameError" in followup_blob
    assert "exit_code" in followup_blob
    # The Turn persisted cleanly: User input + the relayed explanation.
    turns = store.turns_of(agent.conversation_id)
    assert [(t.role, t.content) for t in turns] == [
        ("user", "run broken.py"),
        ("agent", "The script failed with a NameError."),
    ]
