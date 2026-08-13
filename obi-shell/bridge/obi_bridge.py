#!/usr/bin/env python3
"""
OBI BRIDGE — Obliteratus host server for the Quasar Agent-OS
============================================================
The device half of the OBI wrapper. Runs on your phone (Termux) and gives
the web shell teeth:

  • Serves the app itself      → open http://localhost:8420 (same-origin, no CORS pain)
  • Real skill dispatch        POST /dispatch  {"command":"/scan ..."}  → six-skill output
  • Local model proxy          POST /chat       (OpenAI-style) → forwards to Ollama
  • Device control (gated)     POST /exec       {"cmd":"..."}   requires OBI_ALLOW_EXEC=1
  • Filesystem                 /fs/list /fs/read /fs/write
  • Screen capture             GET  /screen      → PNG via termux-api

Stdlib only. No pip installs. Python 3.8+.

SECURITY
--------
  • Binds to 127.0.0.1 by default — not reachable off-device.
  • /exec is DISABLED unless you set OBI_ALLOW_EXEC=1 (arbitrary command execution).
  • Set OBI_TOKEN=<secret> to require an X-OBI-Token header on control endpoints.
  • This is a personal, single-user tool. Do not expose it to a public interface.

USAGE
-----
  export OBI_ALLOW_EXEC=1                 # optional: enable device control
  export OBI_TOKEN=changeme               # optional: require a token
  python obi_bridge.py                    # serves on http://localhost:8420
  python obi_bridge.py --port 9000 --dir /path/to/app
"""

import os, sys, json, argparse, subprocess, mimetypes, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ── config ───────────────────────────────────────────────────────
HERE          = os.path.dirname(os.path.abspath(__file__))
APP_DIR       = os.environ.get("OBI_APP_DIR", os.path.dirname(HERE))  # obi-shell/
SKILLS_DIR    = os.path.expanduser(os.environ.get("OBI_SKILLS_DIR", "~/obi/skills/adversarial"))
COMMANDS_DIR  = os.path.expanduser(os.environ.get("OBI_COMMANDS_DIR", "~/obi/commands"))
OLLAMA        = os.environ.get("OBI_OLLAMA", "http://localhost:11434")
TOKEN         = os.environ.get("OBI_TOKEN", "")
ALLOW_EXEC    = os.environ.get("OBI_ALLOW_EXEC", "") == "1"

for p in (SKILLS_DIR, COMMANDS_DIR):
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

