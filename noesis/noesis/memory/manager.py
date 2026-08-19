"""
Memory manager — the tiered "knowledge holder".

Ties the tiers together into one facade:

  * working    — a small ring buffer of the most recent items (fast, volatile)
  * short-term — a larger bounded buffer, consolidated into long-term on overflow
  * long-term  — the vector store (semantic recall via embeddings)
  * episodic   — the SQLite conversation history (exact/full-text recall)

Every store and consolidation is recorded in the immutable :class:`Ledger`, so
the memory tier is fully auditable.
"""
from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

from .embeddings import EmbeddingProvider
from .episodic import Episode, EpisodicStore
from .ledger import Ledger
from .vector_store import VectorStore


@dataclass
class MemoryItem:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class MemoryManager:
    def __init__(
        self,
        root: str = "~/.noesis",
        working_limit: int = 8,
        short_term_limit: int = 32,
        embeddings: Optional[EmbeddingProvider] = None,
        vector_store: Optional[VectorStore] = None,
        episodic: Optional[EpisodicStore] = None,
        ledger: Optional[Ledger] = None,
    ):
        import os

        base = os.path.expanduser(root)
        self.working_limit = working_limit
        self.short_term_limit = short_term_limit
        self.working: Deque[MemoryItem] = deque(maxlen=working_limit)
        self.short_term: Deque[MemoryItem] = deque(maxlen=short_term_limit)
        self.embeddings = embeddings or EmbeddingProvider()
        self.long_term = vector_store or VectorStore(persist_dir=os.path.join(base, "vectors"))
        self.episodic = episodic or EpisodicStore(db_path=os.path.join(base, "episodes.db"))
        self.ledger = ledger or Ledger(db_path=os.path.join(base, "ledger.db"))

    # ── writes ───────────────────────────────────────────────────
    def remember(self, text: str, metadata: Optional[Dict[str, Any]] = None, actor: str = "agent") -> MemoryItem:
        """Store a fact across working + short-term, promote to long-term."""
        item = MemoryItem(text=text, metadata=metadata or {})
        self.working.append(item)
        overflow = None
        if len(self.short_term) == self.short_term_limit:
            overflow = self.short_term[0]  # will be evicted by append
        self.short_term.append(item)
        self._promote_long_term(item)
        if overflow is not None:
            self._promote_long_term(overflow)
        self.ledger.append(
            action="memory_store",
            actor=actor,
            target_type="memory",
            target_id=item.id,
            after_state={"text": text, "metadata": item.metadata},
        )
        return item

    def _promote_long_term(self, item: MemoryItem) -> None:
        vec = self.embeddings.embed_query(item.text)
        self.long_term.add(item.id, item.text, vec, item.metadata)

    def record_episode(self, episode: Episode, actor: str = "agent") -> Episode:
        self.episodic.add(episode)
        self.ledger.append(
            action="episode_store",
            actor=actor,
            target_type="episode",
            target_id=episode.id,
            after_state={"query": episode.query, "response": episode.response},
        )
        return episode

    # ── reads ────────────────────────────────────────────────────
    def recall(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Semantic recall from long-term memory."""
        vec = self.embeddings.embed_query(query)
        return self.long_term.query(vec, top_k=top_k)

    def recall_episodes(self, query: str, limit: int = 5) -> List[Episode]:
        return self.episodic.search(query, limit=limit)

    def context(self, query: str, top_k: int = 5, history: int = 6) -> Dict[str, Any]:
        """Assemble a recall bundle for prompting: working set + semantic hits + history."""
        return {
            "working": [i.text for i in self.working],
            "recall": self.recall(query, top_k=top_k),
            "history": self.episodic.conversation_thread(history),
        }

    def clear_working(self) -> None:
        self.working.clear()

    def stats(self) -> Dict[str, Any]:
        return {
            "working": len(self.working),
            "short_term": len(self.short_term),
            "long_term": self.long_term.count(),
            "episodes": self.episodic.count(),
            "ledger": self.ledger.get_stats()["total_entries"],
        }
