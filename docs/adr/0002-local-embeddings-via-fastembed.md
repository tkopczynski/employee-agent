# Local embeddings via fastembed

Recall's vector search needs an embedding model. Since Anthropic (the chosen LLM provider, ADR-0001) has no embeddings API, this is a separate decision. We chose **local embeddings via `fastembed`** (ONNX runtime, `bge-small-en-v1.5`) rather than a hosted embeddings API.

Why: it keeps the product self-contained and single-process — consistent with ADR-0001. The Agent's reasoning depends on Claude (network), but its *memory* should not also depend on a second vendor. Recall is the long-lived, years-of-data part of the system; keeping it dependency-light and offline-capable matters more here than the marginal quality gain from a hosted model. `fastembed` over `sentence-transformers` because the latter pulls in ~2GB of PyTorch for no benefit at this scale.

Rejected: OpenAI `text-embedding-3-small` (better quality, trivial code, but adds a second API provider + key, a network call on every Seal and every recall, and breaks offline operation); `sentence-transformers` (PyTorch install tax).

Consequence: **the embedding model is sticky.** Changing it later requires re-embedding *all* of Recall — vectors from different models are not comparable. Treat a model change as a full Recall re-index, not a config tweak.
