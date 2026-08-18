#!/data/data/com.termux/files/usr/bin/bash
# ════════════════════════════════════════════════════════════════
#  OBLITERATUS BRIDGE — one-shot Termux installer
#  Sets up the device half of the OBI agent-OS and auto-wires the
#  six adversarial skills you already have in Downloads.
# ════════════════════════════════════════════════════════════════
set -u
BRIDGE_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$BRIDGE_DIR/.." && pwd)"

echo "═══════════════════════════════════════════════════════"
echo "  OBLITERATUS BRIDGE — Termux setup"
echo "  app:    $APP_DIR"
echo "═══════════════════════════════════════════════════════"

# 1 ── packages ──────────────────────────────────────────────────
echo "→ installing python + termux-api (screen capture) …"
pkg install -y python termux-api >/dev/null 2>&1 || pkg install -y python termux-api

# 2 ── skill layout ──────────────────────────────────────────────
SK="$HOME/obi/skills/adversarial"
CM="$HOME/obi/commands"
mkdir -p "$SK" "$CM"

# 3 ── auto-find the skills you already downloaded ───────────────
echo "→ hunting for your obi_skill_*.py and dispatcher …"
SEARCH_ROOTS=(
  "/storage/emulated/0/Download"
  "/storage/emulated/0/Documents"
  "$HOME"
)
found=0
for root in "${SEARCH_ROOTS[@]}"; do
  [ -d "$root" ] || continue
  while IFS= read -r f; do
    cp -f "$f" "$SK/" && found=$((found+1))
  done < <(find "$root" -type f -name 'obi_skill_*.py' 2>/dev/null)
  while IFS= read -r f; do
    cp -f "$f" "$CM/"
  done < <(find "$root" -type f -name 'obi_command_dispatcher.py' 2>/dev/null)
done
echo "  copied $found skill file(s) into $SK"
ls "$SK"/*.py >/dev/null 2>&1 && echo "  skills: $(ls "$SK" | tr '\n' ' ')"
ls "$CM"/obi_command_dispatcher.py >/dev/null 2>&1 \
  && echo "  dispatcher: present ✓" \
  || echo "  dispatcher: NOT found — copy obi_command_dispatcher.py into $CM (app still works with built-in scanners)"

# 4 ── launch ────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════"
echo "  Ready. Launch OBI:"
echo ""
echo "    export OBI_ALLOW_EXEC=1     # optional: device control"
echo "    python \"$BRIDGE_DIR/obi_bridge.py\""
echo ""
echo "  Then open  http://localhost:8420  in your browser"
echo "  and Add to Home screen for the full agent-OS."
echo "═══════════════════════════════════════════════════════"

# 5 ── offer to start now ────────────────────────────────────────
printf "Start OBI now? [y/N] "
read -r ans
if [ "${ans:-N}" = "y" ] || [ "${ans:-N}" = "Y" ]; then
  echo "→ launching on http://localhost:8420  (Ctrl-C to stop)"
  exec python "$BRIDGE_DIR/obi_bridge.py"
fi
