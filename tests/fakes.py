"""Deterministic test doubles for the chat spine.

FakeLLMClient satisfies the same `complete(messages, model)` shape as the real
Anthropic-backed client, returns scripted replies, and records every call so
tests can assert which model the agent loop resolved.
"""


from employee_agent.llm import Response, ToolCall
from employee_agent.sandbox import ExecResult
from employee_agent.summarizer import Summary
from employee_agent.web import SearchResult


class FakeLLMClient:
    """Scripted LLMClient. A reply entry is a str (final text), a ToolCall or
    list of ToolCalls (a tool-use turn), or a Response (used as-is). Records
    every call as (messages, model, tools) so tests can assert which model was
    resolved and which tools were offered."""

    def __init__(
        self,
        replies: list[str | ToolCall | list[ToolCall] | Response] | None = None,
    ) -> None:
        self._replies: list[str | ToolCall | list[ToolCall] | Response] = list(
            replies or []
        )
        self.calls = []  # list of (messages, model, tools) in call order

    def complete(
        self, messages: list[dict], model: str, *, tools: list[dict] | None = None
    ) -> Response:
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


class FakeSandbox:
    """Deterministic Sandbox double (Issue 03), mirroring FakeWebClient.
    `results` maps a command to a canned ExecResult; an unmapped command is a
    benign empty success. Records every (command, timeout) so tests can assert
    the agent loop routes run_command through the seam without Docker."""

    def __init__(self, results=None):
        self._results = results or {}
        self.calls = []  # list of (command, timeout) in call order

    def run(self, command, timeout):
        self.calls.append((command, timeout))
        return self._results.get(
            command,
            ExecResult(stdout="", stderr="", exit_code=0, timed_out=False),
        )


class FakeSummarizer:
    """Deterministic Summarizer double for Compactor tests (Issue 06).

    `prose_for` is called with the turns it was asked to summarise and returns
    the running-Summary prose, so a test can make the prose grow without bound
    to exercise the running-Summary cap. Records every call's turns so a test
    can assert what was folded into each regeneration. Defaults to a short
    constant recap (the common case)."""

    def __init__(self, prose_for=None):
        self._prose_for = prose_for or (lambda turns: "recap")
        self.calls = []  # list of the turns lists it was asked to summarise

    def summarize(self, turns) -> Summary:
        self.calls.append(list(turns))
        return Summary(prose=self._prose_for(turns), requests=[], outcomes=[])


class FakeRecall:
    """Recall double that records the Units handed to it (Issue 06), so a test
    can assert compacted Turns are written to Recall storage exactly once."""

    def __init__(self):
        self.added = []  # flat list of every Unit passed to add_units

    def add_units(self, units):
        self.added.extend(units)


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
