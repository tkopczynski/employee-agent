"""Deterministic test doubles for the chat spine.

FakeLLMClient satisfies the same `complete(messages, model)` shape as the real
Anthropic-backed client, returns scripted replies, and records every call so
tests can assert which model the agent loop resolved.
"""


from employee_agent.llm import Response, ToolCall


class FakeLLMClient:
    """Scripted LLMClient. A reply entry is a str (final text), a ToolCall or
    list of ToolCalls (a tool-use turn), or a Response (used as-is). Records
    every call as (messages, model, tools) so tests can assert which model was
    resolved and which tools were offered."""

    def __init__(self, replies=None):
        self._replies = list(replies or [])
        self.calls = []  # list of (messages, model, tools) in call order

    def complete(self, messages, model, *, tools=None):
        self.calls.append((messages, model, tools or []))
        if not self._replies:
            raise AssertionError("FakeLLMClient.complete called more times than scripted")
        reply = self._replies.pop(0)
        if isinstance(reply, Response):
            return reply
        if isinstance(reply, ToolCall):
            return Response(tool_calls=[reply])
        if isinstance(reply, list):
            return Response(tool_calls=list(reply))
        return Response(text=reply)


class FakeEmbedder:
    """Deterministic Embedder placeholder. Keyword Recall does not embed, so
    this just satisfies the seam; the same text always maps to the same
    vector so a later semantic-recall issue can rely on determinism."""

    def __init__(self, dim=384):
        self._dim = dim

    def embed(self, texts):
        return [
            [float((hash(t) >> i) & 1) for i in range(self._dim)] for t in texts
        ]
