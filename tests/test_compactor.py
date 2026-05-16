"""Compactor — the cost-bounding module (Issue 06, ADR-0003).

Tested through its public interface (`observe`, `hot_context`,
`hot_user_turns`) with an injected token counter and a fake Summarizer /
Recall (PRD Testing Decisions). We assert observable contracts — the hot
context stays under the configured fraction of the window, the verbatim tail
is preserved, the running Summary never exceeds its own cap, and compacted
User Turns reach Recall storage exactly once — never internal state or LLM
phrasing.
"""

from employee_agent.compactor import Compactor
from employee_agent.config import Config

from fakes import FakeRecall, FakeSummarizer

# A deterministic 1-token-per-character counter: it makes the budgets in these
# tests exact, so "never exceeds the fraction" is an unambiguous assertion.
CHARS = len


def _compactor(config=None, summarizer=None, recall=None):
    return Compactor(
        summarizer or FakeSummarizer(),
        config or Config(),
        conversation_id=1,
        recall=recall or FakeRecall(),
        token_counter=CHARS,
    )


def test_under_budget_hot_context_is_the_verbatim_messages(tmp_path):
    # A roomy window: nothing should compact, so the hot context is exactly
    # what was observed, in order, with no running Summary injected.
    cfg = Config(compaction={"context_window": 10_000})
    c = _compactor(cfg)

    c.observe("user", "hello there")
    c.observe("assistant", "hi, how can I help?")

    assert c.hot_context() == [
        {"role": "user", "content": "hello there"},
        {"role": "assistant", "content": "hi, how can I help?"},
    ]


def _hot_tokens(c, counter=CHARS):
    return sum(counter(m["content"]) for m in c.hot_context())


def test_hot_context_never_exceeds_the_fraction_over_a_long_stream(tmp_path):
    # Tight budgets force repeated Compaction. The contract: no matter how
    # long the User keeps talking, the hot context we'd send the model never
    # exceeds trigger_fraction * context_window (PRD acceptance #1).
    cfg = Config(
        compaction={
            "context_window": 200,
            "trigger_fraction": 0.5,  # trigger = 100 "tokens" (= chars here)
            "tail_token_budget": 60,
            "summary_token_cap": 30,
        }
    )
    c = _compactor(cfg)
    trigger = 0.5 * 200

    for i in range(80):
        role = "user" if i % 2 == 0 else "assistant"
        c.observe(role, f"message number {i} with some filler text to add weight")
        assert _hot_tokens(c) <= trigger, f"hot context blew the bound at turn {i}"


def test_recent_turns_are_preserved_verbatim_in_the_tail(tmp_path):
    # Compaction condenses the *old* part; the recent tail must stay verbatim
    # (not summarised) so the Agent does not get amnesia about what was just
    # said (PRD acceptance #2, User story 15).
    cfg = Config(
        compaction={
            "context_window": 200,
            "trigger_fraction": 0.5,
            "tail_token_budget": 60,
            "summary_token_cap": 30,
        }
    )
    c = _compactor(cfg)
    for i in range(40):
        c.observe("user" if i % 2 == 0 else "assistant", f"turn {i} content here")

    tail_msgs = [m for m in c.hot_context() if not m["content"].startswith("[Earlier")]
    # The most recent message is always present, unaltered.
    assert tail_msgs[-1] == {"role": "assistant", "content": "turn 39 content here"}
    # The tail is a contiguous verbatim suffix of what was observed.
    for n, m in enumerate(tail_msgs):
        i = 40 - len(tail_msgs) + n
        assert m["content"] == f"turn {i} content here"
    # And the verbatim tail itself stays within its own configured budget.
    assert sum(CHARS(m["content"]) for m in tail_msgs) <= 60


def test_running_summary_stays_under_its_cap_even_if_summariser_leaks(tmp_path):
    # The "summary is the leak" failure mode: a Summarizer that keeps making
    # the prose longer every time it is called. The Compactor must hard-cap
    # it regardless, so the running Summary never grows unbounded (PRD
    # acceptance #3).
    growing = {"n": 0}

    def ever_longer(turns):
        growing["n"] += 1
        return "LEAK " * 50 * growing["n"]  # 250, 500, 750, … chars

    cfg = Config(
        compaction={
            "context_window": 200,
            "trigger_fraction": 0.5,
            "tail_token_budget": 60,
            "summary_token_cap": 30,
        }
    )
    c = _compactor(cfg, summarizer=FakeSummarizer(prose_for=ever_longer))

    summary_sizes = []
    for i in range(60):
        c.observe("user" if i % 2 == 0 else "assistant", f"turn {i} some content")
        summary = next(
            (m["content"] for m in c.hot_context() if m["content"].startswith("[Earlier")),
            "",
        )
        body = summary[len("[Earlier in this conversation, condensed]\n"):]
        summary_sizes.append(CHARS(body))

    assert growing["n"] > 1, "test did not exercise repeated regeneration"
    # However big the model's output got, the kept Summary never exceeds cap.
    assert max(summary_sizes) <= 30


def test_compacted_user_turns_reach_recall_exactly_once(tmp_path):
    # ADR-0004: compacted Turns are written to Recall storage incrementally,
    # exactly once. Only User Turns are indexed units; Agent Turns never are.
    cfg = Config(
        compaction={
            "context_window": 200,
            "trigger_fraction": 0.5,
            "tail_token_budget": 60,
            "summary_token_cap": 30,
        }
    )
    recall = FakeRecall()
    c = _compactor(cfg, recall=recall)

    user_texts = [f"user question {i} about some topic" for i in range(30)]
    for i, q in enumerate(user_texts):
        c.observe("user", q)
        c.observe("assistant", f"agent reply {i} with detail")

    indexed = recall.added
    # Every indexed unit is a User Turn for this Conversation — no Agent Turns.
    assert indexed and all(u.kind == "user_turn" for u in indexed)
    assert all(u.conversation_id == 1 for u in indexed)
    assert not any(u.text.startswith("agent reply") for u in indexed)

    compacted = [u.text for u in indexed]
    still_hot = c.hot_user_turns()
    # Exactly once: no unit indexed twice, compacted and still-hot are
    # disjoint, and together they account for every User Turn (so Sealing the
    # still-hot ones later double-counts nothing).
    assert len(compacted) == len(set(compacted))
    assert set(compacted).isdisjoint(still_hot)
    assert sorted(compacted + still_hot) == sorted(user_texts)
