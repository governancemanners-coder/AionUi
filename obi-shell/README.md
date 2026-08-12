# OBLITERATUS // Quasar Agent-OS — OBI Shell

A phone-first **agent-OS shell** for **OBI (Obliteratus)** — Sean's reverse-engineering &
personal-security harness. The visual identity is a **quasar**: an onyx-black event horizon,
a rotating gold accretion disk, gravitational-lensing violet, cream/tan text, glassmorphism.

`index.html` is a **fully self-contained, offline prototype** — open it directly in any
browser (or add it to your home screen on Android/iOS for a Gemini-style app feel).

---

## What is real right now (no backend required)

| Feature | Status | How |
| --- | --- | --- |
| Quasar / event-horizon UI | ✅ live | Canvas accretion disk + lensing, reduced-motion aware |
| Chat interface | ✅ live | Local OBI persona + themed replies |
| **`/scan /sescan /mcpscan`** | ✅ live | Real pattern scanners **ported from OBI's own dashboards** |
| `/se /net /ext /poi /mcp` knowledge | ✅ live | Compact technique corpus from the six skills |
| **Text-to-speech** (play each reply) | ✅ live | Web Speech `speechSynthesis` — per-message ▶ + auto-read toggle |
| **Speech-to-text** (mic dictation) | ✅ live | Web Speech `SpeechRecognition` where supported |
| Workspace (upload / drag-drop / scan files) | ✅ live | `FileReader`, text files auto-scannable for injection |
| History of past sessions | ✅ live | `localStorage`, reload any session |
| Notifications | ✅ live | Fires on quarantine / ingest / high-severity scans |
| Agent Screen (thought-stream) | ✅ live | Toggleable `THINK → TOOL → OBS → ACT` telemetry |
| Settings (voice, motion, auto-screen, wipe) | ✅ live | Persisted locally |
| Self-protection: scans your input before acting | ✅ live | SOUL directive — flags injection in your own messages |

Everything runs **100% locally in the browser**. No data leaves the device.

## What is stubbed (honestly marked "not connected")

- **Model backend** — OBI's LLM replies are local placeholders. Wire to your OpenRouter /
  Ollama / API endpoint next.
- **proot / device control bridge** — needs the Termux host agent.
- **Screen share to OBI** — the "watch his computer" live feed (Manus/Kimi style) needs a
  host-side capture bridge.

---

## Integration roadmap (deep wiring)

**Phase 1 — Model backend.** Replace `obiReply()` / `respond()` with a streaming call to
your provider. The Agent Screen already models `THINK/TOOL/OBS/ACT` — stream real tokens and
tool-call events into `asLine()`.

**Phase 2 — Dispatch to the real skills.** The Python `OBIDispatcher` already routes
`/commands` to the six skills. Stand up a tiny local HTTP shim (Flask/FastAPI in Termux) that
exposes `dispatch(cmd)`; the shell's `handleCommand()` then calls it instead of the ported JS
(which stays as the offline fallback).

**Phase 3 — Device bridge.** A Termux companion process exposes proot/file/exec over a
localhost socket; the Settings "device bridge" pills flip to connected and gate a permissioned
command surface. **Every tool result must pass `scan_tool_result()` before it re-enters
context** — the ReAct-loop protection from `obi_skill_mcp_poisoning`.

**Phase 4 — Screen stream.** Host-side capture (scrcpy / MediaProjection / a headless browser
frame) piped to a `<video>`/canvas in the Agent Screen panel, toggled by the existing Screen
button.

**Phase 5 — Fold into AionUi.** Port the shell into `packages/desktop/src/renderer` as Arco
components following the repo's `architecture` skill (10-children/dir, semantic tokens, no raw
HTML), reusing AionUi's existing multi-provider model plumbing and IPC bridge for the device
layer.

---

*Prototype v0.1 · built on branch `claude/obi-wrapper-agent-os-2nwxpa`. All processing local.*
