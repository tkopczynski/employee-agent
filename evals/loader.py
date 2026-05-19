"""loader — parse + validate the committed dataset (PRD "Modules", ADR-0008).

Shallow plumbing, deliberately not unit-tested (schema validation, not a deep
module). A malformed dataset is a hard error (`DatasetError`), never a silent
skip — a typo must never produce a falsely-passing run (PRD US-19).

Probe / Floor expose exactly the duck type `evals.scoring` expects
(`probe.query/.arm/.expect`, `floor.recall_at_k/.hit_at_1`).
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

_ARMS = {"semantic", "keyword"}


class DatasetError(Exception):
    """The dataset file is malformed. Always fatal — never a silent skip."""


@dataclass(frozen=True)
class Turn:
    role: str
    text: str


@dataclass(frozen=True)
class Golden:
    requests: list[str]
    summary: str
    outcomes: list[str]


@dataclass(frozen=True)
class Conversation:
    id: int
    topic: str
    turns: list[Turn]
    golden: Golden


@dataclass(frozen=True)
class Probe:
    query: str
    arm: str
    expect: int  # the one correct Conversation id


@dataclass(frozen=True)
class Floor:
    recall_at_k: float
    hit_at_1: float


@dataclass(frozen=True)
class Dataset:
    floor: Floor
    conversations: list[Conversation]  # sorted by id == build order
    probes: list[Probe]


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise DatasetError(msg)


def _fraction(block: dict, key: str) -> float:
    _require(key in block, f"floor.{key} is missing")
    v = block[key]
    _require(
        isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= v <= 1.0,
        f"floor.{key} must be a number in [0, 1], got {v!r}",
    )
    return float(v)


def load(path: str | Path) -> Dataset:
    """Parse and fully validate `path`. Raises `DatasetError` on any defect:
    a bad arm, an unknown expected id, a missing/out-of-range floor, duplicate
    or non-contiguous ids. The conversations come back sorted by id, which is
    the order the runner must build them in so authored ids equal the
    `Store`-assigned `conversation_id` (the id-invariant)."""
    with open(path) as fh:
        raw = yaml.safe_load(fh)
    _require(isinstance(raw, dict), "dataset must be a YAML mapping")

    for key in ("floor", "conversations", "probes"):
        _require(key in raw, f"top-level '{key}' is missing")

    floor_block = raw["floor"]
    _require(isinstance(floor_block, dict), "floor must be a mapping")
    floor = Floor(
        recall_at_k=_fraction(floor_block, "recall_at_k"),
        hit_at_1=_fraction(floor_block, "hit_at_1"),
    )

    raw_convs = raw["conversations"]
    _require(
        isinstance(raw_convs, list) and raw_convs,
        "conversations must be a non-empty list",
    )
    conversations: list[Conversation] = []
    for c in raw_convs:
        _require(isinstance(c, dict), f"conversation must be a mapping, got {c!r}")
        for key in ("id", "topic", "turns", "golden"):
            _require(key in c, f"conversation is missing '{key}': {c!r}")
        _require(
            isinstance(c["id"], int) and not isinstance(c["id"], bool),
            f"conversation id must be an int, got {c['id']!r}",
        )
        turns = []
        _require(
            isinstance(c["turns"], list) and c["turns"],
            f"conversation {c['id']} has no turns",
        )
        for t in c["turns"]:
            _require(
                isinstance(t, dict) and "role" in t and "text" in t,
                f"conversation {c['id']} has a malformed turn: {t!r}",
            )
            _require(
                t["role"] in ("user", "agent"),
                f"conversation {c['id']} turn role must be user|agent, "
                f"got {t['role']!r}",
            )
            turns.append(Turn(role=t["role"], text=str(t["text"])))
        g = c["golden"]
        _require(
            isinstance(g, dict)
            and isinstance(g.get("requests"), list)
            and isinstance(g.get("summary"), str)
            and isinstance(g.get("outcomes"), list),
            f"conversation {c['id']} has a malformed golden block: {g!r}",
        )
        conversations.append(
            Conversation(
                id=c["id"],
                topic=str(c["topic"]),
                turns=turns,
                golden=Golden(
                    requests=[str(r) for r in g["requests"]],
                    summary=g["summary"],
                    outcomes=[str(o) for o in g["outcomes"]],
                ),
            )
        )

    ids = [c.id for c in conversations]
    _require(len(set(ids)) == len(ids), f"conversation ids are not unique: {ids}")
    # The id-invariant's authoring side: a fresh SQLite assigns 1..N in build
    # order, so the authored ids must be exactly that set. The runner asserts
    # the runtime side (assigned == authored) after building.
    _require(
        sorted(ids) == list(range(1, len(ids) + 1)),
        f"conversation ids must be exactly 1..{len(ids)} (got {sorted(ids)}) "
        "so authored ids equal the Store-assigned conversation_id",
    )
    conversations.sort(key=lambda c: c.id)

    raw_probes = raw["probes"]
    _require(
        isinstance(raw_probes, list) and raw_probes,
        "probes must be a non-empty list",
    )
    known = set(ids)
    probes: list[Probe] = []
    for p in raw_probes:
        _require(
            isinstance(p, dict)
            and isinstance(p.get("query"), str)
            and "arm" in p
            and "expect_conversation" in p,
            f"malformed probe: {p!r}",
        )
        _require(
            p["arm"] in _ARMS,
            f"probe arm must be semantic|keyword, got {p['arm']!r}",
        )
        _require(
            p["expect_conversation"] in known,
            f"probe expects unknown conversation id {p['expect_conversation']!r}",
        )
        probes.append(
            Probe(query=p["query"], arm=p["arm"], expect=p["expect_conversation"])
        )

    return Dataset(floor=floor, conversations=conversations, probes=probes)
