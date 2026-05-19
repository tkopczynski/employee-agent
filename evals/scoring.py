"""scoring — the eval's one deep module (PRD "Modules", ADR-0008).

A pure function from probes, a `search` callable (query -> ranked
Conversation-id list, exactly what the runner gets from `Recall.search` and
what the test gets from a fake), the configured `k`, and the recall floor, to a
Scorecard. No I/O, no embedder, no database — the Recall/Compactor analogue:
simple stable interface, all metric logic behind it, isolation-testable.

Probe duck type: `.query: str`, `.arm: str`, `.expect: int`.
Floor duck type: `.recall_at_k: float`, `.hit_at_1: float`.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol


# The duck types the docstring documents, formalized as co-located Protocols
# (the house seam pattern): the loader's Probe/Floor dataclasses and the
# test's stand-ins structurally satisfy these, so neither is imported here.
class Probe(Protocol):
    query: str
    arm: str
    expect: int


class Floor(Protocol):
    recall_at_k: float
    hit_at_1: float


# query -> ranked Conversation-id list (Recall.search in the runner, a canned
# lambda in the test).
Search = Callable[[str], list[int]]


@dataclass(frozen=True)
class ArmMetrics:
    recall_at_k: float
    hit_at_1: float
    recall_at_1: float
    recall_at_3: float
    recall_at_6: float


@dataclass(frozen=True)
class ProbeRow:
    query: str
    arm: str
    expect: int
    rank: int | None  # 1-based rank of the expected id, or None for a MISS
    ranked_ids: list[int]


@dataclass(frozen=True)
class Scorecard:
    overall: ArmMetrics
    per_arm: dict[str, ArmMetrics]
    rows: list[ProbeRow]
    passed: bool


def _metrics(
    probes: list[Probe], ranked: dict[str, list[int]], k: int
) -> ArmMetrics:
    n = len(probes)
    if not n:
        return ArmMetrics(0.0, 0.0, 0.0, 0.0, 0.0)

    def recall_at(cutoff: int) -> float:
        return sum(p.expect in ranked[p.query][:cutoff] for p in probes) / n

    return ArmMetrics(
        recall_at_k=recall_at(k),
        hit_at_1=sum(
            bool(ranked[p.query]) and ranked[p.query][0] == p.expect for p in probes
        ) / n,
        recall_at_1=recall_at(1),
        recall_at_3=recall_at(3),
        recall_at_6=recall_at(6),
    )


def score(
    probes: Iterable[Probe], search: Search, k: int, floor: Floor
) -> Scorecard:
    probes = list(probes)
    ranked = {p.query: search(p.query) for p in probes}
    arms = sorted({p.arm for p in probes})
    overall = _metrics(probes, ranked, k)
    per_arm = {
        arm: _metrics([p for p in probes if p.arm == arm], ranked, k)
        for arm in arms
    }
    rows = [
        ProbeRow(
            query=p.query,
            arm=p.arm,
            expect=p.expect,
            rank=(
                ranked[p.query].index(p.expect) + 1
                if p.expect in ranked[p.query]
                else None
            ),
            ranked_ids=ranked[p.query],
        )
        for p in probes
    ]
    passed = (
        overall.recall_at_k >= floor.recall_at_k
        and overall.hit_at_1 >= floor.hit_at_1
    )
    return Scorecard(overall=overall, per_arm=per_arm, rows=rows, passed=passed)
