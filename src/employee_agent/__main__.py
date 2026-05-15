"""Entrypoint: one launch == one new Conversation (ADR-0005).

Wires Config + Store + the real LLM adapter into the Agent, then hands it to
the TUI. Exiting the TUI ends the process and thus the Conversation; deterministic
Sealing on exit arrives with a later issue.
"""

import os
import sys

from .agent import Agent
from .config import Config
from .llm import AnthropicLLMClient
from .store import Store
from .tui import ChatApp


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set")
    db_path = os.environ.get("EMPLOYEE_AGENT_DB", "employee_agent.sqlite")
    store = Store(db_path)
    agent = Agent(llm=AnthropicLLMClient(), store=store, config=Config())
    ChatApp(agent).run()


if __name__ == "__main__":
    main()
