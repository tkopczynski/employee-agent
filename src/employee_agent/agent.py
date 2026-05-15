"""The agent loop — the spine everything else hangs off.

It orchestrates: open a Conversation on construction; on Sealing, condense the
Conversation's Turns into the final structured Summary via the Summarizer.
Tools, Compaction and Recall are deliberately absent; they hang off this spine
later.
"""

from .summarizer import Summarizer


class Agent:
    def __init__(self, llm, store, config):
        self._llm = llm
        self._store = store
        self._config = config
        self._summarizer = Summarizer(llm, config)
        self.conversation_id = store.start_conversation()
        self._next_seq = 0

    def send(self, user_input: str) -> str:
        self._store.add_turn(self.conversation_id, self._next_seq, "user", user_input)
        self._next_seq += 1

        model = self._config.model_for("agent_loop")
        messages = [{"role": "user", "content": user_input}]
        reply = self._llm.complete(messages, model)

        self._store.add_turn(self.conversation_id, self._next_seq, "agent", reply)
        self._next_seq += 1
        return reply

    def seal(self) -> None:
        """Seal the Conversation: write the final whole-Conversation Summary
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
