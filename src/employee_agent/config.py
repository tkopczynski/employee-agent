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

    def __init__(self, models: dict[str, str] | None = None):
        self._models = {**self.DEFAULT_MODELS, **(models or {})}

    def model_for(self, task: str) -> str:
        return self._models[task]
