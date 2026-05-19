"""The Compactor — bounds a live Conversation's hot context (ADR-0003).

A deep module: callers only `observe(role, content)` each finalized message
and read `hot_context()` to assemble the next LLM call. Hidden behind that:
token budgeting, the Compaction trigger, the verbatim-tail and running-Summary
caps, and handing cold (compacted) User Turns to Recall storage.

Every growing thing is capped — the verbatim Turn tail and the running
Summary — so the cost bound (PRD's core learning payoff) cannot leak. The
running Summary is *regenerated* from the prior Summary plus the newly
compacted Turns (not appended) and then hard-truncated to its own cap, so
"the summary is the leak" failure mode is structurally impossible.

Cost observability (PRD's learning payoff): every Compaction emits a
structured log record with the hot-token count before and after, so the
bound can be watched holding against a real model.
"""

import logging
from dataclasses import dataclass

from .config import Config
from .recall import RecallSink, Unit
from .summarizer import SummarizerLike

logger = logging.getLogger("employee_agent.compactor")

# The running Summary is injected as a leading message; this marker tells the
# model the span it stands in for. Its token cost is reserved in the budget so
# the marker itself cannot push hot context over the bound.
_SUMMARY_PREFIX = "[Earlier in this conversation, condensed]\n"


def _estimate_tokens(text: str | None) -> int:
    """Dependency-free ~4-chars/token estimate, matching Recall's. Only sizes
    the bound; a real tokenizer is never shipped just for budgeting."""
    if not text:
        return 0
    return -(-len(text) // 4)  # ceil division


@dataclass(frozen=True)
class _Msg:
    """Minimal Turn-shaped value the Summarizer can format (it reads
    .role/.content). The running Summary is transient, never persisted."""

    role: str
    content: str


class Compactor:
    def __init__(
        self,
        summarizer: SummarizerLike,
        config: Config,
        conversation_id,
        recall: RecallSink,
        *,
        token_counter=None,
    ):
        self._summarizer = summarizer
        self._config = config
        self._conversation_id = conversation_id
        self._recall = recall
        self._count = token_counter or _estimate_tokens
        self._tail: list[tuple[str, str]] = []  # (role, content), oldest first
        self._summary = ""  # running Summary prose; "" until first Compaction

    def observe(self, role: str, content: str) -> None:
        self._tail.append((role, content))
        self._maybe_compact()

    def hot_context(self) -> list[dict]:
        msgs: list[dict] = []
        if self._summary:
            msgs.append(
                {"role": "user", "content": _SUMMARY_PREFIX + self._summary}
            )
        msgs += [{"role": r, "content": c} for r, c in self._tail]
        return msgs

    def hot_user_turns(self) -> list[str]:
        """The User Turns still verbatim in the tail — i.e. never compacted
        away. Sealing indexes these; the compacted ones were already handed to
        Recall during the session, so every User Turn is indexed exactly once."""
        return [content for role, content in self._tail if role == "user"]

    # --- internals ---------------------------------------------------------

    def _maybe_compact(self) -> None:
        trigger = self._config.compaction_trigger_fraction * (
            self._config.compaction_context_window
        )
        tail_budget = self._config.compaction_tail_token_budget
        cap = self._config.compaction_summary_token_cap
        # Worst-case size of the regenerated Summary message: its own cap plus
        # the fixed marker overhead. Reserving it lets us decide eviction in
        # one pass (one Summarizer call), and guarantees the post-Compaction
        # hot context is <= trigger without re-measuring after the LLM call.
        summary_slot = cap + self._count(_SUMMARY_PREFIX)

        if not self._over_budget(trigger, tail_budget, summary_slot):
            return

        before = self._hot_tokens()
        evicted: list[tuple[str, str]] = []
        while self._tail and self._over_budget(trigger, tail_budget, summary_slot):
            evicted.append(self._tail.pop(0))

        self._index_cold(evicted)
        self._regenerate_summary(evicted, cap)
        after = self._hot_tokens()
        logger.info(
            "compaction",
            extra={
                "conversation_id": self._conversation_id,
                "hot_tokens_before": before,
                "hot_tokens_after": after,
                "evicted_turns": len(evicted),
                "trigger": trigger,
            },
        )

    def _hot_tokens(self) -> int:
        return sum(self._count(m["content"]) for m in self.hot_context())

    def _over_budget(self, trigger, tail_budget, summary_slot) -> bool:
        tail_tokens = sum(self._count(c) for _r, c in self._tail)
        return tail_tokens > tail_budget or summary_slot + tail_tokens > trigger

    def _index_cold(self, evicted: list[tuple[str, str]]) -> None:
        # Only User Turns are an indexed Recall unit (PRD schema). Compacted
        # Turns are seal-gated by Recall, so they stay unsearchable until the
        # Conversation is Sealed; written here exactly once (they leave the
        # tail and are never observed again).
        units = [
            Unit(self._conversation_id, "user_turn", content)
            for role, content in evicted
            if role == "user"
        ]
        if units:
            self._recall.add_units(units)

    def _regenerate_summary(self, evicted: list[tuple[str, str]], cap: int) -> None:
        # Regenerate (not append): re-summarise the prior Summary together
        # with the just-compacted Turns. Then hard-truncate to the cap so the
        # running Summary cannot grow unbounded whatever the model returns.
        turns: list[_Msg] = []
        if self._summary:
            turns.append(_Msg("assistant", "[Summary so far] " + self._summary))
        turns += [_Msg(role, content) for role, content in evicted]
        prose = self._summarizer.summarize(turns).prose or ""
        self._summary = self._truncate(prose, cap)

    def _truncate(self, text: str, cap: int) -> str:
        if self._count(text) <= cap:
            return text
        # Largest prefix whose token count fits the cap (binary search — works
        # for any counter monotonic in prefix length, incl. the test doubles).
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._count(text[:mid]) <= cap:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo]
