"""SQLite persistence for the chat spine.

Encapsulates the single inspectable SQLite file (ADR-0001). Callers see
Conversations and Turns, never SQL. Timestamps are ISO-8601 TEXT so the file
stays human-inspectable. Recall's search tables (search_units / vec / fts) are
deliberately out of scope here — they arrive with later issues.
"""

import datetime as dt
import sqlite3
import threading
from dataclasses import dataclass


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


@dataclass(frozen=True)
class Conversation:
    id: int
    started_at: str
    sealed_at: str | None


@dataclass(frozen=True)
class Turn:
    seq: int
    role: str
    content: str
    created_at: str


class Store:
    def __init__(self, db_path):
        # The TUI runs the agent loop on a Textual worker thread, so the
        # connection is shared across threads; access is serialised by _lock.
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                sealed_at TEXT,
                summary_prose TEXT,
                summary_outcomes TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id),
                seq INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                compacted INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.commit()

    def start_conversation(self) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO conversations (started_at) VALUES (?)", (_now_iso(),)
            )
            self._conn.commit()
            return cur.lastrowid

    def get_conversation(self, conversation_id: int) -> Conversation | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, started_at, sealed_at FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        return Conversation(
            id=row["id"],
            started_at=row["started_at"],
            sealed_at=row["sealed_at"],
        )

    def add_turn(self, conversation_id: int, seq: int, role: str, content: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO turns (conversation_id, seq, role, content, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (conversation_id, seq, role, content, _now_iso()),
            )
            self._conn.commit()

    def turns_of(self, conversation_id: int) -> list[Turn]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, role, content, created_at FROM turns "
                "WHERE conversation_id = ? ORDER BY seq",
                (conversation_id,),
            ).fetchall()
        return [
            Turn(
                seq=r["seq"],
                role=r["role"],
                content=r["content"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
