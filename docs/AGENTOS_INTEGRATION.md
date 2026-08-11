# Running AionUI inside AgentOS

AionUI is embedded as-is inside the [AgentOS](https://github.com/governancemanners-coder/AgentOS)
umbrella shell, surfaced from its sidebar under **Apps → AionUI**. AgentOS
hosts AionUI in an `<iframe>`; no changes to AionUI are required.

## How it is wired

AgentOS embeds the **AionUI WebUI** (not the Electron app). Start it with:

```bash
bun run webui
```

By default the WebUI dev server listens on **http://localhost:25809**. AgentOS
points at that origin via its `NEXT_PUBLIC_AIONUI_URL` environment variable
(default `http://localhost:25809`).

To run the whole stitched suite (AgentOS + AionUI + Agent Office) with one
command, use AgentOS's `pnpm dev:suite` — see
[`docs/integration.md`](https://github.com/governancemanners-coder/AgentOS/blob/main/docs/integration.md)
in the AgentOS repo.

## Standalone use

Nothing about the embedding changes how AionUI runs on its own. The desktop
app (`bun start`) and the WebUI (`bun run webui`) both work exactly as before.
