"""Deterministic test doubles for the chat spine.

FakeLLMClient satisfies the same `complete(messages, model)` shape as the real
Anthropic-backed client, returns scripted replies, and records every call so
tests can assert which model the agent loop resolved.
"""


class FakeLLMClient:
    def __init__(self, replies=None):
        self._replies = list(replies or [])
        self.calls = []  # list of (messages, model) in call order

    def complete(self, messages, model):
        self.calls.append((messages, model))
        if not self._replies:
            raise AssertionError("FakeLLMClient.complete called more times than scripted")
        return self._replies.pop(0)
