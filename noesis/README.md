# noesis — knowledge holder & memory agent harness

> Working name (Greek: *knowledge / understanding*). Rename freely — it lives in
> exactly one place: the `noesis/` package folder and the `name` in `pyproject.toml`.

A standalone, **stdlib-only** Python harness that gives an agent a durable
memory and a single door to every model backend. Built to run anywhere from a
workstation down to an Android phone under Termux, with graceful degradation the
whole way down (no key? offline heuristic. no numpy? pure-Python vectors. no
FTS5? `LIKE` search).

Heritage: the tiered-memory + immutable-ledger design is borrowed from the
Mnemosyne harness; the reasoning strategies are Hermes-inspired.

## What it is

```
                         ┌─────────────── Harness ───────────────┐
   your app  ─────────▶  │  ask() · chat() · remember() · recall() │
                         └───┬───────┬───────────┬──────────┬──────┘
                             │       │           │          │
                   ReasoningEngine  MemoryManager  SoulGraph  ProviderRouter
                   (cot/react/       (working →      (entities, (subscription
                    reflexion/tot)    short-term →    beliefs,   + BYOK, per
                             │        long-term →     relations) provider auto)
                             │        episodic)          │          │
                             └──────────── Ledger (SHA-256, append-only) ──────┘
```

- **Multi-tier memory** — working ring buffer → short-term buffer → long-term
  vector store (semantic recall) → episodic SQLite history (exact / full-text).
- **Soul graph** — durable, structured knowledge: entities, beliefs, relations,
  persisted as one JSON document.
- **Immutable ledger** — every memory write and episode is appended with a
  SHA-256 checksum and can be re-verified; tampering is detectable.
- **Reasoning engine** — Chain-of-Thought, ReAct, Reflexion, Tree-of-Thought.
  Choose per call or with a `cot:` / `react:` / `reflexion:` / `tot:` prefix.
- **Unified provider layer** — one interface, many backends, two auth modes.

## Providers & auth

Every provider is an adapter that supports **both** ways in, and prefers your
subscription (what you already pay for) over per-token API billing:

| Provider     | API key (BYOK)                    | Subscription (CLI / OAuth)      |
| ------------ | --------------------------------- | ------------------------------- |
| `openrouter` | ✅ OpenRouter key                 | —                               |
| `claude`     | ✅ Anthropic Messages API         | ✅ `claude` CLI (Claude Code)   |
| `claude-code`| ✅ (same as claude)               | ✅ subscription-first alias     |
| `kimi`       | ✅ Moonshot OpenAI-compat key     | ✅ `kimi` CLI                   |
| `gemini`     | ✅ Google Generative Language key | ✅ `gemini` CLI                 |
| `custom`     | ✅ any OpenAI-compatible endpoint (incl. Ollama) | —                |

The router picks the best available provider automatically (subscription-first
priority), or you address one explicitly (`provider="kimi"`) or via a
`provider/model` string (`"openrouter/anthropic/claude-3.5-sonnet"`), with an
optional fallback chain.

## Quick start

```bash
cd noesis
python -m noesis --status        # what's configured / available
python -m noesis                 # interactive REPL
```

Configure by exporting keys and/or having a vendor CLI installed — no config
file required:

```bash
export OPENROUTER_API_KEY=sk-or-...     # BYOK
export GEMINI_API_KEY=...               # BYOK
# ...or just have `claude` / `gemini` / `kimi` on PATH to use a subscription
export NOESIS_NO_CLI=1                   # optional: BYOK-only, ignore installed CLIs
```

Programmatic use:

```python
from noesis import Harness

h = Harness.from_env()
h.remember("My favorite language is Rust")
print(h.ask("What language do I like?").answer)     # recalls memory, reasons, answers

# direct model access, any provider
print(h.chat([{"role": "user", "content": "hi"}], provider="gemini").text)
```

## Configuration file (optional)

`~/.noesis/config.json` (or `.yaml` with the `yaml` extra). Env vars overlay it.

```json
{
  "default_strategy": "react",
  "priority": ["claude-code", "kimi", "gemini", "openrouter", "custom"],
  "providers": {
    "kimi":       { "prefer": "subscription", "default_model": "kimi-k2-0711-preview" },
    "openrouter": { "api_key": "sk-or-...", "default_model": "anthropic/claude-3.5-sonnet" },
    "custom":     { "base_url": "http://localhost:11434/v1", "model": "llama3" }
  }
}
```

## Termux / Android

Runtime dependencies: **none** (stdlib only). It runs as-is:

```bash
pkg install python
python -m noesis
```

Optional extras (`pip install .[vectors,cli,yaml]`) enable
`sentence-transformers` + `chromadb` embeddings, a `rich` REPL, and YAML config —
each with a pure-Python fallback when absent.

## Tests

```bash
cd noesis && PYTHONPATH=. pytest -q      # 31 offline tests, no network
```

## Layout

```
noesis/
  providers/   base · router · http · cli · openrouter · claude · kimi · gemini · openai_compat
  memory/      embeddings · vector_store · episodic · ledger · manager
  reasoning/   engine · strategies
  soul.py      knowledge graph
  config.py    file + env provider auto-detection
  harness.py   the object your app constructs
  __main__.py  REPL / one-shot CLI
```

## Status

First increment: the full memory + soul + ledger + reasoning + provider stack is
implemented and tested; the Claude Code subscription path is verified live.
Not yet wired: tool/skill dispatch inside ReAct, streaming in the REPL, and the
optional ChromaDB long-term backend (interface is ready). See the harness's
`obi-shell/bridge` for a matching device-side HTTP surface to mount this on.
