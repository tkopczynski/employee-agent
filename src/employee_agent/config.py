"""Configuration for the Employee Agent.

The per-task model map is the central learning artifact (PRD Q19): it lets the
recall-quality-vs-cost trade-off be measured by swapping models per task. Model
names are never hardcoded in the agent loop — they are resolved from here.
"""


class Config:
    DEFAULT_MODELS = {
        "agent_loop": "claude-sonnet-4-6",
        "summarise": "claude-haiku-4-5",
    }

    # Recall result budget + fusion constant (PRD "Recall retrieval": K and
    # the token ceiling are config; RRF k≈60, no weight tuning). Overridable
    # like the model map so the recall-quality-vs-cost trade-off stays
    # measurable.
    DEFAULT_RECALL = {"k": 6, "token_ceiling": 2000, "rrf_k": 60}

    def __init__(
        self,
        models: dict[str, str] | None = None,
        recall: dict[str, int] | None = None,
    ):
        self._models = {**self.DEFAULT_MODELS, **(models or {})}
        self._recall = {**self.DEFAULT_RECALL, **(recall or {})}

    def model_for(self, task: str) -> str:
        return self._models[task]

    @property
    def recall_k(self) -> int:
        return self._recall["k"]

    @property
    def recall_token_ceiling(self) -> int:
        return self._recall["token_ceiling"]

    @property
    def rrf_k(self) -> int:
        return self._recall["rrf_k"]
