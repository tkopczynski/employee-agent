# Compaction indexes into Recall incrementally, not at Sealing

**Status:** Partially superseded by ADR-0005. The incremental-indexing decision below still holds (kept for amortised embedding cost). The "searchable while the Conversation is still open" consequence does **not** — resume was dropped and `search_recall` is now scoped to Sealed Conversations only.

With rolling compaction (ADR-0003) on resumable, potentially weeks-long Conversations, the original glossary rule "only Sealed Conversations are recallable" created a blind spot: a long *open* Conversation's early Turns get compacted out of hot context but, not being Sealed, would be searchable nowhere — breaking the headline "when did I ask about X" query *within a single long Conversation*.

Decision: when Turns are compacted out of the active context, they are embedded and added to **Recall** immediately. Sealing is no longer the indexing trigger; it is purely a lifecycle transition (the Conversation can no longer be extended, and a final whole-Conversation Summary is written).

Why: it makes the headline feature correct in the normal case (one long resumable thread), and it decouples two things that were wrongly conflated — *lifecycle* (open vs Sealed) and *searchability* (hot vs cold). Searchability now tracks coldness, which is the cost-relevant property the project is about.

Rejected: index only at Seal (simpler, but a long open Conversation can never recall its own early content — fails the exact example query the project was started for).

Consequence: `search_recall` can return hits that belong to the *current, still-open* Conversation, not just past ones. The Agent must be able to tell "this came from earlier in our current Conversation" apart from "this is a past Conversation," because the right response differs. That distinction is an open design question (see Q15).
