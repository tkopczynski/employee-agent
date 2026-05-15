"""The thin LLM seam.

`LLMClient` is the entire contract the agent loop depends on: one method,
no Anthropic types leaking out. Tests substitute a structural fake; the real
adapter below is intentionally thin, untested glue (no network in tests).
"""

import os
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, messages: list[dict], model: str) -> str: ...


class AnthropicLLMClient:
    def __init__(self, api_key: str | None = None):
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def complete(self, messages: list[dict], model: str) -> str:
        resp = self._client.messages.create(
            model=model,
            max_tokens=1024,
            messages=messages,
        )
        return "".join(block.text for block in resp.content if block.type == "text")
