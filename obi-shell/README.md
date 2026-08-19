# OBLITERATUS // Quasar Agent-OS — OBI

A phone-first **agent-OS** for **OBI (Obliteratus)** — Sean's reverse-engineering &
personal-security harness. Onyx-black event horizon, rotating gold accretion disk,
gravitational-lensing violet, cream/tan text, glassmorphism.

This is a **complete two-piece system**:

```
obi-shell/
├── index.html            ← the app (PWA — installs to your home screen)
├── manifest.webmanifest  ← PWA manifest
├── sw.js                 ← offline service worker
├── icon.svg              ← quasar app icon
└── bridge/
    ├── obi_bridge.py      ← the device half: serves the app + device control + real skills
    ├── install.sh         ← one-command Termux setup
    └── README.md          ← bridge docs
```

---

## Run it (full power, on your phone)

```bash
# in Termux on Android
pkg install python termux-api git
git clone <this repo> && cd AionUi/obi-shell/bridge
bash install.sh

# drop your OBI skill files where the bridge expects them
cp /path/to/obi_skill_*.py            ~/obi/skills/adversarial/
cp /path/to/obi_command_dispatcher.py ~/obi/commands/

# launch
export OBI_ALLOW_EXEC=1                 # enable device control (optional)
python obi_bridge.py                    # → http://localhost:8420
```

Open **http://localhost:8420**, **Add to Home screen**, then in the app pick
**Settings → OBI's brain → Obliteratus Bridge**. Now everything is live:
real model (via local Ollama), real `/scan` etc. through your Python skills,
device control, and screen capture.

## Or use it right now (no phone setup)

Open the app in any browser and go to **Settings → OBI's brain**:
- **OpenRouter** or **Anthropic** — paste a key, OBI thinks immediately (works in-browser).
- Or leave it unconnected — the offline scanners and voice still work.

---

## What's live

| | Works offline (no backend) | Needs a provider | Needs the bridge |
| --- | :---: | :---: | :---: |
| Quasar / event-horizon UI, glassmorphism | ✅ | | |
| Chat with OBI persona | ✅ | | |
| **Live streaming AI** (OBI's SOUL as system prompt) | | ✅ OpenRouter/Anthropic/Ollama/OpenAI-compat | ✅ local Ollama |
| Text-to-speech (play each reply) + STT dictation | ✅ | | |
| `/scan /sescan /mcpscan` (ported scanners) | ✅ | | ✅ real Python skills |
| `/se /net /ext /poi /mcp` knowledge + `/skills` `/help` | ✅ | | ✅ full dispatcher |
| Workspace: ingest, drag-drop, one-tap file injection scan | ✅ | | |
| Session history + notifications | ✅ | | |
| Agent Screen thought-stream (THINK/TOOL/OBS/ACT) | ✅ | ✅ real stream status | |
| **Team orchestration** (`/team` — OBI spawns visible subagents) | ✅ local team | ✅ each subagent is a real model call | ✅ via local model |
| Self-protection: input injection-scanned before OBI acts | ✅ | | |
| **proot / device control** (`/exec`) | | | ✅ |
| **Screen capture** from device | | | ✅ |
| Install to home screen (PWA), offline shell | ✅ | | |

The app degrades gracefully: no provider → offline scanners; no bridge → the app
falls back to its built-in JS scanners for slash commands.

## Team orchestration — visible subagents

OBI doesn't just answer; he **delegates**. Type `/team <task>` (or `/delegate`) and OBI
becomes the orchestrator:

1. **Decompose** — he breaks the task into 2–4 subtasks (a live model plans it; offline, a
   keyword heuristic does).
2. **Delegate** — each subtask is assigned to a named subordinate with its own specialized
   system prompt: **Recon**, **Reverser**, **Red Team**, **Analyst**, **Defender**, **Scribe**.
3. **Watch** — open the **Team** tab. Each subordinate gets its own card: profile, assigned
   subtask, a live status badge (queued → running → done), and its streaming output. The
   Agent Screen mirrors it with `DELEGATE` / `SUBAGENT` / `OBS` lines.
4. **Synthesize** — OBI fuses every report into one brief (Findings · Risk · Next actions),
   posts it to chat, and saves it to your workspace.

Each subagent is a real, provider-agnostic model call (it reuses the same connection you set
in Settings), so this works on OpenRouter, Anthropic, Ollama, or the Termux bridge's local
model. With no model connected, the team still runs on local scanners + heuristics so you can
see the whole delegation fire end-to-end. No Docker, no containers — visible subagents are
orchestration + UI, and it's all here.

## Security posture (built in, per OBI's SOUL)

- Your input is injection-scanned **before** OBI acts on it; flagged content is
  surfaced, not executed.
- API keys are stored only in this device's `localStorage`.
- The bridge binds to `127.0.0.1`, keeps `/exec` **off** unless `OBI_ALLOW_EXEC=1`,
  and supports an `OBI_TOKEN` shared secret.
- Tool/`/exec` output should pass `scan_tool_result()` before re-entering context —
  the ReAct-loop defense from skill 6.

## Next step: folding into AionUi proper

The prototype is deliberately standalone so it runs anywhere today. To make it a
first-class AionUi surface, port `index.html` into `packages/desktop/src/renderer`
as Arco components (follow the repo's `architecture` skill — 10-children/dir,
semantic tokens, no raw HTML), reusing AionUi's multi-provider model plumbing and
IPC bridge for the device layer in place of the standalone Termux bridge.

*v0.1 · branch `claude/obi-wrapper-agent-os-2nwxpa` · all processing local.*
