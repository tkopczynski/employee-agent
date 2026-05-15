"""The thin LLM seam.

`LLMClient` is the entire contract the agent loop depends on: one method,
no Anthropic types leaking out. It returns a `Response` that is either final
text or a list of `ToolCall`s the Agent must execute and feed back. Tests
substitute a structural fake; the real adapter below is intentionally thin,
untested glue (no network in tests).
"""

import os
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass(frozen=True)
class Response:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(Protocol):
    def complete(
        self, messages: list[dict], model: str, *, tools: list[dict] | None = None
    ) -> Response: ...


class AnthropicLLMClient:
    def __init__(self, api_key: str | None = None):
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def complete(
        self, messages: list[dict], model: str, *, tools: list[dict] | None = None
    ) -> Response:
        resp = self._client.messages.create(
            model=model,
            max_tokens=1024,
            messages=messages,
            **({"tools": tools} if tools else {}),
        )
        text = "".join(b.text for b in resp.content if b.type == "text") or None
        tool_calls = [
            ToolCall(id=b.id, name=b.name, input=b.input)
            for b in resp.content
            if b.type == "tool_use"
        ]
        return Response(text=text, tool_calls=tool_calls)
