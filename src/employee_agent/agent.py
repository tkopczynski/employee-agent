"""The agent loop — the spine everything else hangs off.

For issue 01 it orchestrates: open a Conversation on construction. Tools,
Compaction and Recall are deliberately absent; they hang off this spine later.
"""


class Agent:
    def __init__(self, llm, store, config):
        self._llm = llm
        self._store = store
        self._config = config
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
