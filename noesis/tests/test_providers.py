import pytest

from noesis.providers import (
    AuthMode,
    ChatResult,
    ClaudeProvider,
    GeminiProvider,
    KimiProvider,
    Message,
    Provider,
    ProviderConfig,
    ProviderError,
    ProviderRouter,
)
from noesis.providers.cli import messages_to_prompt, which
from noesis.providers.openai_compat import OpenAICompatProvider


class StubProvider(Provider):
    name = "stub"
    _api_capable = True
    _cli_capable = True

    def default_model(self):
        return "stub-1"

    def _has_cli(self):  # pretend the CLI exists when configured
        return bool(self.config.cli_path)

    def _chat_api(self, messages, model, **opts):
        return ChatResult(text="api:" + messages[-1].content, provider=self.name, model=model, auth_mode=AuthMode.API_KEY)

    def _chat_cli(self, messages, model, **opts):
        return ChatResult(text="cli:" + messages[-1].content, provider=self.name, model=model, auth_mode=AuthMode.SUBSCRIPTION)


def test_auth_selection_prefers_subscription():
    p = StubProvider(ProviderConfig(api_key="k", cli_path="stub", prefer=AuthMode.SUBSCRIPTION))
    assert set(p.usable_auth()) == {AuthMode.API_KEY, AuthMode.SUBSCRIPTION}
    assert p.chat([{"role": "user", "content": "hi"}]).auth_mode is AuthMode.SUBSCRIPTION


def test_auth_selection_byok_only():
    p = StubProvider(ProviderConfig(api_key="k"))  # no cli
    assert p.usable_auth() == [AuthMode.API_KEY]
    r = p.chat([{"role": "user", "content": "yo"}])
    assert r.text == "api:yo"


def test_unconfigured_provider_raises():
    p = StubProvider(ProviderConfig())
    assert p.available() is False
    with pytest.raises(ProviderError):
        p.chat([{"role": "user", "content": "x"}])


def test_router_auto_and_explicit():
    stub = StubProvider(ProviderConfig(api_key="k"))
    router = ProviderRouter({"stub": stub}, priority=["stub"])
    assert router.available_providers() == ["stub"]
    assert router.chat([{"role": "user", "content": "a"}]).text == "api:a"
    assert router.select(provider="stub") is stub
    with pytest.raises(ProviderError):
        router.select(provider="missing")


def test_router_provider_slash_model_split():
    stub = StubProvider(ProviderConfig(api_key="k"))
    router = ProviderRouter({"stub": stub})
    prov, model = router._split_model("stub/some-model")
    assert prov == "stub" and model == "some-model"
    r = router.chat([{"role": "user", "content": "q"}], model="stub/some-model")
    assert r.model == "some-model"


def test_router_fallback_chain():
    down = StubProvider(ProviderConfig())  # unusable
    up = StubProvider(ProviderConfig(api_key="k"))
    up.name = "up"
    router = ProviderRouter({"down": down, "up": up}, priority=["down", "up"])
    r = router.chat_with_fallback([{"role": "user", "content": "z"}])
    assert r.text == "api:z"


def test_claude_payload_hoists_system():
    p = ClaudeProvider(ProviderConfig(api_key="k"))
    msgs = [Message("system", "be terse"), Message("user", "hello")]
    payload = p._payload(msgs, "claude-3-5-sonnet-latest", False, {})
    assert payload["system"] == "be terse"
    assert payload["messages"] == [{"role": "user", "content": "hello"}]
    assert payload["model"].startswith("claude")


def test_claude_code_prefers_subscription():
    p = ClaudeProvider(ProviderConfig(api_key="k"))
    from noesis.providers import ClaudeCodeProvider

    cc = ClaudeCodeProvider(ProviderConfig(api_key="k"))
    assert cc.config.prefer is AuthMode.SUBSCRIPTION
    assert p.config.prefer is AuthMode.SUBSCRIPTION or p.config.prefer is AuthMode.API_KEY


def test_claude_cli_model_alias():
    from noesis.providers.claude import _cli_model

    assert _cli_model("claude-3-5-sonnet-latest") == "sonnet"
    assert _cli_model("claude-3-5-haiku-20241022") == "haiku"
    assert _cli_model("some-opus-build") == "opus"
    assert _cli_model("gpt-4o") == "gpt-4o"  # unknown passes through


def test_gemini_contents_shaping():
    p = GeminiProvider(ProviderConfig(api_key="k"))
    system, contents = p._to_contents([Message("system", "s"), Message("user", "u"), Message("assistant", "a")])
    assert system == "s"
    assert contents[0]["role"] == "user"
    assert contents[1]["role"] == "model"  # assistant -> model
    assert contents[0]["parts"][0]["text"] == "u"


def test_openai_compat_payload():
    p = OpenAICompatProvider(ProviderConfig(api_key="k"))
    payload = p._payload([Message("user", "hi")], "gpt", False, {"temperature": 0.5})
    assert payload["messages"][0]["content"] == "hi"
    assert payload["temperature"] == 0.5


def test_kimi_defaults_and_dual_capability():
    p = KimiProvider(ProviderConfig(api_key="k"))
    assert p.default_model()
    assert set(p.supported_auth()) == {AuthMode.API_KEY, AuthMode.SUBSCRIPTION}


def test_cli_prompt_flatten():
    prompt = messages_to_prompt([Message("system", "S"), Message("user", "hello"), Message("assistant", "hi")])
    assert prompt.startswith("S")
    assert "User: hello" in prompt
    assert prompt.rstrip().endswith("Assistant:")


def test_which_absolute_and_missing(tmp_path):
    assert which(None) is None
    assert which(str(tmp_path / "nope")) is None
    real = tmp_path / "bin"
    real.write_text("x")
    assert which(str(real)) == str(real)
