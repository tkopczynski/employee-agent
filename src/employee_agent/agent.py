"""The agent loop — the spine everything else hangs off.

It orchestrates: open a Conversation on construction; per Turn, run an
agent-pulled tool loop (PRD Q8) where the model decides when to reach into
Recall via `search_recall` / `get_conversation`; on Sealing, condense the
Conversation's Turns into the final structured Summary and index its User
Turns, extracted Requests and the Summary into Recall.

A Turn is one User message plus the Agent's response (CONTEXT.md); the tool
round-trips in between are intra-Turn hot-context mechanics, not Turns, so
only the User input and the final text reply are persisted.
"""

import json

from .recall import Unit
from .summarizer import Summarizer

# Read-only recall surface. Other read-only tools (file/web) hang off this
# same surface in a later issue — adding them is purely additive here.
TOOL_SCHEMAS = [
    {
        "name": "search_recall",
        "description": (
            "Search your Recall of PAST, finished Conversations (earlier "
            "sessions, never the current one) by keyword. Returns dated hits."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_conversation",
        "description": (
            "Drill into the full ordered transcript of one past Conversation "
            "returned by search_recall, using its conversation_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"conversation_id": {"type": "integer"}},
            "required": ["conversation_id"],
        },
    },
]

_MAX_TOOL_STEPS = 8  # bound the loop — runaway tool use is a cost hazard


class Agent:
    def __init__(self, llm, store, config, recall):
        self._llm = llm
        self._store = store
        self._config = config
        self._recall = recall
        self._summarizer = Summarizer(llm, config)
        self.conversation_id = store.start_conversation()
        self._next_seq = 0

    def send(self, user_input: str) -> str:
        self._store.add_turn(self.conversation_id, self._next_seq, "user", user_input)
        self._next_seq += 1

        model = self._config.model_for("agent_loop")
        messages = [{"role": "user", "content": user_input}]
        reply = ""
        for _ in range(_MAX_TOOL_STEPS):
            resp = self._llm.complete(messages, model, tools=TOOL_SCHEMAS)
            if not resp.tool_calls:
                reply = resp.text or ""
                break
            messages.append(self._assistant_message(resp))
            messages.append(self._tool_results_message(resp.tool_calls))

        self._store.add_turn(self.conversation_id, self._next_seq, "agent", reply)
        self._next_seq += 1
        return reply

    def _assistant_message(self, resp) -> dict:
        content: list[dict] = []
        if resp.text:
            content.append({"type": "text", "text": resp.text})
        content.extend(
            {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input}
            for tc in resp.tool_calls
        )
        return {"role": "assistant", "content": content}

    def _tool_results_message(self, tool_calls) -> dict:
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": self._run_tool(tc.name, tc.input),
                }
                for tc in tool_calls
            ],
        }

    def _run_tool(self, name: str, tool_input: dict) -> str:
        if name == "search_recall":
            hits = self._recall.search(
                tool_input["query"], tool_input.get("k", 6)
            )
            # Recall is seal-scoped (ADR-0005): every hit is necessarily a
            # PAST, finished session, never the current one. Frame it that
            # way explicitly and date each hit so the Agent distinguishes
            # past from current without guessing.
            return json.dumps(
                {
                    "scope": "past_sealed_conversations",
                    "note": (
                        "These are PAST, finished Conversations from earlier "
                        "sessions — never the current session."
                    ),
                    "hits": [
                        {
                            "conversation_id": h.conversation_id,
                            "session": "past",
                            "date": h.date,
                            "summary_line": h.summary_line,
                            "snippet": h.snippet,
                        }
                        for h in hits
                    ],
                }
            )
        if name == "get_conversation":
            turns = self._recall.get_conversation(tool_input["conversation_id"])
            return json.dumps(
                [{"role": t.role, "content": t.content} for t in turns]
            )
        return f"unknown tool: {name}"

    def seal(self) -> None:
        """Seal the Conversation: write the final whole-Conversation Summary,
        index its User Turns + extracted Requests + the Summary into Recall,
        and stamp sealed_at. Idempotent — the Store ignores a re-Seal — so a
        deterministic exit hook can call it without guarding."""
        conv = self._store.get_conversation(self.conversation_id)
        if conv is None or conv.sealed_at is not None:
            return  # already Sealed — don't spend a second summarise call
        turns = self._store.turns_of(self.conversation_id)
        summary = self._summarizer.summarize(turns)
        self._store.seal_conversation(
            self.conversation_id, summary.prose, summary.outcomes
        )
        self._recall.add_units(self._units_for(turns, summary))

    def _units_for(self, turns, summary):
        units = [
            Unit(self.conversation_id, "user_turn", t.content, t.seq)
            for t in turns
            if t.role == "user"
        ]
        units += [
            Unit(self.conversation_id, "request", r) for r in summary.requests
        ]
        if summary.prose:
            units.append(Unit(self.conversation_id, "summary", summary.prose))
        return units
