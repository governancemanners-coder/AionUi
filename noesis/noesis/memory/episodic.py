"""
Episodic memory — the harness's conversation history.

Full interaction episodes (query + response + metadata) stored in stdlib
``sqlite3`` with an FTS5 full-text index when the SQLite build supports it,
degrading to ``LIKE`` search otherwise. Synchronous and dependency-free.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Episode:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    query: str = ""
    response: str = ""
    tools_used: List[str] = field(default_factory=list)
    trace_id: Optional[str] = None
    strategy: Optional[str] = None
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class EpisodicStore:
    def __init__(self, db_path: str = "~/.noesis/episodes.db"):
        self.db_path = str(Path(db_path).expanduser())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._fts = False
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    response TEXT NOT NULL,
                    tools_used TEXT DEFAULT '[]',
                    trace_id TEXT,
                    strategy TEXT,
                    confidence REAL DEFAULT 0.0,
                    metadata TEXT DEFAULT '{}',
                    created_at REAL NOT NULL
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ep_created ON episodes(created_at DESC)"
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_ep_trace ON episodes(trace_id)")
            # FTS5 is optional depending on the SQLite build.
            try:
                db.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                        query, response, content='episodes', content_rowid='rowid'
                    )
                    """
                )
                db.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS ep_ai AFTER INSERT ON episodes BEGIN
                        INSERT INTO episodes_fts(rowid, query, response)
                        VALUES (new.rowid, new.query, new.response);
                    END
                    """
                )
                self._fts = True
            except sqlite3.OperationalError:
                self._fts = False
            db.commit()

    def add(self, episode: Episode) -> Episode:
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                INSERT OR REPLACE INTO episodes
                (id, query, response, tools_used, trace_id, strategy, confidence, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode.id,
                    episode.query,
                    episode.response,
                    json.dumps(episode.tools_used),
                    episode.trace_id,
                    episode.strategy,
                    episode.confidence,
                    json.dumps(episode.metadata),
                    episode.created_at,
                ),
            )
            db.commit()
        return episode

    def recent(self, limit: int = 10) -> List[Episode]:
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM episodes ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_episode(r) for r in rows]

    def search(self, query: str, limit: int = 10) -> List[Episode]:
        episodes: List[Episode] = []
        if self._fts:
            try:
                with sqlite3.connect(self.db_path) as db:
                    db.row_factory = sqlite3.Row
                    rows = db.execute(
                        """
                        SELECT e.* FROM episodes e
                        JOIN episodes_fts fts ON e.rowid = fts.rowid
                        WHERE episodes_fts MATCH ?
                        ORDER BY rank LIMIT ?
                        """,
                        (query, limit),
                    ).fetchall()
                    episodes = [self._row_to_episode(r) for r in rows]
            except sqlite3.OperationalError:
                episodes = []
        if not episodes:  # LIKE fallback
            with sqlite3.connect(self.db_path) as db:
                db.row_factory = sqlite3.Row
                pattern = f"%{query}%"
                rows = db.execute(
                    """
                    SELECT * FROM episodes
                    WHERE query LIKE ? OR response LIKE ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (pattern, pattern, limit),
                ).fetchall()
                episodes = [self._row_to_episode(r) for r in rows]
        return episodes

    def conversation_thread(self, limit: int = 20) -> List[Dict[str, str]]:
        episodes = self.recent(limit)
        episodes.reverse()
        thread: List[Dict[str, str]] = []
        for ep in episodes:
            thread.append({"role": "user", "content": ep.query})
            thread.append({"role": "assistant", "content": ep.response})
        return thread

    def count(self) -> int:
        with sqlite3.connect(self.db_path) as db:
            return db.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]

    def clear(self) -> None:
        with sqlite3.connect(self.db_path) as db:
            db.execute("DELETE FROM episodes")
            if self._fts:
                try:
                    db.execute("DELETE FROM episodes_fts")
                except sqlite3.OperationalError:
                    pass
            db.commit()

    def _row_to_episode(self, row: sqlite3.Row) -> Episode:
        return Episode(
            id=row["id"],
            query=row["query"],
            response=row["response"],
            tools_used=json.loads(row["tools_used"]) if row["tools_used"] else [],
            trace_id=row["trace_id"],
            strategy=row["strategy"],
            confidence=row["confidence"] or 0.0,
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
        )
