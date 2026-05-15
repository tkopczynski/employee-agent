"""Entrypoint: one launch == one new Conversation (ADR-0005).

Wires Config + Store + the real LLM adapter into the Agent, then hands it to
the TUI. `App.run()` returns when the TUI exits, so Sealing here is
deterministic: the finished Conversation is always Sealed before the process
ends. Thin glue — the Sealing behaviour itself lives in `Agent.seal()`.
"""

import os
import sys

from .agent import Agent
from .config import Config
from .embedder import FastEmbedEmbedder
from .llm import AnthropicLLMClient
from .recall import Recall
from .store import Store
from .tui import ChatApp


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set")
    db_path = os.environ.get("EMPLOYEE_AGENT_DB", "employee_agent.sqlite")
    store = Store(db_path)
    recall = Recall(store, FastEmbedEmbedder(), Config())
    agent = Agent(
        llm=AnthropicLLMClient(), store=store, config=Config(), recall=recall
    )
    ChatApp(agent).run()
    agent.seal()


if __name__ == "__main__":
    main()
