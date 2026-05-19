"""The Summarizer — one mechanism, used at two time-scales (ADR-0003).

A deep module: the interface is just `summarize(turns) -> Summary`; the prompt
construction, model resolution, JSON parsing and entry normalisation are hidden
behind it. The same call serves the final whole-Conversation Summary written at
Sealing and (later, issue 06) the running Compaction Summary.

Output shape is ADR-0006's structured Summary: a prose recap plus discrete
`requests` and `outcomes` lists, so the request-shaped headline query is a
strong Recall match instead of being buried in prose.
"""

import json
from dataclasses import dataclass
from typing import Protocol

_PROMPT = """\
Summarise this finished Conversation between a User and an Agent.

Reply with ONLY a single JSON object (no surrounding text), exactly these keys:
- "prose": 2-4 sentence recap of what happened
- "requests": list of distinct, normalised things the User asked the Agent to \
do, phrased as short imperatives; [] if none
- "outcomes": list of concrete things decided or produced; [] if none

Transcript:
{transcript}"""


@dataclass(frozen=True)
class Summary:
    prose: str
    requests: list[str]
    outcomes: list[str]


# The one-method seam the Compactor depends on. It exists only because a Fake
# double is substituted (`FakeSummarizer`): ty checks it and the concrete
# `Summarizer` against this Protocol, so a Fake drifting from the real seam is
# a type error. `turns` stays unannotated to match the concrete signature —
# callers pass Store Turns or transient `_Msg`s interchangeably.
class SummarizerLike(Protocol):
    def summarize(self, turns) -> Summary: ...


class Summarizer:
    def __init__(self, llm, config):
        self._llm = llm
        self._config = config

    def summarize(self, turns) -> Summary:
        transcript = "\n".join(f"{t.role}: {t.content}" for t in turns)
        reply = self._llm.complete(
            [{"role": "user", "content": _PROMPT.format(transcript=transcript)}],
            self._config.model_for("summarise"),
        ).text or ""
        try:
            data = json.loads(reply)
            return Summary(
                prose=str(data["prose"]).strip(),
                requests=_normalise(data.get("requests")),
                outcomes=_normalise(data.get("outcomes")),
            )
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            # Model ignored the JSON contract — degrade so Sealing still
            # completes: keep the raw text as the recap, no structured lists.
            return Summary(prose=reply.strip(), requests=[], outcomes=[])


def _normalise(value) -> list[str]:
    """Discrete, normalised entries (ADR-0006): strip, drop empties, dedupe
    keeping first occurrence and order."""
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        entry = str(item).strip()
        if entry and entry not in seen:
            seen.add(entry)
            out.append(entry)
    return out