# ── skill dispatcher (graceful if not installed) ─────────────────
_dispatcher = None
def get_dispatcher():
    global _dispatcher
    if _dispatcher is None:
        try:
            from obi_command_dispatcher import OBIDispatcher
            _dispatcher = OBIDispatcher(skills_path=SKILLS_DIR)
        except Exception as e:
            _dispatcher = e
    return _dispatcher


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ── helpers ──────────────────────────────────────────────────
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-OBI-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors(); self.end_headers()
        self.wfile.write(body)

    def _bytes(self, data, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self._cors(); self.end_headers()
        self.wfile.write(data)

    def _read(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b""
        try: return json.loads(raw or b"{}")
        except Exception: return {}

    def _authed(self):
        if not TOKEN: return True
        return self.headers.get("X-OBI-Token", "") == TOKEN

    def log_message(self, *a): pass  # quiet

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    # ── GET ──────────────────────────────────────────────────────
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            return self._json({
                "status": "ok", "name": "obi-bridge", "version": "0.1",
                "exec_enabled": ALLOW_EXEC, "token_required": bool(TOKEN),
                "skills": not isinstance(get_dispatcher(), Exception),
            })
        if path == "/screen":
            return self._screen()
        if path in ("/fs/list",):
            return self._fs_list()
        # static file serving (the app)
        return self._static(path)

    # ── POST ─────────────────────────────────────────────────────
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/dispatch":  return self._dispatch()
        if path == "/chat":      return self._chat()
        if path == "/exec":      return self._exec()
        if path == "/fs/read":   return self._fs_read()
        if path == "/fs/write":  return self._fs_write()
        return self._json({"error": "unknown endpoint"}, 404)

    # ── endpoints ────────────────────────────────────────────────
    def _static(self, path):
        if path in ("/", ""): path = "/index.html"
        fp = os.path.normpath(os.path.join(APP_DIR, path.lstrip("/")))
        if not fp.startswith(APP_DIR) or not os.path.isfile(fp):
            return self._json({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
        with open(fp, "rb") as f:
            self._bytes(f.read(), ctype)

    def _dispatch(self):
        if not self._authed(): return self._json({"error": "unauthorized"}, 401)
        cmd = (self._read().get("command") or "").strip()
        if not cmd: return self._json({"error": "no command"}, 400)
        d = get_dispatcher()
        if isinstance(d, Exception):
            return self._json({"output":
                f"[bridge] Skills not found on device.\n"
                f"Expected the six skills at {SKILLS_DIR} and the dispatcher at {COMMANDS_DIR}.\n"
                f"Import error: {d}\n"
                f"The app is falling back to its built-in offline scanners."})
        try:
            return self._json({"output": d.dispatch(cmd)})
        except Exception as e:
            return self._json({"output": f"[bridge] dispatch error: {e}"})

    def _chat(self):
        """OpenAI-style chat, forwarded to local Ollama so keys never leave the device."""
        if not self._authed(): return self._json({"error": "unauthorized"}, 401)
        payload = self._read()
        try:
            req = urllib.request.Request(
                OLLAMA + "/v1/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"})
            up = urllib.request.urlopen(req, timeout=120)
            # stream the SSE straight through
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self._cors(); self.end_headers()
            while True:
                chunk = up.read(1024)
                if not chunk: break
                try: self.wfile.write(chunk)
                except Exception: break
        except Exception as e:
            self._json({"error": f"ollama unreachable at {OLLAMA}: {e}"}, 502)

    def _exec(self):
        if not self._authed(): return self._json({"error": "unauthorized"}, 401)
        if not ALLOW_EXEC:
            return self._json({"output": "[bridge] device control disabled. "
                                         "Restart with OBI_ALLOW_EXEC=1 to enable /exec."}, 403)
        cmd = (self._read().get("cmd") or "").strip()
        if not cmd: return self._json({"error": "no cmd"}, 400)
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
            return self._json({"code": r.returncode, "output": out[:100000]})
        except subprocess.TimeoutExpired:
            return self._json({"output": "[bridge] command timed out (120s)"}, 408)
        except Exception as e:
            return self._json({"output": f"[bridge] exec error: {e}"}, 500)

    def _screen(self):
        """Capture the device screen via termux-api."""
        if not self._authed(): return self._json({"error": "unauthorized"}, 401)
        out = "/data/data/com.termux/files/usr/tmp/obi_screen.png"
        try:
            os.makedirs(os.path.dirname(out), exist_ok=True)
        except Exception:
            out = os.path.join(APP_DIR, "obi_screen.png")
        try:
            subprocess.run(["termux-screenshot", out], timeout=20, check=True)
            with open(out, "rb") as f:
                return self._bytes(f.read(), "image/png")
        except FileNotFoundError:
            return self._json({"error": "termux-api not installed — run: pkg install termux-api"}, 500)
        except Exception as e:
            return self._json({"error": f"screen capture failed: {e}"}, 500)

    def _fs_list(self):
        if not self._authed(): return self._json({"error": "unauthorized"}, 401)
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)
        d = os.path.expanduser(q.get("path", ["~"])[0])
        try:
            items = [{"name": n, "dir": os.path.isdir(os.path.join(d, n))}
                     for n in sorted(os.listdir(d))]
            return self._json({"path": d, "items": items})
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _fs_read(self):
        if not self._authed(): return self._json({"error": "unauthorized"}, 401)
        fp = os.path.expanduser(self._read().get("path", ""))
        try:
            with open(fp, "r", errors="replace") as f:
                return self._json({"path": fp, "content": f.read(200000)})
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _fs_write(self):
        if not self._authed(): return self._json({"error": "unauthorized"}, 401)
        b = self._read(); fp = os.path.expanduser(b.get("path", ""))
        try:
            with open(fp, "w") as f:
                f.write(b.get("content", ""))
            return self._json({"ok": True, "path": fp})
        except Exception as e:
            return self._json({"error": str(e)}, 500)


def main():
    global APP_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("OBI_PORT", 8420)))
    ap.add_argument("--host", default=os.environ.get("OBI_HOST", "127.0.0.1"))
    ap.add_argument("--dir", default=APP_DIR, help="directory to serve the app from")
    args = ap.parse_args()
    APP_DIR = os.path.abspath(args.dir)

    print("═" * 58)
    print("  OBLITERATUS BRIDGE  //  OBI host server v0.1")
    print("═" * 58)
    print(f"  app        http://{args.host}:{args.port}")
    print(f"  serving    {APP_DIR}")
    print(f"  skills     {SKILLS_DIR}  ({'found' if not isinstance(get_dispatcher(), Exception) else 'MISSING — offline scanners only'})")
    print(f"  ollama     {OLLAMA}")
    print(f"  device ctl {'ENABLED (/exec live)' if ALLOW_EXEC else 'disabled (set OBI_ALLOW_EXEC=1)'}")
    print(f"  token      {'required' if TOKEN else 'none'}")
    print("═" * 58)
    print("  Open the app URL above in your browser, then in the app set")
    print("  Settings → OBI's brain → Obliteratus Bridge.  Ctrl-C to stop.")
    print("═" * 58)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nHorizon collapsed. OBI bridge offline.")
