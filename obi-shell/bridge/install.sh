#!/data/data/com.termux/files/usr/bin/bash
# ── OBLITERATUS BRIDGE installer (Termux / Android) ──────────────
# One command to stand up OBI's device half.
set -e

echo "═══════════════════════════════════════════════════════"
echo "  OBLITERATUS BRIDGE — Termux setup"
echo "═══════════════════════════════════════════════════════"

# 1. Packages (python + termux-api for screen capture)
echo "→ installing python + termux-api …"
pkg install -y python termux-api >/dev/null 2>&1 || pkg install -y python termux-api

# 2. Skill layout (matches the OBI package README)
mkdir -p "$HOME/obi/skills/adversarial" "$HOME/obi/commands"
echo "→ skill directories ready at ~/obi/"
echo "  Drop the six obi_skill_*.py files into ~/obi/skills/adversarial/"
echo "  Drop obi_command_dispatcher.py into ~/obi/commands/"

# 3. Optional: pull an Ollama model host note
echo "→ (optional) install Ollama for a fully on-device brain:"
echo "    pkg install ollama && ollama serve &  ;  ollama pull llama3.1"

# 4. Launch
BRIDGE_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "═══════════════════════════════════════════════════════"
echo "  Launch OBI:"
echo "    export OBI_ALLOW_EXEC=1     # enable device control (optional)"
echo "    python \"$BRIDGE_DIR/obi_bridge.py\""
echo "  Then open  http://localhost:8420  in your browser."
echo "  Add it to your home screen for the full agent-OS feel."
echo "═══════════════════════════════════════════════════════"
