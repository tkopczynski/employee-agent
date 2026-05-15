"""Recall — the searchable store of Sealed Conversations (CONTEXT.md).

A deep module: callers see Units, a search query, and Hits — never SQL, FTS5,
or vectors. It owns the indexed corpus (`search_units`) and the FTS5 keyword
index, living in the same single SQLite file as the Store (ADR-0001). The
seal-gate is a live SQL join onto `conversations.sealed_at`, so only Sealed
(past-session) Conversations are searchable (ADR-0005) and incremental
indexing during a session (a later issue) stays additive.

Semantic search (sqlite-vec) and RRF arrive in a later issue; the Embedder
seam is wired now so that is purely additive.
"""

import datetime as dt
import sqlite3
import threading
from dataclasses import dataclass


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


@dataclass(frozen=True)
class Unit:
    """One indexed item — a raw User Turn, an extracted Request, or the
    Summary. The indexed corpus is deliberately not the set of Turns."""

    conversation_id: int
    kind: str  # 'user_turn' | 'request' | 'summary'
    text: str
    source_turn_id: int | None = None


@dataclass(frozen=True)
class Hit:
    conversation_id: int
    date: str
    summary_line: str
    snippet: str


class Recall:
    def __init__(self, store, embedder, config):
        self._store = store
        self._embedder = embedder
        self._config = config
        # Recall owns its own connection to the same file the Store wrote
        # (ADR-0001). Cross-thread like the Store (TUI worker thread).
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(store.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS search_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                source_turn_id INTEGER,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS fts_search_units USING fts5(text)"
        )
        self._conn.commit()

    def add_units(self, units: list[Unit]) -> None:
        with self._lock:
            for unit in units:
                cur = self._conn.execute(
                    "INSERT INTO search_units "
                    "(conversation_id, kind, source_turn_id, text, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        unit.conversation_id,
                        unit.kind,
                        unit.source_turn_id,
                        unit.text,
                        _now_iso(),
                    ),
                )
                self._conn.execute(
                    "INSERT INTO fts_search_units (rowid, text) VALUES (?, ?)",
                    (cur.lastrowid, unit.text),
                )
            self._conn.commit()

    def search(self, query: str, k: int) -> list[Hit]:
        # Seal-gate: the join onto conversations + `sealed_at IS NOT NULL`
        # means only Sealed (past-session) Conversations are searchable.
        with self._lock:
            # bm25() is only valid directly against the FTS table (not inside
            # a grouped subquery), so rank units best-first in SQL, then fold
            # to one Hit per Conversation in Python: the first row seen for a
            # Conversation is its best-matching unit (the snippet), and
            # Conversations surface in best-unit order. k caps Conversations.
            rows = self._conn.execute(
                """
                SELECT su.conversation_id, c.started_at, c.summary_prose, su.text
                FROM fts_search_units
                JOIN search_units su ON su.id = fts_search_units.rowid
                JOIN conversations c ON c.id = su.conversation_id
                WHERE fts_search_units MATCH ? AND c.sealed_at IS NOT NULL
                ORDER BY bm25(fts_search_units)
                """,
                (query,),
            ).fetchall()
        hits: list[Hit] = []
        seen: set[int] = set()
        for r in rows:
            cid = r["conversation_id"]
            if cid in seen:
                continue
            seen.add(cid)
            hits.append(
                Hit(
                    conversation_id=cid,
                    date=r["started_at"][:10],
                    summary_line=r["summary_prose"],
                    snippet=r["text"],
                )
            )
            if len(hits) == k:
                break
        return hits

    def get_conversation(self, conversation_id: int):
        """Drill-in: the full ordered transcript (both roles) of a past
        Conversation, so bounded recall is not lossy. Only ever called with
        an id from a seal-gated `search` Hit, so no extra gate here."""
        return self._store.turns_of(conversation_id)
