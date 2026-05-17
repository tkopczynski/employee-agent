"""Retrieval-quality eval (ADR-0008).

A standalone, deterministic, no-LLM instrument that measures `Recall.search`
quality over a hand-authored corpus with the real `FastEmbedEmbedder`. Lives
outside `uv run pytest` (the real embedder is barred from the hermetic suite);
only the pure `scoring` math is unit-tested under pytest.
"""
