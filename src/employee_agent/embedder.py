"""The thin Embedder seam (ADR-0002).

`Embedder` is the entire contract Recall depends on for vectors: one method,
no fastembed/ONNX types leaking out. Tests substitute a deterministic fake;
the real local adapter (fastembed `bge-small-en-v1.5`, 384-dim) arrives with
the semantic-recall issue. Keyword Recall does not embed, but the seam exists
now so that semantic recall is a purely additive change.
"""

from typing import Protocol


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedEmbedder:
    """Local embeddings via fastembed (ADR-0002), `bge-small-en-v1.5`, 384-dim.
    Intentionally thin, untested glue (no model download in tests) — the
    keyword-recall path does not embed, so this stays dormant until semantic
    recall. The model is loaded lazily on first embed."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self._model_name = model_name
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(self._model_name)
        return [v.tolist() for v in self._model.embed(texts)]
