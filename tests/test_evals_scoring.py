"""Hermetic unit test of the pure eval scoring math (ADR-0008, PRD US-21/25).

The embedder-driven eval run is deliberately outside `uv run pytest`; only
`evals.scoring` — pure metric logic, no embedder, no database, no I/O — is
tested here, driven by a fake `search` returning canned ranked id lists. We
assert the observable contract (returned metrics + verdict), never internals
or formatting wording.
"""

from dataclasses import dataclass

from evals.scoring import score


@dataclass(frozen=True)
class Probe:
    query: str
    arm: str
    expect: int


@dataclass(frozen=True)
class Floor:
    recall_at_k: float
    hit_at_1: float


def fake_search(ranked_by_query):
    """A canned search: query -> ranked conversation-id list."""
    return lambda q: ranked_by_query[q]


def test_recall_at_k_counts_expected_anywhere_in_ranked_ids(tmp_path):
    # Tracer: the expected Conversation is returned (at rank 3, within k=6),
    # so recall@k credits the probe and the run clears a floor it meets.
    probes = [Probe("when did I ask about the report", "semantic", 7)]
    search = fake_search({"when did I ask about the report": [4, 2, 7, 9]})

    card = score(probes, search, k=6, floor=Floor(recall_at_k=1.0, hit_at_1=0.0))

    assert card.overall.recall_at_k == 1.0
    assert card.passed is True


def test_hit_at_1_only_credits_expected_at_rank_one():
    # Both probes recall their target (recall@k = 1.0), but only the first
    # ranks it #1, so hit@1 is the stricter 0.5 — the ranking-regression
    # signal recall@k would hide (PRD US-10).
    probes = [
        Probe("rank one", "semantic", 3),
        Probe("rank three", "keyword", 8),
    ]
    search = fake_search({"rank one": [3, 1, 9], "rank three": [5, 1, 8]})

    card = score(probes, search, k=6, floor=Floor(recall_at_k=0.0, hit_at_1=0.0))

    assert card.overall.recall_at_k == 1.0
    assert card.overall.hit_at_1 == 0.5


def test_recall_curve_truncates_ids_to_one_three_six():
    # P1's target is rank 1 (in @1/@3/@6); P2's is rank 5 (only in @6). The
    # curve shows the ranking headroom a single recall@k number hides
    # (PRD US-11).
    probes = [
        Probe("p1", "semantic", 1),
        Probe("p2", "semantic", 2),
    ]
    search = fake_search({"p1": [1, 9, 8, 7, 6], "p2": [9, 8, 7, 6, 2]})

    card = score(probes, search, k=6, floor=Floor(recall_at_k=0.0, hit_at_1=0.0))

    assert card.overall.recall_at_1 == 0.5
    assert card.overall.recall_at_3 == 0.5
    assert card.overall.recall_at_6 == 1.0


def test_metrics_are_partitioned_per_arm():
    # The semantic probe lands; the keyword probe misses entirely. The overall
    # number averages them, but the per-arm split shows the semantic arm
    # carrying the run and the keyword arm failing (PRD US-12 — the learning
    # artifact: does each arm earn its complexity).
    probes = [
        Probe("by meaning", "semantic", 1),
        Probe("by token", "keyword", 2),
    ]
    search = fake_search({"by meaning": [1, 7], "by token": [7, 8]})

    card = score(probes, search, k=6, floor=Floor(recall_at_k=0.0, hit_at_1=0.0))

    assert card.overall.recall_at_k == 0.5
    assert card.per_arm["semantic"].recall_at_k == 1.0
    assert card.per_arm["semantic"].hit_at_1 == 1.0
    assert card.per_arm["keyword"].recall_at_k == 0.0
    assert card.per_arm["keyword"].hit_at_1 == 0.0


def test_verdict_flips_exactly_at_the_floor():
    # Observed run: recall@k = 0.5, hit@1 = 0.5 (one full hit, one miss).
    probes = [Probe("a", "semantic", 1), Probe("b", "keyword", 2)]
    search = fake_search({"a": [1, 9], "b": [8, 9]})

    def verdict(recall_floor, hit_floor):
        return score(
            probes, search, k=6,
            floor=Floor(recall_at_k=recall_floor, hit_at_1=hit_floor),
        ).passed

    # Exactly at the floor is a PASS (>= , the floor is the regression
    # tripwire, PRD US-14/15) ...
    assert verdict(0.5, 0.5) is True
    # ... a hair above either floor is a FAIL ...
    assert verdict(0.51, 0.5) is False
    assert verdict(0.5, 0.51) is False
    # ... and *both* floors gate, not just recall.
    assert verdict(0.0, 0.6) is False


def test_per_probe_rows_expose_rank_or_miss_and_returned_ids():
    # The per-probe row is what lets the User see *where* retrieval breaks,
    # not just that it did (PRD US-13): rank of the expected Conversation
    # (1-based) or MISS, plus the ids that came back.
    probes = [
        Probe("found at rank two", "semantic", 5),
        Probe("not returned at all", "keyword", 3),
    ]
    search = fake_search(
        {"found at rank two": [2, 5, 9], "not returned at all": [1, 2]}
    )

    card = score(probes, search, k=6, floor=Floor(recall_at_k=0.0, hit_at_1=0.0))

    assert [(r.query, r.arm, r.expect) for r in card.rows] == [
        ("found at rank two", "semantic", 5),
        ("not returned at all", "keyword", 3),
    ]
    found, miss = card.rows
    assert found.rank == 2          # 1-based rank of the expected id
    assert found.ranked_ids == [2, 5, 9]
    assert miss.rank is None        # expected id never returned -> MISS
    assert miss.ranked_ids == [1, 2]
