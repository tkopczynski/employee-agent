"""Recall — the searchable store of Sealed Conversations (CONTEXT.md).

A deep module: callers see Units, a search query, and Hits — never SQL, FTS5,
or vectors. It owns the indexed corpus (`search_units`) and the FTS5 keyword
index, living in the same single SQLite file as the Store (ADR-0001). The
seal-gate is a live SQL join onto `conversations.sealed_at`, so only Sealed
(past-session) Conversations are searchable (ADR-0005) and incremental
indexing during a session (a later issue) stays additive.

Retrieval is hybrid: an FTS5 keyword arm and a sqlite-vec semantic arm
(units embedded locally via the Embedder seam, ADR-0002), fused by Reciprocal
Rank Fusion (no score normalisation or weight tuning), then bounded by a
top-K + token-ceiling budget. Both arms are seal-gated, so semantic recall
obeys ADR-0005 exactly like keyword.
"""

import datetime as dt
import re
import sqlite3
import threading
from dataclasses import dataclass
from typing import Protocol

import sqlite_vec

from .config import Config
from .embedder import Embedder
from .store import Store, Turn


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _fts5_match_query(query: str) -> str | None:
    """Turn LLM/user free text into a safe FTS5 MATCH expression.

    The query is ordinary phrasing, never an FTS5 expression: `AC/DC`,
    `opening-quarter`, `notes: Q1` are all normal asks, but `/ - : * " ( )`
    are FTS5 query syntax and crash MATCH unsanitised. We extract the
    tokenisable word runs and quote each as an FTS5 string literal, joined by
    spaces (implicit AND) so multi-word semantics match the old raw behaviour
    for punctuation-free queries. Returns None when nothing is tokenisable
    (caller skips the keyword arm rather than issuing an empty MATCH)."""
    words = re.findall(r"\w+", query, re.UNICODE)
    if not words:
        return None
    return " ".join(f'"{w}"' for w in words)


