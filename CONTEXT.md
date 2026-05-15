# Employee Agent

A single-user personal AI assistant accessed via a TUI chat interface. The "employee" framing is product positioning — architecturally this is a one-user assistant, not a multi-actor team.

## Language

**Agent**:
The assistant the user talks to.
_Avoid_: Bot, assistant (when ambiguous), employee (the product name, not a domain term)

**User**:
The single human who owns and talks to the Agent.
_Avoid_: Owner, operator

**Conversation**:
One session with the Agent — the sequence of Turns from launching the TUI to exiting it. Starts on launch, **Sealed** on exit. Not resumable; a new launch is always a new Conversation.
_Avoid_: Chat, session, thread

**Turn**:
One user message plus the Agent's response within a Conversation.
_Avoid_: Message, exchange

**Compaction**:
Within a live session, condensing the oldest hot Turns into a running Summary to keep the active context bounded. The raw compacted Turns are written to **Recall** storage incrementally (to amortise embedding cost) but do not become *searchable* until the Conversation is **Sealed**.
_Avoid_: Truncation, eviction, summarisation (too generic)

**Sealing**:
The transition that happens when a session ends: the Conversation is closed (no more Turns), a final whole-Conversation Summary is written, and any not-yet-indexed Turns are added to **Recall**. Sealing is what makes a Conversation searchable — only Sealed Conversations appear in Recall.
_Avoid_: Closing, archiving, finalising

**Summary**:
A generated condensation of a span of Turns. The *running* Summary produced during **Compaction** is transient hot-context working state. The *final* whole-Conversation Summary produced at **Sealing** is the one indexed into **Recall**.
_Avoid_: Abstract, digest, TLDR

**Recall**:
The searchable store of **Sealed** (past-session) Conversations — their Turns and final Summaries. Lets the User ask "when did I ... X" about earlier sessions without loading history into the active context. The current live session is **not** in Recall until it is Sealed.
_Avoid_: Memory (overloaded), history, archive

## Relationships

- A **User** has many **Conversations**; each **Conversation** is exactly one session
- A **Conversation** contains many **Turns** in order
- A **Conversation** is open (the live session) or **Sealed** (a past session); only **Sealed** Conversations are in **Recall**
- **Compaction** writes compacted **Turns** to Recall storage during a session, but they are searchable only once the Conversation is **Sealed**
- A Conversation has many transient running **Summaries** (from **Compaction**) and exactly one final **Summary** (at **Sealing**, the indexed one)

## Example dialogue

> **User:** "When did I ask you to prepare a report on the Q1 numbers?"
> **Agent:** "On 2026-04-12, in an earlier session. You asked me to draft a one-pager on Q1 revenue."

The query is answered from **Recall**, which holds only **Sealed** Conversations (past sessions). The current session's own earlier Turns are not in Recall until it is Sealed — while the session is live, the Agent relies on hot context (including the running **Compaction** Summary) instead.

## Flagged ambiguities

- "Employee" — the product name and metaphor, **not** a domain term. The Agent is *framed* as an employee for product positioning; it is not modelled as one (no role, no team, no manager-of-the-agent hierarchy).
- **Sealing vs searchability** — re-resolved (2026-05-15). First decoupled (searchable at **Compaction**); then **resume was dropped** to cut complexity, so deliberately re-coupled: indexing into Recall storage still happens incrementally at **Compaction** (to amortise cost), but *searchability* is gated by **Sealing**. Only Sealed (past-session) Conversations are returned by `search_recall`; the live session relies on hot context. Net: a Conversation = one session, no resume, no current-session hits from search.
