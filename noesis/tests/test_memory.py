from noesis.memory import (
    EmbeddingProvider,
    Episode,
    EpisodicStore,
    Ledger,
    MemoryManager,
    VectorStore,
)


def test_ledger_append_and_verify(tmp_path):
    ledger = Ledger(db_path=str(tmp_path / "ledger.db"))
    entry = ledger.append("memory_store", "agent", "memory", after_state={"text": "hi"})
    assert ledger.verify(entry.id) is True
    summary = ledger.verify_all()
    assert summary["total"] == 1 and summary["invalid"] == 0
    assert ledger.get_stats()["total_entries"] == 1
    assert ledger.recent()[0].action == "memory_store"


def test_ledger_detects_tamper(tmp_path):
    import sqlite3

    ledger = Ledger(db_path=str(tmp_path / "ledger.db"))
    e = ledger.append("x", "agent", "memory", after_state={"v": 1})
    with sqlite3.connect(ledger.db_path) as db:
        db.execute("UPDATE ledger SET after_state=? WHERE id=?", ('{"v": 999}', e.id))
        db.commit()
    assert ledger.verify(e.id) is False
    assert ledger.verify_all()["invalid"] == 1


def test_vector_store_roundtrip(tmp_path):
    vs = VectorStore(collection_name="t", persist_dir=str(tmp_path))
    vs.add("a", "the cat sat", [1.0, 0.0, 0.0])
    vs.add("b", "the dog ran", [0.0, 1.0, 0.0])
    hits = vs.query([0.9, 0.1, 0.0], top_k=1)
    assert hits[0]["id"] == "a"
    assert vs.count() == 2
    # persistence
    vs2 = VectorStore(collection_name="t", persist_dir=str(tmp_path))
    assert vs2.count() == 2


def test_vector_store_metadata_filter(tmp_path):
    vs = VectorStore(collection_name="t", persist_dir=str(tmp_path))
    vs.add("a", "x", [1.0, 0.0], metadata={"kind": "note"})
    vs.add("b", "y", [1.0, 0.0], metadata={"kind": "fact"})
    hits = vs.query([1.0, 0.0], top_k=5, filter_dict={"kind": "fact"})
    assert [h["id"] for h in hits] == ["b"]


def test_embeddings_fallback_is_deterministic():
    emb = EmbeddingProvider()
    emb._fallback = True  # force offline path
    v1 = emb.embed_query("hello world")
    v2 = emb.embed_query("hello world")
    assert v1 == v2
    assert len(v1) == emb.dimension


def test_episodic_store_and_search(tmp_path):
    store = EpisodicStore(db_path=str(tmp_path / "ep.db"))
    store.add(Episode(query="I like Rust", response="noted"))
    store.add(Episode(query="weather?", response="sunny"))
    assert store.count() == 2
    hits = store.search("Rust")
    assert any("Rust" in e.query for e in hits)
    thread = store.conversation_thread()
    assert thread[0]["role"] == "user"


def test_memory_manager_end_to_end(tmp_path):
    mm = MemoryManager(root=str(tmp_path))
    mm.remember("Sean likes the quasar theme", metadata={"kind": "pref"})
    mm.remember("The bridge runs on port 8420")
    hits = mm.recall("quasar theme", top_k=1)
    assert hits and "quasar" in hits[0]["text"].lower()
    stats = mm.stats()
    assert stats["long_term"] == 2
    assert stats["ledger"] >= 2
