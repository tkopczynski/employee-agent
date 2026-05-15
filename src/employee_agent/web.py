"""The thin web seam for the read-only web tools (PRD Q9, Issue 05).

`WebClient` is the entire contract the web tools depend on: search the web,
fetch a page. No provider types leak out. Tests substitute a structural fake
so they stay offline (PRD Testing Decisions); the real adapter is thin,
untested glue (no network in tests).
"""

import os
from dataclasses import dataclass
from typing import Protocol

_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class WebClient(Protocol):
    def search(self, query: str) -> list[SearchResult]: ...

    def fetch(self, url: str) -> str: ...


class AnthropicWebClient:
    """Real adapter: search via the Anthropic API's server-side web_search
    tool (no extra vendor), fetch via stdlib urllib. Intentionally thin,
    untested glue — exercised only in production, faked in tests."""

    def __init__(self, api_key: str | None = None):
        from anthropic import Anthropic

        self._client = Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    def search(self, query: str) -> list[SearchResult]:
        resp = self._client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": query}],
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
        )
        results: list[SearchResult] = []
        for block in resp.content:
            if getattr(block, "type", None) != "web_search_tool_result":
                continue
            for item in block.content:
                results.append(
                    SearchResult(
                        title=getattr(item, "title", "") or "",
                        url=getattr(item, "url", "") or "",
                        snippet=getattr(item, "encrypted_content", "") or "",
                    )
                )
        return results

    def fetch(self, url: str) -> str:
        import urllib.request

        # Many sites 403 the default "Python-urllib" agent; identify as a
        # normal browser so a plain read-only GET is not rejected.
        req = urllib.request.Request(
            url, headers={"User-Agent": _BROWSER_UA}
        )
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
            return r.read().decode("utf-8", errors="replace")
