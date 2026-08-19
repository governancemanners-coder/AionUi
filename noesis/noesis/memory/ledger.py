"""
Immutable audit ledger.

Append-only, SHA-256-verified record of everything the harness does — every
memory write, tool call, and reasoning turn. Inspired by zero-hallucination
ledger designs: the only write operation is :meth:`append`, and every entry
can be re-verified against its stored checksum. Backed by stdlib ``sqlite3``
(no aiosqlite dependency) so it runs anywhere.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class LedgerEntry:
    id: str
    action: str
    actor: str
    target_type: str
    target_id: Optional[str] = None
    before_state: Optional[str] = None
    after_state: Optional[str] = None
    checksum: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def compute_checksum(self) -> str:
        return hashlib.sha256((self.after_state or "").encode()).hexdigest()

    def verify(self) -> bool:
        return self.checksum == self.compute_checksum()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Ledger:
    def __init__(self, db_path: str = "~/.noesis/ledger.db"):
        self.db_path = str(Path(db_path).expanduser())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS ledger (
                    id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT,
                    before_state TEXT,
                    after_state TEXT,
                    checksum TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    timestamp REAL NOT NULL
                )
                """
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_led_ts ON ledger(timestamp DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_led_act ON ledger(action)")
            db.commit()

    def append(
        self,
        action: str,
        actor: str,
        target_type: str,
        target_id: Optional[str] = None,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LedgerEntry:
        after_json = json.dumps(after_state, default=str) if after_state else "{}"
        entry = LedgerEntry(
            id=str(uuid.uuid4()),
            action=action,
            actor=actor,
            target_type=target_type,
            target_id=target_id,
            before_state=json.dumps(before_state, default=str) if before_state else None,
            after_state=after_json,
            checksum=hashlib.sha256(after_json.encode()).hexdigest(),
            metadata=metadata or {},
        )
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                INSERT INTO ledger (id, action, actor, target_type, target_id,
                    before_state, after_state, checksum, metadata, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.action,
                    entry.actor,
                    entry.target_type,
                    entry.target_id,
                    entry.before_state,
                    entry.after_state,
                    entry.checksum,
                    json.dumps(entry.metadata),
                    entry.timestamp,
                ),
            )
            db.commit()
        return entry

    def verify(self, entry_id: str) -> bool:
        with sqlite3.connect(self.db_path) as db:
            row = db.execute(
                "SELECT after_state, checksum FROM ledger WHERE id=?", (entry_id,)
            ).fetchone()
        if not row:
            return False
        after_state, stored = row
        return hashlib.sha256((after_state or "").encode()).hexdigest() == stored

    def verify_all(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {"total": 0, "valid": 0, "invalid": 0, "failures": []}
        with sqlite3.connect(self.db_path) as db:
            for row in db.execute(
                "SELECT id, action, after_state, checksum FROM ledger ORDER BY timestamp"
            ):
                results["total"] += 1
                eid, action, after_state, stored = row
                computed = hashlib.sha256((after_state or "").encode()).hexdigest()
                if computed == stored:
                    results["valid"] += 1
                else:
                    results["invalid"] += 1
                    results["failures"].append(
                        {"id": eid, "action": action, "expected": stored, "computed": computed}
                    )
        return results

    def recent(self, limit: int = 50) -> List[LedgerEntry]:
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM ledger ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def get_stats(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as db:
            total = db.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
            actions = {
                r[0]: r[1] for r in db.execute("SELECT action, COUNT(*) FROM ledger GROUP BY action")
            }
            actors = {
                r[0]: r[1] for r in db.execute("SELECT actor, COUNT(*) FROM ledger GROUP BY actor")
            }
        return {"total_entries": total, "action_breakdown": actions, "actor_breakdown": actors}

    def _row_to_entry(self, row: sqlite3.Row) -> LedgerEntry:
        return LedgerEntry(
            id=row["id"],
            action=row["action"],
            actor=row["actor"],
            target_type=row["target_type"],
            target_id=row["target_id"],
            before_state=row["before_state"],
            after_state=row["after_state"],
            checksum=row["checksum"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            timestamp=row["timestamp"],
        )
