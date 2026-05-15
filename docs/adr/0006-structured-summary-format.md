# Structured Summary format: prose recap + Requests + Outcomes

A Summary is not free-form prose. It is a short narrative recap **plus** two explicit structured lists: `Requests` (what the User asked the Agent to do) and `Outcomes` (what was decided or produced). Each `Requests` item is embedded into Recall as its own unit, alongside the raw User Turns.

Why: the headline query the project was started for ("when did I ask you to prepare a report on X") is request-shaped, not topic-shaped. Burying requests in prose makes that query a weak semantic match and dilutes the FTS5 keyword signal. Promoting requests to first-class, separately-embedded, normalised units makes the headline feature land. The deliberate redundancy with raw User Turns (noisy, multiple phrasings) vs extracted Requests (clean, normalised) is a feature — two granularities improve recall hit rate. The prose recap is retained so topical browse queries and the running Compaction Summary still work; B is the only option covering both query shapes.

Rejected: free-form prose (request-precision lost); pure structured extraction (browse/narrative lost); one-line label (fails the headline query outright).

Consequence: **the Summary format is sticky.** Changing it later leaves old Sealed Conversations with old-format Summaries — Recall stays inconsistent until the entire history is re-summarised, which is an LLM cost over all past Conversations, not a migration script. Same stickiness class as the embedding model (ADR-0002). Treat a format change as a full-corpus re-summarisation.
