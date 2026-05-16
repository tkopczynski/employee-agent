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

**Workspace**:
The Agent's durable working area on disk and its *entire* filesystem surface — the only place it may read, write, or run code; it has no filesystem access of any kind outside it. Bounded: code the Agent runs in the Workspace cannot reach the network or touch anything outside it. Persists across Conversations; **Sealing** does not affect it. Separate from **Recall** (memory of past sessions) — the Workspace is files, not searchable history.
_Avoid_: Sandbox (the containment mechanism, not the concept), scratch dir, workdir, temp

## Relationships

- A **User** has many **Conversations**; each **Conversation** is exactly one session
- A **Conversation** contains many **Turns** in order
- A **Conversation** is open (the live session) or **Sealed** (a past session); only **Sealed** Conversations are in **Recall**
- **Compaction** writes compacted **Turns** to Recall storage during a session, but they are searchable only once the Conversation is **Sealed**
- A Conversation has many transient running **Summaries** (from **Compaction**) and exactly one final **Summary** (at **Sealing**, the indexed one)
- The **Workspace** is the **Agent**'s entire filesystem surface: it may read, write, and run code there and nowhere else
- The **Workspace** is an airlock: inputs enter only by the **User** placing files in it or the **Agent** writing fetched web data into it — the Agent cannot pull files off the rest of the disk
- A **Workspace** persists across **Conversations** and is a separate axis from **Recall**: **Sealing** finalises a Conversation into Recall but never touches the Workspace
- Network is an **Agent** capability, not a **Workspace** one: code run in the Workspace has no network; the Agent fetches external data (web tools) and writes it into the Workspace for code to read

## Example dialogue

> **User:** "When did I ask you to prepare a report on the Q1 numbers?"
> **Agent:** "On 2026-04-12, in an earlier session. You asked me to draft a one-pager on Q1 revenue."

The query is answered from **Recall**, which holds only **Sealed** Conversations (past sessions). The current session's own earlier Turns are not in Recall until it is Sealed — while the session is live, the Agent relies on hot context (including the running **Compaction** Summary) instead.

> **User:** "Compute the median of the numbers in `~/projects/data.csv`."
> **Agent:** "I can't read files outside the **Workspace**. Drop `data.csv` into the Workspace and I'll write and run a script over it there."

The Agent has no filesystem access outside the **Workspace** (strict airlock). The User stages the input by placing it in the Workspace; the Agent then writes a script and runs it there, with no network. Had the data been on the web instead, the Agent would have fetched it (web tools) and written it into the Workspace itself.

## Flagged ambiguities

- "Employee" — the product name and metaphor, **not** a domain term. The Agent is *framed* as an employee for product positioning; it is not modelled as one (no role, no team, no manager-of-the-agent hierarchy).
- "fetch and write data from a directory" (2026-05-16) — used to mean three distinct capabilities. Resolved: the **Workspace** is the Agent's entire filesystem surface (read + write + execute), a strict airlock with no network for executed code and no Agent filesystem access outside it. The Agent's *web* tools (`fetch_url`/`web_search`) are unaffected — those are web reads, not filesystem reads. Residual, consciously deferred: a prompt-injected Agent can still exfiltrate *Workspace contents* via `fetch_url` (blast radius bounded to the Workspace by the airlock).
- **Sealing vs searchability** — re-resolved (2026-05-15). First decoupled (searchable at **Compaction**); then **resume was dropped** to cut complexity, so deliberately re-coupled: indexing into Recall storage still happens incrementally at **Compaction** (to amortise cost), but *searchability* is gated by **Sealing**. Only Sealed (past-session) Conversations are returned by `search_recall`; the live session relies on hot context. Net: a Conversation = one session, no resume, no current-session hits from search.
