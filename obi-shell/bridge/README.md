# OBI Bridge — the device half

`obi_bridge.py` is the Termux host server that turns the web shell into a full
device-controlling agent OS. **Stdlib only, no pip installs.**

## What it gives the app

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/` (any static path) | GET | Serves the app itself (same-origin — no CORS/mixed-content issues) |
| `/health` | GET | Connection probe (the app polls this to flip the "connected" pills) |
| `/dispatch` | POST | Runs your **real six-skill `OBIDispatcher`** (`/scan`, `/se`, `/mcp` …) |
| `/chat` | POST | OpenAI-style chat, forwarded to local **Ollama** — keys never leave the device |
| `/exec` | POST | **Device control** — shell command execution (gated, off by default) |
| `/fs/list` `/fs/read` `/fs/write` | GET/POST | Filesystem access |
| `/screen` | GET | Screen capture via `termux-screenshot` (termux-api) |

## Quick start

```bash
# in Termux
pkg install python termux-api
bash install.sh                        # sets up ~/obi/ skill dirs

# put your OBI files in place
cp obi_skill_*.py            ~/obi/skills/adversarial/
cp obi_command_dispatcher.py ~/obi/commands/

# run it
export OBI_ALLOW_EXEC=1                 # optional: enable device control
python obi_bridge.py                    # → http://localhost:8420
```

Open **http://localhost:8420** in your phone browser → **Add to Home screen**.
In the app: **Settings → OBI's brain → Obliteratus Bridge**. The device-bridge
pills turn green and `/scan` etc. now run your real Python skills.

## Configuration (environment variables)

| Var | Default | Meaning |
| --- | --- | --- |
| `OBI_PORT` | `8420` | Port to serve on |
| `OBI_HOST` | `127.0.0.1` | Bind address — keep on localhost |
| `OBI_ALLOW_EXEC` | *(off)* | Set `1` to enable `/exec` device control |
| `OBI_TOKEN` | *(none)* | Require `X-OBI-Token` header on control endpoints |
| `OBI_OLLAMA` | `http://localhost:11434` | Local model host for `/chat` |
| `OBI_SKILLS_DIR` | `~/obi/skills/adversarial` | Where the six skills live |
| `OBI_COMMANDS_DIR` | `~/obi/commands` | Where the dispatcher lives |

## Security

- Binds to **127.0.0.1** — not reachable from off-device.
- `/exec` runs arbitrary shell commands and is **disabled unless `OBI_ALLOW_EXEC=1`**.
- Set `OBI_TOKEN` to require a shared secret on control endpoints.
- Single-user personal tool. **Never expose it on a public interface.**
- The app's ReAct/tool-result scanning (`scan_tool_result`) should gate anything
  the model does with `/exec` output before it re-enters context — that is the
  MCP-poisoning defense from skill 6, and it is the whole point of running OBI
  self-protecting.
