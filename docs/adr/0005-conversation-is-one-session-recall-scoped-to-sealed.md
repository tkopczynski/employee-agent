# Conversation = one session; search_recall scoped to Sealed Conversations

Partially supersedes ADR-0004 (retains its incremental-indexing decision; reverses its "searchable while open" scope).

Resume across sessions was dropped. It was not a must-have, but it was generating disproportionate complexity: a resume picker, lazy-seal-after-inactivity, "open Conversations must be searchable," and a current-vs-past hit provenance problem. A **Conversation is now exactly one session** — it starts on launch and is Sealed deterministically on exit. There is no resume and no `/new` (start fresh = exit and relaunch).

`search_recall` is scoped to **Sealed** (past-session) Conversations only. Compaction still writes compacted Turns into Recall storage incrementally during a session — this amortises embedding cost and is the cost lesson the project exists to learn, so it is kept — but those Turns do not become *searchable* until the session is Sealed. Within a live session the Agent relies on hot context (including the running Compaction Summary) for "what did we cover earlier."

Why: this is the actual simplification. Dropping resume alone left Compaction and the provenance problem intact; scoping `search_recall` to Sealed Conversations is what eliminates them. The lost capability — verbatim recall of a detail compacted out of the *current* multi-hour session before it ends — is narrow and rare for a pet project where a session is a single sitting. The common precise-recall need is cross-session, which this handles fully.

Rejected: keeping `search_recall` spanning the live session's cold tail (more precise in a marathon session, but reintroduces the provenance flag / scope machinery for a capability deemed not must-have).

Consequence: the Q15 current-vs-past provenance question is moot — `search_recall` can never return a current-Conversation hit. ADR-0003's "one mechanism, three time-scales" still holds: Compaction condenses + indexes incrementally, Sealing finalises + flips searchability, Recall searches.
