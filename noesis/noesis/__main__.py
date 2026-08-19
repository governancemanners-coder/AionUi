"""
noesis CLI — a minimal, dependency-free REPL over the Harness.

    python -m noesis                 # interactive REPL
    python -m noesis --status        # print provider/memory status and exit
    python -m noesis --ask "..."     # one-shot question
"""
from __future__ import annotations

import argparse
import json
import sys

from .harness import Harness
from .version import __version__

BANNER = f"""\
noesis {__version__} — knowledge holder & memory agent harness
type /help for commands, /quit to exit
"""

HELP = """\
commands:
  /ask <query>            reason over a query (prefix cot:/react:/reflexion:/tot:)
  /remember <text>        store a fact in memory
  /recall <query>         semantic recall from long-term memory
  /soul                   show the soul graph stats
  /learn <entity> :: <belief>   add a belief about an entity
  /providers              list configured providers and their auth
  /status                 memory + provider status
  /help                   this text
  /quit                   exit
anything else is treated as an /ask query.
"""


def _print_status(h: Harness) -> None:
    print(json.dumps(h.status(), indent=2, default=str))


def _repl(h: Harness) -> None:
    print(BANNER)
    if not h.engine.has_model():
        print("(!) no model configured — reasoning uses the offline heuristic.")
        print("    export OPENROUTER_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY,")
        print("    or install the claude / gemini / kimi CLI to use a subscription.\n")
    while True:
        try:
            line = input("noesis> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye.")
            return
        if not line:
            continue
        if line in ("/quit", "/exit"):
            print("bye.")
            return
        if line == "/help":
            print(HELP)
        elif line == "/status":
            _print_status(h)
        elif line == "/providers":
            for d in h.router.describe():
                mark = "✓" if d["available"] else "·"
                print(f"  {mark} {d['name']:<12} auth={d['usable_auth'] or d['supported_auth']} model={d['default_model']}")
        elif line == "/soul":
            print(json.dumps(h.soul.get_stats(), indent=2))
        elif line.startswith("/remember "):
            item = h.remember(line[len("/remember "):].strip())
            print(f"stored {item.id}")
        elif line.startswith("/recall "):
            for r in h.recall(line[len("/recall "):].strip()):
                print(f"  [{r['score']:.2f}] {r['text']}")
        elif line.startswith("/learn "):
            body = line[len("/learn "):]
            if "::" in body:
                ent, belief = body.split("::", 1)
                h.soul.add_belief(ent.strip(), belief.strip())
                print(f"learned about {ent.strip()!r}")
            else:
                print("usage: /learn <entity> :: <belief>")
        else:
            query = line[len("/ask "):].strip() if line.startswith("/ask ") else line
            trace = h.ask(query)
            src = f" via {trace.provider}" if trace.provider else " (offline)"
            print(f"[{trace.strategy.value}{src}] {trace.answer}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="noesis", description="knowledge holder & memory agent harness")
    ap.add_argument("--config", help="path to a config file")
    ap.add_argument("--status", action="store_true", help="print status and exit")
    ap.add_argument("--ask", help="one-shot query and exit")
    ap.add_argument("--version", action="version", version=f"noesis {__version__}")
    args = ap.parse_args()

    h = Harness.from_env(args.config)
    if args.status:
        _print_status(h)
        return
    if args.ask:
        trace = h.ask(args.ask)
        print(trace.answer)
        return
    _repl(h)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
