import os

from noesis.config import load_config
from noesis.providers import AuthMode, ChatResult, Provider, ProviderConfig, ProviderRouter
from noesis.reasoning import ReasoningEngine, Strategy


class FakeProvider(Provider):
    name = "fake"
    _api_capable = True

    def default_model(self):
        return "fake-1"

    def _chat_api(self, messages, model, **opts):
        # Echo a deterministic "ANSWER:" so strategies can parse it.
        return ChatResult(
            text="Thinking...\nANSWER: 42",
            provider=self.name,
            model=model,
            auth_mode=AuthMode.API_KEY,
        )


def _engine_with_model():
    router = ProviderRouter({"fake": FakeProvider(ProviderConfig(api_key="k"))}, priority=["fake"])
    return ReasoningEngine(router=router)


def test_engine_has_model_toggle():
    assert ReasoningEngine(router=None).has_model() is False
    assert _engine_with_model().has_model() is True


def test_cot_with_model_extracts_answer():
    eng = _engine_with_model()
    trace = eng.reason("what is the answer?")
    assert trace.strategy is Strategy.COT
    assert trace.answer == "42"
    assert trace.provider == "fake"


def test_prefix_selects_strategy():
    eng = _engine_with_model()
    trace = eng.reason("reflexion: check this")
    assert trace.strategy is Strategy.REFLEXION
    assert trace.answer == "42"


def test_offline_heuristic_without_model():
    eng = ReasoningEngine(router=None)
    trace = eng.reason("hello", context={"recall": [{"text": "prior fact", "score": 1.0}]})
    assert "prior fact" in trace.answer
    assert trace.confidence < 0.5


def test_config_env_autodetect(monkeypatch, tmp_path):
    monkeypatch.setenv("NOESIS_HOME", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = load_config(root=str(tmp_path))
    assert cfg.providers["openrouter"].api_key == "sk-or-test"
    assert cfg.providers["openrouter"].prefer is AuthMode.API_KEY
    assert cfg.providers["gemini"].api_key == "g-test"
    assert "openrouter" in cfg.priority


def test_config_file_overlay(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        '{"default_strategy": "react", "providers": {"custom": '
        '{"base_url": "http://localhost:11434/v1", "model": "llama3"}}}'
    )
    cfg = load_config(path=str(cfg_file), root=str(tmp_path))
    assert cfg.default_strategy == "react"
    assert cfg.providers["custom"].base_url.endswith("/v1")
    assert cfg.providers["custom"].default_model == "llama3"
