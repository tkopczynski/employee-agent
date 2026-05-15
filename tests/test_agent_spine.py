import datetime as dt
import threading

from employee_agent.agent import Agent
from employee_agent.config import Config
from employee_agent.store import Store

from fakes import FakeLLMClient


def make_agent(tmp_path, replies=None, config=None):
    store = Store(tmp_path / "recall.sqlite")
    llm = FakeLLMClient(replies or [])
    agent = Agent(llm=llm, store=store, config=config or Config())
    return agent, store, llm


def test_constructing_agent_opens_a_conversation(tmp_path):
    agent, store, _ = make_agent(tmp_path)

    conv = store.get_conversation(agent.conversation_id)

    assert conv is not None
    # started_at is recorded as an ISO-8601 string (ADR-0001)
    dt.datetime.fromisoformat(conv.started_at)
    # an open Conversation is not Sealed yet
    assert conv.sealed_at is None


def test_send_returns_the_models_reply(tmp_path):
    agent, _, _ = make_agent(tmp_path, replies=["Hi there!"])

    assert agent.send("hello") == "Hi there!"


def test_send_persists_user_then_agent_turn_in_order(tmp_path):
    agent, store, _ = make_agent(tmp_path, replies=["Hi there!"])

    agent.send("hello")

    turns = store.turns_of(agent.conversation_id)
    assert [(t.seq, t.role, t.content) for t in turns] == [
        (0, "user", "hello"),
        (1, "agent", "Hi there!"),
    ]
    for t in turns:
        dt.datetime.fromisoformat(t.created_at)


def test_multiple_exchanges_keep_a_single_monotonic_sequence(tmp_path):
    agent, store, _ = make_agent(tmp_path, replies=["reply one", "reply two"])

    agent.send("first")
    agent.send("second")

    turns = store.turns_of(agent.conversation_id)
    assert [(t.seq, t.role, t.content) for t in turns] == [
        (0, "user", "first"),
        (1, "agent", "reply one"),
        (2, "user", "second"),
        (3, "agent", "reply two"),
    ]
    seqs = [t.seq for t in turns]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_agent_loop_model_is_resolved_from_the_per_task_map(tmp_path):
    agent, _, llm = make_agent(tmp_path, replies=["ok"])
    agent.send("hi")
    _, model_used = llm.calls[-1]
    assert model_used == "claude-sonnet-4-6"  # default agent_loop model

    # Overriding the config map changes the model — proves it is not hardcoded.
    cfg = Config(models={"agent_loop": "claude-opus-4-7"})
    agent2, _, llm2 = make_agent(tmp_path, replies=["ok"], config=cfg)
    agent2.send("hi")
    _, model_used2 = llm2.calls[-1]
    assert model_used2 == "claude-opus-4-7"


def test_store_is_usable_from_a_worker_thread(tmp_path):
    # The TUI runs agent.send() in a Textual worker thread while the Store was
    # constructed on the main thread. The Store must tolerate cross-thread use.
    agent, store, _ = make_agent(tmp_path, replies=["from worker"])

    errors = []

    def worker():
        try:
            agent.send("hi from another thread")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert errors == [], f"send() raised on a worker thread: {errors}"
    turns = store.turns_of(agent.conversation_id)
    assert [(turn.role, turn.content) for turn in turns] == [
        ("user", "hi from another thread"),
        ("agent", "from worker"),
    ]
