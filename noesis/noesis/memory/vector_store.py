"""
Pure-Python vector store with cosine similarity.

Persists to a JSON file; no compiled dependencies. This is the long-term
semantic memory tier. (A ChromaDB-backed store can be dropped in later behind
the same interface for large corpora.)
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional


class VectorStore:
    def __init__(
        self,
        collection_name: str = "noesis",
        persist_dir: str = "~/.noesis/vectors",
    ):
        self.persist_dir = os.path.expanduser(persist_dir)
        os.makedirs(self.persist_dir, exist_ok=True)
        self.collection_name = collection_name
        self.persist_path = os.path.join(self.persist_dir, f"{collection_name}.json")
        # id -> {"text", "embedding", "metadata"}
        self._docs: Dict[str, Dict[str, Any]] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────
    def _load(self) -> None:
        if os.path.exists(self.persist_path):
            try:
                with open(self.persist_path, "r", encoding="utf-8") as f:
                    self._docs = json.load(f)
            except Exception:
                self._docs = {}

    def _save(self) -> None:
        tmp = self.persist_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._docs, f)
            os.replace(tmp, self.persist_path)
        except Exception:
            pass

    # ── math ─────────────────────────────────────────────────────
    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    # ── CRUD ─────────────────────────────────────────────────────
    def add(
        self,
        id: str,
        text: str,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._docs[id] = {
            "text": text,
            "embedding": list(embedding),
            "metadata": metadata or {},
        }
        self._save()

    def add_batch(self, items: List[Dict[str, Any]]) -> None:
        for item in items:
            self._docs[item["id"]] = {
                "text": item["text"],
                "embedding": list(item["embedding"]),
                "metadata": item.get("metadata", {}),
            }
        self._save()

    def query(
        self,
        embedding: List[float],
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        results = []
        for doc_id, doc in self._docs.items():
            if filter_dict and not _matches(doc.get("metadata", {}), filter_dict):
                continue
            sim = self._cosine(embedding, doc["embedding"])
            results.append(
                {
                    "id": doc_id,
                    "text": doc["text"],
                    "score": sim,
                    "distance": 1.0 - sim,
                    "metadata": doc["metadata"],
                }
            )
        results.sort(key=lambda x: x["distance"])
        return results[:top_k]

    def get(self, id: str) -> Optional[Dict[str, Any]]:
        doc = self._docs.get(id)
        if not doc:
            return None
        return {"id": id, "text": doc["text"], "metadata": doc["metadata"]}

    def delete(self, id: str) -> None:
        if id in self._docs:
            del self._docs[id]
            self._save()

    def count(self) -> int:
        return len(self._docs)

    def clear(self) -> None:
        self._docs.clear()
        self._save()


def _matches(metadata: Dict[str, Any], filter_dict: Dict[str, Any]) -> bool:
    return all(metadata.get(k) == v for k, v in filter_dict.items())
