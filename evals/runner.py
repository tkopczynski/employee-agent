"""runner — thin impure glue (PRD "Modules", ADR-0008).

Builds the corpus in a throwaway SQLite via the *real* `Store` / `Recall` /
`Unit` public interfaces with the real `FastEmbedEmbedder` (no LLM, ADR-0008),
runs each probe through `Recall.search`, hands the ranked ids to the pure
`scoring` module, prints the always-on scorecard, and returns the exit code.
Not unit-tested — the project's established untested-adapter-glue pattern
(cf. `FastEmbedEmbedder`, the Anthropic client). The embedder-driven run lives
outside `uv run pytest` by construction (ADR-0008).
"""

import tempfile
from pathlib import Path

from employee_agent.config import Config
from employee_agent.embedder import FastEmbedEmbedder
from employee_agent.recall import Recall, Unit
from employee_agent.store import Store

from .loader import Conversation, Dataset, DatasetError, load
from .scoring import Scorecard, score

# Pinned + echoed so a saved scorecard is self-describing (ADR-0002, PRD US-17).
EMBED_MODEL = "BAAI/bge-small-en-v1.5"


def _units_for(conv: Conversation) -> list[Unit]:
    """Exactly the three ADR-0006 indexed kinds, mirroring `Agent._units_for`:
    one `user_turn` per User Turn, one `request` per golden Request, one
    `summary` for the golden Summary prose. Agent Turns and outcomes are not
    indexed."""
    units = [
        Unit(conv.id, "user_turn", t.text)
        for t in conv.turns
        if t.role == "user"
    ]
    units += [Unit(conv.id, "request", r) for r in conv.golden.requests]
    if conv.golden.summary:
        units.append(Unit(conv.id, "summary", conv.golden.summary))
    return units


def _build_corpus(dataset: Dataset, store: Store, recall: Recall) -> None:
    # Built in id order into a fresh db so authored ids equal the
    # Store-assigned conversation_id; assert that runtime side of the
    # id-invariant so a probe's expected Conversation is unambiguous.
    for conv in dataset.conversations:
        cid = store.start_conversation()
        if cid != conv.id:
            raise DatasetError(
                f"id-invariant violated: conversation authored as {conv.id} "
                f"was assigned id {cid} by the Store"
            )
        for seq, turn in enumerate(conv.turns):
            store.add_turn(cid, seq, turn.role, turn.text)
        store.seal_conversation(cid, conv.golden.summary, conv.golden.outcomes)
        recall.add_units(_units_for(conv))


def _fmt_metrics(label, m, n):
    return (
        f"  {label:<10} n={n:<3} "
        f"recall@1={m.recall_at_1:.2f} recall@3={m.recall_at_3:.2f} "
        f"recall@6={m.recall_at_6:.2f}  recall@k={m.recall_at_k:.2f}  "
        f"hit@1={m.hit_at_1:.2f}"
    )


def _print_scorecard(card: Scorecard, dataset: Dataset, config: Config) -> None:
    print("=" * 78)
    print("RETRIEVAL-QUALITY EVAL — scorecard")
    print("=" * 78)
    print(
        f"knobs: embedding={EMBED_MODEL}  recall_k={config.recall_k}  "
        f"rrf_k={config.rrf_k}  token_ceiling={config.recall_token_ceiling}"
    )
    print("-" * 78)
    print(f"{'arm':<9} {'expect':>6} {'rank':>5}  {'top ids':<16} query")
    print("-" * 78)
    for r in card.rows:
        rank = "MISS" if r.rank is None else str(r.rank)
        top = ",".join(str(i) for i in r.ranked_ids[:3]) or "-"
        print(f"{r.arm:<9} {r.expect:>6} {rank:>5}  {top:<16} {r.query}")
    print("-" * 78)
    n_by_arm: dict[str, int] = {}
    for p in dataset.probes:
        n_by_arm[p.arm] = n_by_arm.get(p.arm, 0) + 1
    print(_fmt_metrics("overall", card.overall, len(dataset.probes)))
    for arm in sorted(card.per_arm):
        print(_fmt_metrics(arm, card.per_arm[arm], n_by_arm.get(arm, 0)))
    print("-" * 78)
    if card.passed:
        print("VERDICT: PASS")
    else:
        reasons = []
        if card.overall.recall_at_k < dataset.floor.recall_at_k:
            reasons.append(
                f"recall@k {card.overall.recall_at_k:.2f} "
                f"< floor {dataset.floor.recall_at_k:.2f}"
            )
        if card.overall.hit_at_1 < dataset.floor.hit_at_1:
            reasons.append(
                f"hit@1 {card.overall.hit_at_1:.2f} "
                f"< floor {dataset.floor.hit_at_1:.2f}"
            )
        print(f"VERDICT: FAIL ({'; '.join(reasons)})")
    print("=" * 78)


def run(dataset_path) -> int:
    """Load → build → search → score → print → exit code (0 PASS, 1 FAIL).
    A `DatasetError` propagates to the entry point, which maps it to exit 1."""
    dataset = load(dataset_path)
    config = Config()
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "eval.sqlite")
        recall = Recall(store, FastEmbedEmbedder(EMBED_MODEL), config)
        _build_corpus(dataset, store, recall)
        # k falls through to Config().recall_k inside Recall.search — exactly
        # what the Agent sees at run time.
        def search(query: str) -> list[int]:
            return [h.conversation_id for h in recall.search(query)]

        card = score(dataset.probes, search, config.recall_k, dataset.floor)
    _print_scorecard(card, dataset, config)
    return 0 if card.passed else 1
