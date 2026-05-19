"""Chat-only Textual shell over the agent loop.

Deliberately thin presentation glue — all behaviour lives in `Agent`. The
blocking LLM call runs in a worker thread so the TUI stays responsive.
"""

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Static

from .agent import Agent


class ChatApp(App):
    CSS = """
    #log { padding: 1 2; }
    Input { dock: bottom; }
    """

    def __init__(self, agent: Agent) -> None:
        super().__init__()
        self._agent = agent

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="log")
        yield Input(placeholder="Talk to your agent…")

    @on(Input.Submitted)
    def _on_submit(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        self._append("You", text)
        self._respond(text)

    @work(thread=True)
    def _respond(self, text: str) -> None:
        reply = self._agent.send(text)
        self.call_from_thread(self._append, "Agent", reply)

    def _append(self, who: str, text: str) -> None:
        log = self.query_one("#log", VerticalScroll)
        log.mount(Static(f"[b]{who}:[/b] {text}"))
        log.scroll_end(animate=False)
