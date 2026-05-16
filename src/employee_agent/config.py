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

    # Compaction budgets (PRD/ADR-0003): trigger when hot context exceeds a
    # fraction of the active model's context window; keep a verbatim Turn tail
    # and a running Summary, each under its own cap so the bound cannot leak.
    # Overridable so a human can tune the constants against the real model
    # (the HITL step) and the cost bound stays measurable.
    DEFAULT_COMPACTION = {
        "context_window": 200_000,
        "trigger_fraction": 0.5,
        "tail_token_budget": 4000,
        "summary_token_cap": 2000,
    }

    # The Workspace is the Agent's entire filesystem surface (ADR-0007). Its
    # root is configuration, never hardcoded — the same everything-configurable
    # ethos as the model map and the cost caps above.
    DEFAULT_WORKSPACE = {"root": "workspace"}

    # Execution is a cost/time surface (ADR-0007, PRD US-12/US-15/US-16): the
    # pinned image tag and the CPU / memory / wall-clock caps are all
    # configuration, never hardcoded, exactly like the recall/compaction caps.
    # The real Docker-backed Sandbox (Issue 04) reads every knob from here, so
    # the cost-vs-capability trade-off stays tunable and measurable.
    DEFAULT_SANDBOX = {
        "command_timeout": 30,
        "image": "employee-agent-sandbox:1",
        "cpus": "1.0",
        "memory": "512m",
    }

    def __init__(
        self,
        models: dict[str, str] | None = None,
        recall: dict[str, int] | None = None,
        compaction: dict | None = None,
        workspace: dict | None = None,
        sandbox: dict | None = None,
    ):
        self._models = {**self.DEFAULT_MODELS, **(models or {})}
        self._recall = {**self.DEFAULT_RECALL, **(recall or {})}
        self._compaction = {**self.DEFAULT_COMPACTION, **(compaction or {})}
        self._workspace = {**self.DEFAULT_WORKSPACE, **(workspace or {})}
        self._sandbox = {**self.DEFAULT_SANDBOX, **(sandbox or {})}

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

    @property
    def compaction_context_window(self) -> int:
        return self._compaction["context_window"]

    @property
    def compaction_trigger_fraction(self) -> float:
        return self._compaction["trigger_fraction"]

    @property
    def compaction_tail_token_budget(self) -> int:
        return self._compaction["tail_token_budget"]

    @property
    def compaction_summary_token_cap(self) -> int:
        return self._compaction["summary_token_cap"]

    @property
    def workspace_root(self) -> str:
        return self._workspace["root"]

    @property
    def sandbox_command_timeout(self) -> float:
        return self._sandbox["command_timeout"]

    @property
    def sandbox_image(self) -> str:
        return self._sandbox["image"]

    @property
    def sandbox_cpus(self) -> str:
        return self._sandbox["cpus"]

    @property
    def sandbox_memory(self) -> str:
        return self._sandbox["memory"]
