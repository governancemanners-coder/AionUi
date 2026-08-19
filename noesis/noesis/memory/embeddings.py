"""
Text embeddings with a pure-Python fallback.

On capable machines ``sentence-transformers`` produces real semantic vectors.
On Termux (or anywhere without the compiled stack) we fall back to a
deterministic character-trigram hashing embedding — not semantically rich, but
stable, dependency-free, and good enough for cosine-similarity recall.
"""
from __future__ import annotations

import math
from typing import List


class EmbeddingProvider:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", dim: int = 384):
        self.model_name = model_name
        self._model = None
        self._fallback = False
        self._embedding_dim = dim

    def _load_model(self) -> None:
        if self._model is not None or self._fallback:
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            self._embedding_dim = self._model.get_sentence_embedding_dimension()
        except Exception:
            # ImportError, or a runtime/model-download failure — degrade cleanly.
            self._fallback = True

    def embed(self, texts: List[str]) -> List[List[float]]:
        self._load_model()
        if self._fallback:
            return [self._fallback_embed(t) for t in texts]
        vecs = self._model.encode(list(texts), convert_to_numpy=True)
        return [list(map(float, v)) for v in vecs]

    def embed_query(self, text: str) -> List[float]:
        return self.embed([text])[0]

    def _fallback_embed(self, text: str) -> List[float]:
        dim = self._embedding_dim
        vec = [0.0] * dim
        low = text.lower()
        for i in range(max(0, len(low) - 2)):
            trigram = low[i : i + 3]
            vec[hash(trigram) % dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    @property
    def dimension(self) -> int:
        self._load_model()
        return self._embedding_dim
