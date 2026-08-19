from noesis import Harness, load_config


def test_harness_offline_end_to_end(monkeypatch, tmp_path):
    # No provider keys -> offline heuristic, but memory/soul/ledger all live.
    for var in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "MOONSHOT_API_KEY", "KIMI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NOESIS_NO_CLI", "1")  # force offline (ignore any installed provider CLI)
    monkeypatch.setenv("NOESIS_HOME", str(tmp_path))
    cfg = load_config(root=str(tmp_path))
    h = Harness(cfg)

    h.remember("The event horizon theme is onyx and gold")
    trace = h.ask("tell me about the event horizon theme")
    assert trace.answer  # heuristic surfaces the memory or restates the query

    status = h.status()
    assert status["memory"]["episodes"] >= 1
    assert status["memory"]["long_term"] >= 1
    assert status["has_model"] is False


def test_harness_records_episode(monkeypatch, tmp_path):
    for var in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "MOONSHOT_API_KEY", "KIMI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NOESIS_NO_CLI", "1")
    monkeypatch.setenv("NOESIS_HOME", str(tmp_path))
    h = Harness(load_config(root=str(tmp_path)))
    before = h.memory.episodic.count()
    h.ask("first question")
    h.ask("second question")
    assert h.memory.episodic.count() == before + 2
    # ledger recorded the episodes immutably
    assert h.memory.ledger.verify_all()["invalid"] == 0
