"""Deterministic test doubles for the chat spine.

FakeLLMClient satisfies the same `complete(messages, model)` shape as the real
Anthropic-backed client, returns scripted replies, and records every call so
tests can assert which model the agent loop resolved.
"""


from employee_agent.llm import Response, ToolCall
from employee_agent.web import SearchResult


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


class FakeWebClient:
    """Deterministic WebClient double. `results` maps a query to canned
    SearchResults; `pages` maps a URL to canned page text. Records every
    search/fetch so tests can assert routing without touching the network."""

    def __init__(self, results=None, pages=None):
        self._results = results or {}
        self._pages = pages or {}
        self.searched = []
        self.fetched = []

    def search(self, query):
        self.searched.append(query)
        return [SearchResult(*r) for r in self._results.get(query, [])]

    def fetch(self, url):
        self.fetched.append(url)
        return self._pages.get(url, "")


class TopicEmbedder:
    """Deterministic, controllable Embedder for tests (Issue 04).

    Texts are grouped into named topics; same-topic texts embed to the same
    orthogonal basis vector (semantically identical), different topics are
    orthogonal (maximally far), and any unregistered text embeds to one shared
    "unknown" vector orthogonal to every topic. Tests dictate which phrases are
    semantically close and assert ordering/recall — never raw vectors (PRD
    Testing Decisions). With no topics it is an inert constant embedder: the
    semantic arm contributes uniformly so keyword ranking dominates and
    keyword-only tests stay deterministic.
    """

    def __init__(self, topics=None, dim=384):
        self._dim = dim
        self._axis_of = {}
        for axis, texts in enumerate((topics or {}).values()):
            for text in texts:
                self._axis_of[text] = axis
        self._unknown_axis = len(topics or {})

    def embed(self, texts):
        out = []
        for text in texts:
            vec = [0.0] * self._dim
            vec[self._axis_of.get(text, self._unknown_axis)] = 1.0
            out.append(vec)
        return out
