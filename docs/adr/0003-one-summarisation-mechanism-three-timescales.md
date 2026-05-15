# Summarisation is one mechanism at three time-scales

The system summarises in three places that look like separate features but are the same operation: **compaction** (summarise the old part of the *active* Conversation to bound its context), **Sealing** (summarise a *whole* Conversation when it closes), and **Recall** (search across summarised/indexed history). We decided to design these as one subsystem — "bounded hot working set + searchable cold store, with summarisation as the bridge" — rather than three unrelated features.

Why: the project's actual goal is learning cost-effective operation over a growing corpus. A unified model makes token cost bounded and observable everywhere, and keeps the architecture to a single coherent idea instead of three. v0 ships rolling compaction (C) and Seal-time summaries; the natural end state ("the active Conversation's cold tail is searchable exactly like Recall") is a later tool addition, not a rewrite — so storage is designed to not foreclose it.

Rejected: send-the-whole-Conversation every Turn (O(n²) cost — the anti-pattern the project exists to learn past); sliding window (lossy for resumable weeks-long Conversations); treating compaction and Recall as independent features (duplicates the summarisation + storage design twice).

Consequence: the storage schema must treat compacted-away Turns and Sealed Turns uniformly, so that "make the cold tail searchable" is additive. See ADR-0004 (pending) for whether compaction indexes into Recall incrementally or only at Seal.