def _est_tokens(text: str | None) -> int:
    """Deterministic, dependency-free token estimate (~4 chars/token). Used
    only to size the result budget — we never ship a tokenizer for that."""
    if not text:
        return 0
    return -(-len(text) // 4)  # ceil division


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


# The one-method seam the Compactor depends on: where compacted (cold) User
# Turns are written. Narrow by design — the Compactor only *writes* units;
# `search`/`get_conversation` are the Agent's surface, and the Agent always
# holds a concrete `Recall`, never a Fake, so that side stays concrete. This
# Protocol exists only because a Fake double is substituted (`FakeRecall`):
# the concrete `Recall` also satisfies it, so a Fake drifting is a type error.
class RecallSink(Protocol):
    def add_units(self, units: list[Unit]) -> None: ...


class Recall:
    def __init__(
        self, store: Store, embedder: Embedder, config: Config
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._config = config
        # Recall owns its own connection to the same file the Store wrote
        # (ADR-0001). Cross-thread like the Store (TUI worker thread).
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(store.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)
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
        # Semantic index (ADR-0002): rowid mirrors search_units.id, 384-dim
        # to match bge-small-en-v1.5.
        self._conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS vec_search_units "
            "USING vec0(embedding float[384])"
        )
        self._conn.commit()

    def add_units(self, units: list[Unit]) -> None:
        if not units:
            return
        # One batched local embed call (ADR-0002) — offline by construction;
        # the keyword + vector rows share the unit's rowid in one transaction.
        vectors = self._embedder.embed([u.text for u in units])
        with self._lock:
            for unit, vec in zip(units, vectors):
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
                self._conn.execute(
                    "INSERT INTO vec_search_units (rowid, embedding) "
                    "VALUES (?, ?)",
                    (cur.lastrowid, sqlite_vec.serialize_float32(vec)),
                )
            self._conn.commit()

    def search(self, query: str, k: int | None = None) -> list[Hit]:
        """Hybrid recall: fuse the keyword and semantic rankings with RRF,
        fold to one Hit per Conversation, then apply the result budget. Both
        arms are seal-gated, so only Sealed (past-session) Conversations are
        searchable (ADR-0005). `k` falls back to the configured default."""
        if k is None:
            k = self._config.recall_k
        query_vec = self._embedder.embed([query])[0]
        match = _fts5_match_query(query)
        with self._lock:
            n = self._conn.execute(
                "SELECT count(*) FROM search_units"
            ).fetchone()[0]
            keyword_rows: list[sqlite3.Row] = []
            if match is not None:
                keyword_rows = self._conn.execute(
                    """
                    SELECT su.id, su.conversation_id, c.started_at,
                           c.summary_prose, su.text
                    FROM fts_search_units
                    JOIN search_units su ON su.id = fts_search_units.rowid
                    JOIN conversations c ON c.id = su.conversation_id
                    WHERE fts_search_units MATCH ? AND c.sealed_at IS NOT NULL
                    ORDER BY bm25(fts_search_units)
                    """,
                    (match,),
                ).fetchall()
            # KNN must be a bare vec0 query, so rank all units by distance in a
            # CTE, then seal-gate via the join outside it.
            semantic_rows = self._conn.execute(
                """
                WITH knn AS (
                    SELECT rowid AS id, distance
                    FROM vec_search_units
                    WHERE embedding MATCH ? ORDER BY distance LIMIT ?
                )
                SELECT su.id, su.conversation_id, c.started_at,
                       c.summary_prose, su.text
                FROM knn
                JOIN search_units su ON su.id = knn.id
                JOIN conversations c ON c.id = su.conversation_id
                WHERE c.sealed_at IS NOT NULL
                ORDER BY knn.distance
                """,
                (sqlite_vec.serialize_float32(query_vec), max(n, 1)),
            ).fetchall()
        return self._fuse(keyword_rows, semantic_rows, k)

    def _fuse(
        self,
        keyword_rows: list[sqlite3.Row],
        semantic_rows: list[sqlite3.Row],
        k: int,
    ) -> list[Hit]:
        # Reciprocal Rank Fusion: a unit at 1-based rank r in a list scores
        # 1/(rrf_k + r) for that list; its fused score is the sum across the
        # lists it appears in. No normalisation, no per-arm weighting — a unit
        # ranked in *both* lists beats one ranked top in only one.
        rrf_k = self._config.rrf_k
        scores: dict[int, float] = {}
        meta: dict[int, sqlite3.Row] = {}
        for rows in (keyword_rows, semantic_rows):
            for rank, r in enumerate(rows, 1):
                uid = r["id"]
                scores[uid] = scores.get(uid, 0.0) + 1.0 / (rrf_k + rank)
                meta.setdefault(uid, r)
        # Fold to one Hit per Conversation: its best (max-RRF) unit is the
        # snippet and sets the Conversation's rank.
        best: dict[int, tuple[float, sqlite3.Row]] = {}
        for uid, score in scores.items():
            r = meta[uid]
            cid = r["conversation_id"]
            if cid not in best or score > best[cid][0]:
                best[cid] = (score, r)
        # Deterministic order: score desc, then conversation_id asc.
        ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[0]))
        ceiling = self._config.recall_token_ceiling
        hits: list[Hit] = []
        used = 0
        for cid, (_score, r) in ranked:
            hit = Hit(
                conversation_id=cid,
                date=r["started_at"][:10],
                summary_line=r["summary_prose"],
                snippet=r["text"],
            )
            cost = _est_tokens(hit.summary_line) + _est_tokens(hit.snippet)
            # Fewer complete hits over more truncated ones (PRD): stop before
            # exceeding the ceiling, but always return the top hit.
            if hits and used + cost > ceiling:
                break
            hits.append(hit)
            used += cost
            if len(hits) >= k:
                break
        return hits

    def get_conversation(self, conversation_id: int) -> list[Turn]:
        """Drill-in: the full ordered transcript (both roles) of a past
        Conversation, so bounded recall is not lossy. Only ever called with
        an id from a seal-gated `search` Hit, so no extra gate here."""
        return self._store.turns_of(conversation_id)
