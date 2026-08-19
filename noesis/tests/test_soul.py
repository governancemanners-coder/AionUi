from noesis.soul import SoulGraph


def test_entities_beliefs_relations(tmp_path):
    soul = SoulGraph(storage_path=str(tmp_path / "soul.json"))
    soul.add_entity("Termux", "platform")
    soul.add_belief("Termux", "runs Python without root", confidence=0.9)
    soul.relate("noesis", "runs_on", "Termux")

    stats = soul.get_stats()
    assert stats["total_entities"] == 2  # Termux + noesis (auto-created)
    assert stats["total_beliefs"] == 1
    assert stats["total_relations"] == 1

    beliefs = soul.beliefs_about("Termux")
    assert beliefs[0].statement.startswith("runs Python")

    neigh = soul.neighbors("noesis")
    assert neigh and neigh[0]["entity"] == "Termux"


def test_soul_persistence_and_dedup(tmp_path):
    path = str(tmp_path / "soul.json")
    soul = SoulGraph(storage_path=path)
    soul.add_entity("Kaelus", "project", role="hub")
    soul.add_entity("kaelus", "project")  # same name (case-insensitive) -> dedup

    reloaded = SoulGraph(storage_path=path)
    assert reloaded.get_stats()["total_entities"] == 1
    assert reloaded.find_entity("KAELUS").attributes.get("role") == "hub"
