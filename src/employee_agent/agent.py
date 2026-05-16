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
import logging

from .compactor import Compactor
from .recall import Unit
from .summarizer import Summarizer
from .tools import LocalTools
from .workspace import Workspace

logger = logging.getLogger("employee_agent.agent")

# The agent-pulled recall surface (PRD Q8). The local tools (file/web/clock,
# plus Workspace-confined write_file) hang off the same loop via LocalTools —
# adding them is purely additive: the recall schemas below are unchanged.
RECALL_SCHEMAS = [
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
    def __init__(self, llm, store, config, recall, web=None):
        self._llm = llm
        self._store = store
        self._config = config
        self._recall = recall
        self._tools = LocalTools(web, Workspace(config.workspace_root))
        self._summarizer = Summarizer(llm, config)
        self.conversation_id = store.start_conversation()
        self._compactor = Compactor(
            self._summarizer, config, self.conversation_id, recall
        )
        self._next_seq = 0

    def send(self, user_input: str) -> str:
        self._store.add_turn(self.conversation_id, self._next_seq, "user", user_input)
        self._next_seq += 1
        self._compactor.observe("user", user_input)

        model = self._config.model_for("agent_loop")
        tools = RECALL_SCHEMAS + self._tools.SCHEMAS
        # Hot context (running Summary + verbatim tail) is the cross-Turn
        # bounded base; it already ends with the just-observed User message.
        # The tool round-trips below stay loop-local — they are intra-Turn
        # hot-context mechanics, not Turns, so the Compactor never sees them.
        messages = self._compactor.hot_context()
        logger.info(
            "agent_loop",
            extra={
                "conversation_id": self.conversation_id,
                "task": "agent_loop",
                "model": model,
                "hot_context_messages": len(messages),
            },
        )
        reply = ""
        for _ in range(_MAX_TOOL_STEPS):
            resp = self._llm.complete(messages, model, tools=tools)
            if not resp.tool_calls:
                reply = resp.text or ""
                break
            messages.append(self._assistant_message(resp))
            messages.append(self._tool_results_message(resp.tool_calls))

        self._store.add_turn(self.conversation_id, self._next_seq, "agent", reply)
        self._next_seq += 1
        self._compactor.observe("assistant", reply)
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
            # k falls through to the configured default (PRD: K is config,
            # not hardcoded) unless the model asked for a specific size.
            hits = self._recall.search(
                tool_input["query"], tool_input.get("k")
            )
            logger.info(
                "search_recall",
                extra={
                    "conversation_id": self.conversation_id,
                    "result_hits": len(hits),
                    "result_tokens": sum(
                        len(h.summary_line or "") // 4 + len(h.snippet or "") // 4
                        for h in hits
                    ),
                },
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
        return self._tools.run(name, tool_input)

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
        self._recall.add_units(self._units_for(summary))

    def _units_for(self, summary):
        # Only the still-hot User Turns are indexed here; the ones compacted
        # away during the session were already handed to Recall by the
        # Compactor — so every User Turn is indexed exactly once (ADR-0004).
        units = [
            Unit(self.conversation_id, "user_turn", text)
            for text in self._compactor.hot_user_turns()
        ]
        units += [
            Unit(self.conversation_id, "request", r) for r in summary.requests
        ]
        if summary.prose:
            units.append(Unit(self.conversation_id, "summary", summary.prose))
        return units
