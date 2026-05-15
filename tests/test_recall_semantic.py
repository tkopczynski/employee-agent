"""Recall — hybrid (semantic + keyword) retrieval with RRF (Issue 04).

Exercised through Recall's public interface against a temporary SQLite file
with real sqlite-vec + FTS5 and a deterministic, controllable TopicEmbedder.
We assert observable ordering/recall behaviour — never raw vectors, SQL, or
private state (PRD Testing Decisions).
"""

from employee_agent.config import Config
from employee_agent.recall import Recall, Unit
from employee_agent.store import Store

from fakes import TopicEmbedder


def test_paraphrase_recall_is_seal_gated(tmp_path):
    # "prepare a report" and "draft a one-pager" share no content words, but
    # the controllable Embedder puts them in the same topic — a pure semantic
    # match the keyword (FTS5) arm could never make.
    embedder = TopicEmbedder({"report": ["prepare a report", "draft a one-pager"]})
    store = Store(tmp_path / "r.sqlite")
    recall = Recall(store, embedder, Config())
    cid = store.start_conversation()
    store.add_turn(cid, 0, "user", "draft a one-pager")
    recall.add_units([Unit(cid, "user_turn", "draft a one-pager", 0)])

    # Unsealed (the live session): the semantic arm obeys the seal-gate
    # (ADR-0005) exactly like the keyword arm — nothing is searchable yet.
    assert recall.search("prepare a report") == []

    store.seal_conversation(cid, "Discussed drafting a one-pager.", [])

    # Same query, same unit — now Sealed, the paraphrase lands.
    hits = recall.search("prepare a report")
    assert [h.conversation_id for h in hits] == [cid]
    assert hits[0].snippet == "draft a one-pager"


def _seal_with_unit(store, recall, text):
    cid = store.start_conversation()
    store.seal_conversation(cid, f"recap: {text}", [])
    recall.add_units([Unit(cid, "user_turn", text, 0)])
    return cid


def test_rrf_rewards_good_in_both_lists_over_good_in_one(tmp_path):
    # Query "alpha": the keyword arm (FTS MATCH) matches only the C_BOTH unit;
    # the semantic arm ranks the topic-mate SEM_TOP unit #1 (it shares the
    # query's topic) and C_BOTH second.
    embedder = TopicEmbedder({"q": ["alpha", "quarterly board deck outline"]})
    store = Store(tmp_path / "r.sqlite")
    recall = Recall(store, embedder, Config())

    # In only ONE list: top of semantic, absent from keyword (no "alpha").
    conv_one = _seal_with_unit(store, recall, "quarterly board deck outline")
    # In BOTH lists: keyword rank 1 *and* present in semantic (rank 2).
    conv_both = _seal_with_unit(store, recall, "alpha launch retro notes")

    hits = recall.search("alpha")

    # Good-in-both outranks rank-1-in-a-single-list — the RRF property.
    assert [h.conversation_id for h in hits] == [conv_both, conv_one]


def test_exact_token_still_recalls_its_keyword_match_after_fusion(tmp_path):
    # The semantic arm is deliberately pointed at conv_sem (it shares the
    # query's topic); conv_kw is semantically far but is the only unit that
    # literally contains the exact token. Precise lookups (an error string,
    # a project name) must not be lost to fuzzy matching (PRD story 20).
    embedder = TopicEmbedder({"q": ["ERR_4711", "the onboarding checklist"]})
    store = Store(tmp_path / "r.sqlite")
    recall = Recall(store, embedder, Config())

    conv_sem = _seal_with_unit(store, recall, "the onboarding checklist")
    conv_kw = _seal_with_unit(store, recall, "build failed with ERR_4711 today")

    hits = recall.search("ERR_4711")

    # The exact-token Conversation is recalled and ranked first despite the
    # semantic arm favouring conv_sem — keyword survives fusion (no 03 regress).
    assert hits[0].conversation_id == conv_kw
    assert "ERR_4711" in hits[0].snippet


_UNIT = "alpha " * 10  # 60 chars; with its "recap: " prose, 32 est-tokens/hit


def _budget_corpus(tmp_path, **recall_cfg):
    store = Store(tmp_path / "r.sqlite")
    recall = Recall(store, TopicEmbedder(), Config(recall=recall_cfg))
    for _ in range(5):
        _seal_with_unit(store, recall, _UNIT)
    return recall


def test_token_ceiling_returns_fewer_complete_hits_not_truncated(tmp_path):
    # Five matching Conversations; the ceiling admits only three whole hits.
    recall = _budget_corpus(tmp_path, token_ceiling=100)

    hits = recall.search("alpha")

    # Fewer *complete* hits over more truncated ones (PRD): some are dropped,
    # but every returned snippet is the full, untruncated unit text.
    assert len(hits) == 3
    assert all(h.snippet == _UNIT for h in hits)


def test_top_hit_is_returned_even_when_it_alone_exceeds_the_ceiling(tmp_path):
    recall = _budget_corpus(tmp_path, token_ceiling=1)

    # Recall must never silently return nothing for a real top match.
    assert len(recall.search("alpha")) == 1


def test_top_k_is_honoured_after_fusion(tmp_path):
    recall = _budget_corpus(tmp_path)  # generous default ceiling

    hits = recall.search("alpha", k=2)

    assert len(hits) == 2
    assert len({h.conversation_id for h in hits}) == 2
