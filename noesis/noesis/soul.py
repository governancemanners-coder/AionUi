"""
Soul graph — the harness's persistent knowledge graph.

A lightweight, JSON-persisted graph of entities, the beliefs held about them,
and typed relationships between them. This is the "knowledge holder": durable,
structured memory that survives across sessions, distinct from the fuzzy
vector recall in :mod:`noesis.memory`.

Pure stdlib; the whole graph is a single JSON document.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Entity:
    id: str
    name: str
    kind: str = "concept"
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class Belief:
    id: str
    entity_id: str
    statement: str
    confidence: float = 0.7
    source: Optional[str] = None
    created_at: float = field(default_factory=time.time)


@dataclass
class Relation:
    id: str
    source_id: str
    target_id: str
    kind: str
    weight: float = 1.0
    created_at: float = field(default_factory=time.time)


class SoulGraph:
    def __init__(self, storage_path: str = "~/.noesis/soul_graph.json"):
        self.storage_path = os.path.expanduser(storage_path)
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        self.entities: Dict[str, Entity] = {}
        self.beliefs: Dict[str, Belief] = {}
        self.relations: Dict[str, Relation] = {}
        self._name_index: Dict[str, str] = {}  # lowercased name -> entity id
        self._load()

    # ── entities ─────────────────────────────────────────────────
    def add_entity(self, name: str, kind: str = "concept", **attributes: Any) -> Entity:
        existing = self._name_index.get(name.lower())
        if existing:
            ent = self.entities[existing]
            ent.attributes.update(attributes)
            self._save()
            return ent
        ent = Entity(id=str(uuid.uuid4()), name=name, kind=kind, attributes=attributes)
        self.entities[ent.id] = ent
        self._name_index[name.lower()] = ent.id
        self._save()
        return ent

    def find_entity(self, name: str) -> Optional[Entity]:
        eid = self._name_index.get(name.lower())
        return self.entities.get(eid) if eid else None

    # ── beliefs ──────────────────────────────────────────────────
    def add_belief(
        self,
        entity: str,
        statement: str,
        confidence: float = 0.7,
        source: Optional[str] = None,
    ) -> Belief:
        ent = self.find_entity(entity) or self.add_entity(entity)
        belief = Belief(
            id=str(uuid.uuid4()),
            entity_id=ent.id,
            statement=statement,
            confidence=confidence,
            source=source,
        )
        self.beliefs[belief.id] = belief
        self._save()
        return belief

    def beliefs_about(self, entity: str) -> List[Belief]:
        ent = self.find_entity(entity)
        if not ent:
            return []
        return [b for b in self.beliefs.values() if b.entity_id == ent.id]

    # ── relations ────────────────────────────────────────────────
    def relate(self, source: str, kind: str, target: str, weight: float = 1.0) -> Relation:
        s = self.find_entity(source) or self.add_entity(source)
        t = self.find_entity(target) or self.add_entity(target)
        rel = Relation(id=str(uuid.uuid4()), source_id=s.id, target_id=t.id, kind=kind, weight=weight)
        self.relations[rel.id] = rel
        self._save()
        return rel

    def neighbors(self, entity: str) -> List[Dict[str, Any]]:
        ent = self.find_entity(entity)
        if not ent:
            return []
        out = []
        for rel in self.relations.values():
            if rel.source_id == ent.id:
                other = self.entities.get(rel.target_id)
                if other:
                    out.append({"relation": rel.kind, "entity": other.name, "direction": "out"})
            elif rel.target_id == ent.id:
                other = self.entities.get(rel.source_id)
                if other:
                    out.append({"relation": rel.kind, "entity": other.name, "direction": "in"})
        return out

    # ── stats / persistence ──────────────────────────────────────
    def get_stats(self) -> Dict[str, int]:
        return {
            "total_entities": len(self.entities),
            "total_beliefs": len(self.beliefs),
            "total_relations": len(self.relations),
        }

    def _save(self) -> None:
        data = {
            "entities": {k: v.__dict__ for k, v in self.entities.items()},
            "beliefs": {k: v.__dict__ for k, v in self.beliefs.items()},
            "relations": {k: v.__dict__ for k, v in self.relations.items()},
        }
        tmp = self.storage_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, self.storage_path)

    def _load(self) -> None:
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        self.entities = {k: Entity(**v) for k, v in data.get("entities", {}).items()}
        self.beliefs = {k: Belief(**v) for k, v in data.get("beliefs", {}).items()}
        self.relations = {k: Relation(**v) for k, v in data.get("relations", {}).items()}
        self._name_index = {e.name.lower(): e.id for e in self.entities.values()}
