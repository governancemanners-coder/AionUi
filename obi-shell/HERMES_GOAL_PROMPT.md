# OBI (Obliteratus) — Complete Production Build & Deploy

You are being given a single, comprehensive goal. Execute every phase below sequentially. Do not skip steps. Do not ask for confirmation — resolve blockers autonomously. When a step fails, diagnose, repair, and retry before moving on. Your output at the end should be a fully operational OBI agent-OS running on this device.

---

## CONTEXT — What OBI Is

OBI (Obliteratus) is a phone-first agent-OS for reverse-engineering and adversarial-intelligence work. It is a PWA (Progressive Web App) served from a local Python bridge running in Termux. The system has two halves:

1. **Frontend** (`obi-shell/index.html`) — a single-file PWA with quasar/event-horizon UI, chat, workspace, visible multi-agent team orchestration, agent screen telemetry, slash commands, offline scanners, TTS/STT, and multi-provider LLM streaming.
2. **Backend** (`obi-shell/bridge/obi_bridge.py`) — a stdlib Python HTTP server (no pip dependencies) that serves the app, proxies to a local LLM (Ollama), dispatches the six adversarial skill modules, provides filesystem access, screen capture, and gated device control.

The codebase lives at: `~/AionUi/obi-shell/`

The app already has:
- Full quasar UI with glassmorphism, onyx-black palette, gold accretion disk, gravitational-lensing violet
- Multi-provider streaming (OpenRouter, Anthropic direct, Ollama, OpenAI-compatible, Termux bridge)
- 6-agent visible team orchestration (`/team <task>`) with named subordinates: Recon, Reverser, Red Team, Analyst, Defender, Scribe
- Prompt injection scanning on all inputs (7 pattern categories)
- Workspace with drag-drop file ingestion
- Agent Screen (THINK/TOOL/OBS/ACT thought-stream)
- Session history, notifications
- TTS (speak responses) and STT (mic dictation)
- PWA manifest + service worker for home-screen install and offline operation
- Bridge endpoints: `/health`, `/dispatch`, `/chat`, `/exec`, `/fs/*`, `/screen`

What OBI is MISSING and you must build:

1. **Persistent Memory Agent** — OBI must remember across sessions
2. **Subscription/Credits-based LLM support** — not just raw API keys; users should be able to use OpenRouter credits, prepaid balances, etc.
3. **Auto-delegation** — OBI should decide on his own when to delegate to the team, not only on explicit `/team` commands
4. **Self-enhancement loop** — OBI should be able to improve his own prompts, skills, and knowledge base over time
5. **Production hardening** — error recovery, connection resilience, proper offline/online transitions
6. **Full Termux integration** — everything installed, wired, and verified working

---

## PHASE 1 — Environment Setup & Dependency Installation

### 1.1 Termux packages

```bash
pkg update -y
pkg upgrade -y
pkg install -y python python-pip git termux-api jq curl wget openssh
```

If any package fails, retry with `apt` directly:
```bash
apt install -y python python-pip git termux-api jq curl wget openssh
```

### 1.2 Termux storage permission

```bash
termux-setup-storage
```

Wait for the Android permission dialog. If already granted, this is a no-op.

### 1.3 Python packages for the memory agent and enhanced bridge

```bash
pip install --upgrade pip
pip install chromadb sentence-transformers flask-cors watchdog pyyaml
```

If `chromadb` fails due to build dependencies:
```bash
pkg install -y build-essential rust cmake
pip install chromadb
```

If `sentence-transformers` is too heavy for your device, fall back to a simpler embedding:
```bash
pip install tiktoken numpy
```

### 1.4 Ollama (local LLM)

If not already installed:
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

If the install script doesn't work on Termux (common), install manually:
```bash
# Check if ollama binary exists
which ollama || {
  echo "Ollama not found — install it from https://ollama.com or use OpenRouter instead."
  echo "OBI works without a local model — just set OpenRouter/Anthropic in Settings."
}
```

If Ollama is available, pull a capable model:
```bash
ollama pull llama3.1:8b
# or for lower-memory devices:
ollama pull phi3:mini
```

### 1.5 Clone or update the repo

```bash
cd ~
if [ -d "AionUi" ]; then
  cd AionUi
  git fetch origin
  git checkout claude/obi-agent-zero-mvp-bsdfrp
  git pull origin claude/obi-agent-zero-mvp-bsdfrp
else
  git clone https://github.com/governancemanners-coder/aionui.git AionUi
  cd AionUi
  git checkout claude/obi-agent-zero-mvp-bsdfrp
fi
```

### 1.6 Directory structure

```bash
mkdir -p ~/obi/skills/adversarial
mkdir -p ~/obi/commands
mkdir -p ~/obi/memory/chroma
mkdir -p ~/obi/memory/sessions
mkdir -p ~/obi/memory/knowledge
mkdir -p ~/obi/logs
mkdir -p ~/obi/config
mkdir -p ~/obi/self-enhance
```

---

## PHASE 2 — Memory Agent

OBI needs persistent memory that survives app restarts, session clears, and device reboots. Build a memory agent as a Python module that the bridge loads.

### 2.1 Create `~/obi/memory/obi_memory.py`

Write the following file exactly:

```python
#!/usr/bin/env python3
"""
OBI Memory Agent — persistent recall across sessions.
Stores conversation summaries, learned facts, user preferences,
and task outcomes in a local vector store + JSON knowledge base.

Three memory tiers:
  1. Working memory  — current session context (in-app JS, not here)
  2. Episodic memory  — summaries of past sessions (JSON + vector)
  3. Core memory      — facts, preferences, skills OBI has learned (JSON)
"""

import os, json, time, hashlib, re
from datetime import datetime, timezone
from pathlib import Path

MEMORY_DIR  = Path(os.path.expanduser("~/obi/memory"))
SESSIONS_DIR = MEMORY_DIR / "sessions"
KNOWLEDGE_FILE = MEMORY_DIR / "knowledge" / "core.json"
PREFERENCES_FILE = MEMORY_DIR / "knowledge" / "preferences.json"
SKILLS_LEARNED_FILE = MEMORY_DIR / "knowledge" / "skills_learned.json"
INDEX_FILE = MEMORY_DIR / "index.json"

for d in (SESSIONS_DIR, MEMORY_DIR / "knowledge"):
    d.mkdir(parents=True, exist_ok=True)

# ── Vector store (ChromaDB if available, else simple TF-IDF) ────
_chroma = None
_collection = None

def _init_vector_store():
    global _chroma, _collection
    if _collection is not None:
        return True
    try:
        import chromadb
        _chroma = chromadb.PersistentClient(path=str(MEMORY_DIR / "chroma"))
        _collection = _chroma.get_or_create_collection(
            name="obi_memory",
            metadata={"hnsw:space": "cosine"}
        )
        return True
    except ImportError:
        return False
    except Exception as e:
        print(f"[memory] ChromaDB init failed: {e}")
        return False

def _simple_search(query, entries, top_k=5):
    """Fallback keyword search when ChromaDB is unavailable."""
    query_words = set(re.findall(r'\w+', query.lower()))
    scored = []
    for e in entries:
        text = (e.get("summary", "") + " " + e.get("content", "")).lower()
        text_words = set(re.findall(r'\w+', text))
        overlap = len(query_words & text_words)
        if overlap > 0:
            scored.append((overlap, e))
    scored.sort(key=lambda x: -x[0])
    return [s[1] for s in scored[:top_k]]


# ── Core memory (facts, preferences) ───────────────────────────
def _load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}

def _save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def remember_fact(key, value, category="general"):
    """Store a fact in core memory. Overwrites if key exists."""
    facts = _load_json(KNOWLEDGE_FILE)
    if category not in facts:
        facts[category] = {}
    facts[category][key] = {
        "value": value,
        "stored": datetime.now(timezone.utc).isoformat(),
        "access_count": 0
    }
    _save_json(KNOWLEDGE_FILE, facts)
    # Also store in vector DB if available
    if _init_vector_store():
        doc_id = hashlib.md5(f"fact:{category}:{key}".encode()).hexdigest()
        _collection.upsert(
            ids=[doc_id],
            documents=[f"{category}: {key} = {value}"],
            metadatas=[{"type": "fact", "category": category, "key": key}]
        )
    return True

def recall_facts(category=None):
    """Retrieve all facts, optionally filtered by category."""
    facts = _load_json(KNOWLEDGE_FILE)
    if category:
        return facts.get(category, {})
    return facts

def remember_preference(key, value):
    """Store a user preference."""
    prefs = _load_json(PREFERENCES_FILE)
    prefs[key] = {"value": value, "updated": datetime.now(timezone.utc).isoformat()}
    _save_json(PREFERENCES_FILE, prefs)
    return True

def recall_preferences():
    return _load_json(PREFERENCES_FILE)


# ── Episodic memory (session summaries) ─────────────────────────
def save_session(session_id, messages, summary=None):
    """Archive a conversation session with auto-summary."""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if summary is None:
        # Auto-generate a summary from the last few messages
        texts = [m.get("text", "") for m in messages[-10:]]
        summary = " | ".join(t[:120] for t in texts if t)[:500]

    session_data = {
        "id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_count": len(messages),
        "summary": summary,
        "messages": messages[-50:]  # keep last 50 messages max
    }
    _save_json(session_file, session_data)

    # Index it
    index = _load_json(INDEX_FILE) if INDEX_FILE.exists() else {"sessions": []}
    index["sessions"] = [s for s in index.get("sessions", []) if s["id"] != session_id]
    index["sessions"].insert(0, {
        "id": session_id,
        "timestamp": session_data["timestamp"],
        "summary": summary[:200],
        "message_count": len(messages)
    })
    # Keep last 200 sessions in index
    index["sessions"] = index["sessions"][:200]
    _save_json(INDEX_FILE, index)

    # Vector-store the summary
    if _init_vector_store():
        doc_id = hashlib.md5(f"session:{session_id}".encode()).hexdigest()
        _collection.upsert(
            ids=[doc_id],
            documents=[summary],
            metadatas=[{"type": "session", "session_id": session_id,
                       "timestamp": session_data["timestamp"]}]
        )
    return True

def recall_sessions(query=None, limit=10):
    """Search past sessions. With no query, returns most recent."""
    if query and _init_vector_store():
        results = _collection.query(
            query_texts=[query],
            n_results=limit,
            where={"type": "session"}
        )
        if results and results.get("documents"):
            session_ids = [m["session_id"] for m in results["metadatas"][0]]
            sessions = []
            for sid in session_ids:
                sf = SESSIONS_DIR / f"{sid}.json"
                if sf.exists():
                    sessions.append(_load_json(sf))
            return sessions

    # Fallback: recent sessions from index
    index = _load_json(INDEX_FILE) if INDEX_FILE.exists() else {"sessions": []}
    entries = index.get("sessions", [])[:limit]
    if query:
        entries = _simple_search(query, entries, limit)
    return entries

def recall_session(session_id):
    """Load a specific session by ID."""
    sf = SESSIONS_DIR / f"{session_id}.json"
    if sf.exists():
        return _load_json(sf)
    return None


# ── Semantic recall (cross-cutting search) ──────────────────────
def recall(query, top_k=5):
    """Search ALL memory (facts + sessions + skills) by semantic similarity."""
    results = []

    # Vector search if available
    if _init_vector_store():
        vr = _collection.query(query_texts=[query], n_results=top_k)
        if vr and vr.get("documents"):
            for doc, meta in zip(vr["documents"][0], vr["metadatas"][0]):
                results.append({
                    "type": meta.get("type", "unknown"),
                    "content": doc,
                    "metadata": meta
                })
        return results

    # Fallback: keyword search across all JSON files
    all_entries = []

    # Facts
    facts = _load_json(KNOWLEDGE_FILE)
    for cat, items in facts.items():
        for k, v in items.items():
            all_entries.append({
                "type": "fact",
                "content": f"{cat}: {k} = {v.get('value', '')}",
                "summary": f"{k}: {v.get('value', '')}"
            })

    # Sessions
    index = _load_json(INDEX_FILE) if INDEX_FILE.exists() else {"sessions": []}
    for s in index.get("sessions", []):
        all_entries.append({
            "type": "session",
            "content": s.get("summary", ""),
            "summary": s.get("summary", "")
        })

    return _simple_search(query, all_entries, top_k)


# ── Skills learned (self-enhancement memory) ────────────────────
def learn_skill(name, description, trigger, procedure):
    """OBI records a new skill or technique he's learned."""
    skills = _load_json(SKILLS_LEARNED_FILE)
    skills[name] = {
        "description": description,
        "trigger": trigger,
        "procedure": procedure,
        "learned": datetime.now(timezone.utc).isoformat(),
        "use_count": 0
    }
    _save_json(SKILLS_LEARNED_FILE, skills)
    if _init_vector_store():
        doc_id = hashlib.md5(f"skill:{name}".encode()).hexdigest()
        _collection.upsert(
            ids=[doc_id],
            documents=[f"Skill: {name}. {description}. Trigger: {trigger}. Procedure: {procedure}"],
            metadatas=[{"type": "skill", "name": name}]
        )
    return True

def recall_skills():
    return _load_json(SKILLS_LEARNED_FILE)

def find_skill(query):
    """Find a relevant learned skill for a given situation."""
    if _init_vector_store():
        results = _collection.query(
            query_texts=[query],
            n_results=3,
            where={"type": "skill"}
        )
        if results and results.get("documents") and results["documents"][0]:
            return [{"name": m.get("name", ""), "content": d}
                    for d, m in zip(results["documents"][0], results["metadatas"][0])]

    skills = _load_json(SKILLS_LEARNED_FILE)
    entries = [{"summary": f"{k}: {v['description']}", "name": k, **v} for k, v in skills.items()]
    return _simple_search(query, entries, 3)


# ── Memory stats ────────────────────────────────────────────────
def stats():
    index = _load_json(INDEX_FILE) if INDEX_FILE.exists() else {"sessions": []}
    facts = _load_json(KNOWLEDGE_FILE)
    skills = _load_json(SKILLS_LEARNED_FILE)
    fact_count = sum(len(v) for v in facts.values()) if isinstance(facts, dict) else 0
    return {
        "sessions": len(index.get("sessions", [])),
        "facts": fact_count,
        "skills_learned": len(skills) if isinstance(skills, dict) else 0,
        "vector_store": "chromadb" if _init_vector_store() else "keyword-fallback",
        "memory_dir": str(MEMORY_DIR),
    }
```

### 2.2 Verify the memory module loads

```bash
cd ~/obi/memory
python -c "
import obi_memory as mem
print('Memory module loaded OK')
print('Stats:', mem.stats())
mem.remember_fact('owner', 'Sean A.K. Manners', 'identity')
mem.remember_preference('voice', 'deep male')
print('Recall:', mem.recall_facts('identity'))
print('Prefs:', mem.recall_preferences())
print('Search:', mem.recall('Sean'))
"
```

If this fails, diagnose and fix. The memory module MUST work before proceeding.

---

## PHASE 3 — Enhanced Bridge with Memory + Subscription Support

### 3.1 Create `~/obi/memory/__init__.py`

```python
from .obi_memory import *
```

### 3.2 Update `obi_bridge.py`

Open `~/AionUi/obi-shell/bridge/obi_bridge.py` and add the following capabilities. Do NOT rewrite the entire file — patch these additions into the existing code.

#### 3.2.1 Add memory imports after the existing imports (line ~32)

After `from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer`, add:

```python
# ── memory agent ────────────────────────────────────────────────
MEMORY_DIR = os.path.expanduser("~/obi/memory")
if os.path.isdir(MEMORY_DIR) and MEMORY_DIR not in sys.path:
    sys.path.insert(0, MEMORY_DIR)

_memory = None
def get_memory():
    global _memory
    if _memory is None:
        try:
            import obi_memory
            _memory = obi_memory
        except Exception as e:
            _memory = e
    return _memory
```

#### 3.2.2 Add memory endpoints to `do_POST` (after the `/fs/write` line)

```python
if path == "/memory/recall":    return self._mem_recall()
if path == "/memory/remember":  return self._mem_remember()
if path == "/memory/sessions":  return self._mem_sessions()
if path == "/memory/save":      return self._mem_save_session()
if path == "/memory/stats":     return self._mem_stats()
if path == "/memory/learn":     return self._mem_learn_skill()
```

#### 3.2.3 Add memory endpoint implementations (after `_fs_write` method)

```python
def _mem_recall(self):
    if not self._authed(): return self._json({"error": "unauthorized"}, 401)
    b = self._read()
    m = get_memory()
    if isinstance(m, Exception):
        return self._json({"error": f"Memory agent not available: {m}"}, 500)
    query = b.get("query", "")
    try:
        results = m.recall(query, top_k=b.get("limit", 5))
        return self._json({"results": results, "query": query})
    except Exception as e:
        return self._json({"error": str(e)}, 500)

def _mem_remember(self):
    if not self._authed(): return self._json({"error": "unauthorized"}, 401)
    b = self._read()
    m = get_memory()
    if isinstance(m, Exception):
        return self._json({"error": f"Memory agent not available: {m}"}, 500)
    try:
        if b.get("type") == "preference":
            m.remember_preference(b["key"], b["value"])
        else:
            m.remember_fact(b["key"], b["value"], b.get("category", "general"))
        return self._json({"ok": True})
    except Exception as e:
        return self._json({"error": str(e)}, 500)

def _mem_sessions(self):
    if not self._authed(): return self._json({"error": "unauthorized"}, 401)
    b = self._read()
    m = get_memory()
    if isinstance(m, Exception):
        return self._json({"error": f"Memory agent not available: {m}"}, 500)
    try:
        sessions = m.recall_sessions(query=b.get("query"), limit=b.get("limit", 10))
        return self._json({"sessions": sessions})
    except Exception as e:
        return self._json({"error": str(e)}, 500)

def _mem_save_session(self):
    if not self._authed(): return self._json({"error": "unauthorized"}, 401)
    b = self._read()
    m = get_memory()
    if isinstance(m, Exception):
        return self._json({"error": f"Memory agent not available: {m}"}, 500)
    try:
        m.save_session(b["session_id"], b["messages"], b.get("summary"))
        return self._json({"ok": True})
    except Exception as e:
        return self._json({"error": str(e)}, 500)

def _mem_stats(self):
    if not self._authed(): return self._json({"error": "unauthorized"}, 401)
    m = get_memory()
    if isinstance(m, Exception):
        return self._json({"error": f"Memory agent not available: {m}"}, 500)
    try:
        return self._json(m.stats())
    except Exception as e:
        return self._json({"error": str(e)}, 500)

def _mem_learn_skill(self):
    if not self._authed(): return self._json({"error": "unauthorized"}, 401)
    b = self._read()
    m = get_memory()
    if isinstance(m, Exception):
        return self._json({"error": f"Memory agent not available: {m}"}, 500)
    try:
        m.learn_skill(b["name"], b["description"], b.get("trigger", ""), b.get("procedure", ""))
        return self._json({"ok": True})
    except Exception as e:
        return self._json({"error": str(e)}, 500)
```

#### 3.2.4 Add `/memory/stats` to `do_GET` (after the `/health` handler)

```python
if path == "/memory/stats":
    return self._mem_stats()
```

#### 3.2.5 Update the `/health` response to include memory status

In the existing `_health` handler, add:
```python
"memory": not isinstance(get_memory(), Exception),
```

#### 3.2.6 Print memory status at startup

In the `main()` function, after the skills print line, add:
```python
print(f"  memory   {MEMORY_DIR}  ({'loaded' if not isinstance(get_memory(), Exception) else 'UNAVAILABLE — install chromadb or run without'})")
```

---

## PHASE 4 — Frontend: Memory Integration + Subscription Support + Auto-Delegation

Now modify `~/AionUi/obi-shell/index.html`. These are SURGICAL edits — do not rewrite the entire file.

### 4.1 Add subscription/credits provider support

Find the `PROVIDERS` constant (around line 627). Replace it with this expanded version:

```javascript
const PROVIDERS={
  bridge:{name:'Obliteratus Bridge (Termux)',endpoint:'http://localhost:8420',key:false,model:'',style:'bridge',hint:'Run obi_bridge.py on your device. Serves the app + device control + local model.',subscription:false},
  openrouter:{name:'OpenRouter',endpoint:'https://openrouter.ai/api/v1/chat/completions',key:true,model:'anthropic/claude-3.5-sonnet',style:'openai',hint:'Works in-browser. Supports API keys AND prepaid credits. Buy credits at openrouter.ai/credits — no monthly subscription needed. Paste your OpenRouter key.',subscription:true,creditsUrl:'https://openrouter.ai/credits',balanceEndpoint:'https://openrouter.ai/api/v1/auth/key'},
  anthropic:{name:'Anthropic (direct)',endpoint:'https://api.anthropic.com/v1/messages',key:true,model:'claude-3-5-sonnet-latest',style:'anthropic',hint:'Direct browser access — key stays on this device. Uses prepaid API credits from console.anthropic.com.',subscription:true,creditsUrl:'https://console.anthropic.com/settings/billing'},
  ollama:{name:'Ollama (local)',endpoint:'http://localhost:11434/v1/chat/completions',key:false,model:'llama3.1',style:'openai',hint:'Free, runs locally. No API key, no credits, no subscription. Run Ollama with OLLAMA_ORIGINS=* for browser access.',subscription:false},
  openai_compat:{name:'OpenAI-compatible',endpoint:'',key:true,model:'',style:'openai',hint:'Any /v1/chat/completions endpoint (LM Studio, vLLM, Together, Groq…). Check your provider for subscription/credit options.',subscription:false},
};
```

### 4.2 Add credits/balance checking function

After the `connModel()` function (around line 638), add:

```javascript
async function checkCredits(){
  const p=PROVIDERS[S.conn.provider];
  if(!p||!p.subscription||!p.balanceEndpoint)return null;
  try{
    const headers={'Content-Type':'application/json'};
    if(S.conn.key)headers['Authorization']='Bearer '+S.conn.key;
    if(S.conn.provider==='openrouter'){headers['HTTP-Referer']=location.origin;}
    const r=await fetch(p.balanceEndpoint,{headers});
    if(!r.ok)return null;
    const j=await r.json();
    // OpenRouter returns {data:{credits,limit,usage}}
    if(j.data){
      return {
        credits: j.data.credits!=null ? parseFloat(j.data.credits) : null,
        limit: j.data.limit!=null ? parseFloat(j.data.limit) : null,
        usage: j.data.usage!=null ? parseFloat(j.data.usage) : null,
        remaining: j.data.limit!=null&&j.data.usage!=null ? parseFloat(j.data.limit)-parseFloat(j.data.usage) : j.data.credits!=null ? parseFloat(j.data.credits) : null,
        provider: S.conn.provider
      };
    }
    return null;
  }catch(e){return null;}
}
```

### 4.3 Update the settings panel — add credits display and subscription info

Find the `<!-- ══ SETTINGS ══ -->` section. After the connection test button area (the `<div>` containing `c-test` and `c-status`), add:

```html
<div id="credits-info" style="display:none;margin-top:10px;padding:10px 12px;border-radius:var(--r-sm);background:var(--glass);border:1px solid var(--hair)">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <span style="font-family:var(--mono);font-size:10px;letter-spacing:.1em;color:var(--tan);text-transform:uppercase">Credits / Balance</span>
    <span id="credits-amount" style="font-family:var(--mono);font-size:14px;font-weight:700;color:var(--gold)">—</span>
  </div>
  <div id="credits-detail" style="font-size:11px;color:var(--tan-dim);margin-top:4px"></div>
  <a id="credits-link" href="#" target="_blank" rel="noopener" style="font-size:11px;color:var(--lens);margin-top:6px;display:inline-block;text-decoration:none">Add credits →</a>
</div>
```

### 4.4 Wire up credits display in the provider change handler

Find where the provider select fires (the `provsel` event listener). After the connection test logic, add:

```javascript
// Show credits info for subscription providers
async function updateCreditsDisplay(){
  const p=PROVIDERS[S.conn.provider];
  const ci=$('#credits-info');
  if(!p||!p.subscription){ci.style.display='none';return;}
  ci.style.display='block';
  const link=$('#credits-link');
  link.href=p.creditsUrl||'#';
  link.textContent=p.creditsUrl?'Add credits →':'';
  const bal=await checkCredits();
  const amt=$('#credits-amount');
  const det=$('#credits-detail');
  if(bal&&bal.remaining!=null){
    amt.textContent='$'+bal.remaining.toFixed(4);
    amt.style.color=bal.remaining<1?'var(--red)':bal.remaining<5?'var(--amber)':'var(--gold)';
    det.textContent=bal.usage!=null?`Used: $${bal.usage.toFixed(4)} of $${bal.limit.toFixed(2)} limit`:'Prepaid credits';
  }else{
    amt.textContent='—';
    det.textContent='Connect and test to check balance';
  }
}
```

Call `updateCreditsDisplay()` at the end of the provider-change handler AND after a successful connection test.

### 4.5 Memory integration in the frontend

#### 4.5.1 Add memory slash commands

In the `handleCommand()` function, add these command handlers (alongside the existing `/team`, `/scan`, etc.):

```javascript
if(cmd==='remember'||cmd==='mem'){
  if(!arg){return addObi('Usage: /remember <key>=<value> — store a fact. /remember ? <query> — recall.');}
  if(arg.startsWith('?')){
    // Recall
    const q=arg.slice(1).trim()||'recent';
    if(bridgeUp){
      try{
        const r=await fetch(bridgeEP()+'/memory/recall',{method:'POST',headers:{'Content-Type':'application/json','X-OBI-Token':S.conn.token||''},body:JSON.stringify({query:q,limit:5})});
        const j=await r.json();
        if(j.results&&j.results.length){
          const out=j.results.map(r=>`• [${r.type}] ${r.content||r.summary||JSON.stringify(r.metadata)}`).join('\n');
          return addObi('Recalled from memory:\n'+out);
        }else{return addObi('No memories match that query.');}
      }catch(e){return addObi('Memory recall failed: '+e.message);}
    }else{
      // Offline: check localStorage fallback
      const mem=JSON.parse(localStorage.getItem('obi.memory')||'{}');
      const keys=Object.keys(mem).filter(k=>k.toLowerCase().includes(q.toLowerCase()));
      if(keys.length){return addObi('Local memory:\n'+keys.map(k=>`• ${k}: ${mem[k]}`).join('\n'));}
      return addObi('No local memories found. Connect the bridge for full memory search.');
    }
  }
  // Store
  const eq=arg.indexOf('=');
  if(eq<1){return addObi('Format: /remember key=value');}
  const key=arg.slice(0,eq).trim(), val=arg.slice(eq+1).trim();
  if(bridgeUp){
    try{
      await fetch(bridgeEP()+'/memory/remember',{method:'POST',headers:{'Content-Type':'application/json','X-OBI-Token':S.conn.token||''},body:JSON.stringify({key,value:val,category:'user'})});
      return addObi(`Remembered: ${key} = ${val}`);
    }catch(e){return addObi('Memory store failed: '+e.message);}
  }else{
    const mem=JSON.parse(localStorage.getItem('obi.memory')||'{}');
    mem[key]=val;
    localStorage.setItem('obi.memory',JSON.stringify(mem));
    return addObi(`Remembered locally: ${key} = ${val} (bridge offline — stored in localStorage)`);
  }
}

if(cmd==='memstats'){
  if(bridgeUp){
    try{
      const r=await fetch(bridgeEP()+'/memory/stats',{headers:{'X-OBI-Token':S.conn.token||''}});
      const j=await r.json();
      return addObi(`Memory stats:\n• Sessions archived: ${j.sessions}\n• Facts stored: ${j.facts}\n• Skills learned: ${j.skills_learned}\n• Vector store: ${j.vector_store}\n• Location: ${j.memory_dir}`);
    }catch(e){return addObi('Could not fetch memory stats: '+e.message);}
  }
  return addObi('Bridge offline — memory stats unavailable. Local memory has '+Object.keys(JSON.parse(localStorage.getItem('obi.memory')||'{}')).length+' entries.');
}

if(cmd==='forget'){
  if(!arg){return addObi('Usage: /forget <key> — remove a stored fact');}
  const mem=JSON.parse(localStorage.getItem('obi.memory')||'{}');
  delete mem[arg.trim()];
  localStorage.setItem('obi.memory',JSON.stringify(mem));
  return addObi(`Forgot: ${arg.trim()} (local). Bridge-side memory requires manual cleanup.`);
}
```

#### 4.5.2 Auto-save sessions on close/navigate

At the end of the script, before the closing `</script>` tag, add:

```javascript
// ── Auto-save session to memory on page hide ─────────────────
document.addEventListener('visibilitychange', ()=>{
  if(document.visibilityState==='hidden' && msgs.length>2){
    const sid='session_'+Date.now();
    // Save to localStorage always
    const hist=JSON.parse(localStorage.getItem('obi.sessions')||'[]');
    hist.unshift({id:sid,ts:new Date().toISOString(),count:msgs.length,
      preview:msgs.slice(-3).map(m=>m.text.slice(0,60)).join(' | ')});
    localStorage.setItem('obi.sessions',JSON.stringify(hist.slice(0,100)));
    // If bridge is up, save to persistent memory
    if(bridgeUp){
      navigator.sendBeacon(bridgeEP()+'/memory/save',
        JSON.stringify({session_id:sid,messages:msgs.slice(-50)}));
    }
  }
});
```

#### 4.5.3 Memory context injection — OBI recalls relevant memories before answering

In the `streamChat` call for normal chat (around line 1048), BEFORE the `streamChat` call, add memory recall:

```javascript
// Inject memory context if bridge + memory available
let memoryContext = '';
if(bridgeUp){
  try{
    const lastUserMsg = hist.filter(m=>m.role==='you').pop();
    if(lastUserMsg){
      const mr = await fetch(bridgeEP()+'/memory/recall',{
        method:'POST',
        headers:{'Content-Type':'application/json','X-OBI-Token':S.conn.token||''},
        body:JSON.stringify({query:lastUserMsg.text, limit:3})
      });
      const mj = await mr.json();
      if(mj.results && mj.results.length){
        memoryContext = '\n\n[MEMORY CONTEXT — recalled from persistent memory, use if relevant:]\n' +
          mj.results.map(r=>'• '+( r.content || r.summary || JSON.stringify(r))).join('\n') +
          '\n[END MEMORY CONTEXT]';
      }
    }
  }catch(e){/* memory recall failed, proceed without */}
}
```

Then modify the `streamChat` call to pass the memory-augmented system prompt:

```javascript
const sysWithMemory = memoryContext ? OBI_SOUL + memoryContext : undefined;
await streamChat(hist, (tok,full)=>stream.update(full), sysWithMemory).then(full=>{
```

### 4.6 Auto-delegation — OBI decides when to delegate

Currently `/team` only fires on explicit command. OBI should auto-detect when a task is complex enough to warrant delegation.

In the main chat handler (where OBI responds without a slash command), AFTER the `streamChat` completes, add auto-delegation detection:

```javascript
// Auto-delegation: check if OBI's response suggests he should delegate
if(full && !S._delegating){
  const shouldDelegate =
    full.length > 600 && (
      /\b(multiple|several|steps?|phases?|components?|aspects?)\b/i.test(full) &&
      /\b(analyz|assess|investigat|examin|review|audit|evaluat)\b/i.test(full)
    ) ||
    /\bI (?:would |should |need to )(?:break this|decompose|delegate|assign|split)\b/i.test(full) ||
    /\blet me (?:bring in|deploy|assemble|mobilize) (?:the |my )?team\b/i.test(full);

  if(shouldDelegate){
    S._delegating=true;
    addObi('This task warrants the full team. Deploying agents now.');
    const userText = hist.filter(m=>m.role==='you').pop()?.text || '';
    await orchestrate(userText);
    S._delegating=false;
  }
}
```

### 4.7 Self-enhancement — OBI learns from interactions

After each successful team orchestration (at the end of the `orchestrate()` function, after `teamPhase='complete'`), add:

```javascript
// Self-enhancement: save the orchestration as a learned pattern
if(bridgeUp){
  try{
    const pattern = {
      name: 'orch_' + Date.now(),
      description: 'Team orchestration for: ' + task.slice(0, 100),
      trigger: task.slice(0, 200),
      procedure: JSON.stringify({
        plan: plan.map(p=>({agent:p.agent, subtask:p.subtask})),
        agents_used: team.map(t=>t.agent),
        success: team.every(t=>t.status==='done')
      })
    };
    fetch(bridgeEP()+'/memory/learn',{
      method:'POST',
      headers:{'Content-Type':'application/json','X-OBI-Token':S.conn.token||''},
      body:JSON.stringify(pattern)
    }).catch(()=>{});
  }catch(e){}
}
```

### 4.8 Update help text and hint chips

Add the new memory commands to the help text and hint chips:

In the help command handler, add:
```
/remember key=value — store a fact in OBI's persistent memory
/remember ? query — recall from memory
/memstats — memory agent statistics
/forget key — remove a stored fact
```

In the hint chips array, add: `'/remember'`, `'/memstats'`

### 4.9 Add memory indicator to the status bar

After the bridge health-check code that sets `bridgeUp`, add a memory status indicator:

```javascript
// Memory status in header
if(bridgeUp){
  fetch(bridgeEP()+'/memory/stats').then(r=>r.json()).then(j=>{
    const lbl = document.querySelector('.core-label');
    if(lbl && j.sessions != null){
      lbl.textContent = `CORE ONLINE · ${j.facts} memories`;
    }
  }).catch(()=>{});
}
```

---

## PHASE 5 — Production Hardening

### 5.1 Connection resilience in the bridge

Add automatic reconnection and retry logic. In `obi_bridge.py`, wrap the Ollama proxy (`_chat` method) with retry:

```python
def _chat(self):
    """OpenAI-style chat, forwarded to local Ollama. Retries on transient failures."""
    if not self._authed(): return self._json({"error": "unauthorized"}, 401)
    payload = self._read()
    retries = 3
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                OLLAMA + "/v1/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"})
            up = urllib.request.urlopen(req, timeout=120)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self._cors(); self.end_headers()
            while True:
                chunk = up.read(1024)
                if not chunk: break
                try: self.wfile.write(chunk)
                except Exception: break
            return
        except Exception as e:
            if attempt < retries - 1:
                import time; time.sleep(1 * (attempt + 1))
                continue
            self._json({"error": f"ollama unreachable at {OLLAMA} after {retries} attempts: {e}"}, 502)
```

### 5.2 Graceful offline/online transitions in the frontend

Add a connection monitor that updates UI state:

```javascript
// Connection health monitor — runs every 30s
setInterval(async ()=>{
  if(S.conn.provider==='bridge'||bridgeUp){
    try{
      const r=await fetch(bridgeEP()+'/health',{signal:AbortSignal.timeout(3000)});
      const prev=bridgeUp;
      bridgeUp=r.ok;
      if(!prev&&bridgeUp){
        notify('Bridge reconnected','OBI has full device access again.');
        document.querySelectorAll('.bridge-pill').forEach(p=>{p.textContent='connected';p.classList.remove('off');});
      }
      if(prev&&!bridgeUp){
        notify('Bridge disconnected','Falling back to offline scanners.');
        document.querySelectorAll('.bridge-pill').forEach(p=>{p.textContent='not connected';p.classList.add('off');});
      }
    }catch(e){
      if(bridgeUp){bridgeUp=false;document.querySelectorAll('.bridge-pill').forEach(p=>{p.textContent='not connected';p.classList.add('off');});}
    }
  }
},30000);
```

### 5.3 Error boundaries in orchestration

In the `orchestrate()` function, wrap each subagent run with proper error recovery:

```javascript
// In the for loop over team:
try{
  t.output=live?await runSubagentLive(t,task):await runSubagentOffline(t,task);
  t.status='done';
}catch(e){
  t.status='failed';
  t.output=`[${AGENT_PROFILES[t.agent].name}] Agent failed: ${e.message}. Task: ${t.subtask}`;
  // Don't abort — continue with remaining agents
  console.warn(`Subagent ${t.agent} failed:`, e);
}
```

### 5.4 Add request logging to the bridge

At the top of `do_GET` and `do_POST` in `obi_bridge.py`, add:

```python
def log_request(self, method, path):
    ts = time.strftime("%H:%M:%S")
    print(f"  [{ts}] {method} {path}")
```

And call `self.log_request("GET", path)` / `self.log_request("POST", path)` at the top of each handler. Remove or comment out the `def log_message(self, *a): pass` line so you can see what's happening.

---

## PHASE 6 — OBI Configuration File

### 6.1 Create `~/obi/config/obi.yaml`

```yaml
# OBI Configuration — edit this to customize your agent
identity:
  name: "OBI"
  full_name: "Obliteratus"
  owner: "Sean A.K. Manners"
  role: "Reverse-engineering & adversarial-intelligence agent"

server:
  host: "127.0.0.1"
  port: 8420
  allow_exec: false
  token: ""

model:
  provider: "openrouter"  # openrouter | anthropic | ollama | bridge
  model: "anthropic/claude-3.5-sonnet"
  temperature: 0.7
  max_tokens: 1600

memory:
  enabled: true
  backend: "chromadb"  # chromadb | keyword
  auto_save_sessions: true
  max_session_archive: 200
  recall_on_chat: true
  recall_top_k: 3

team:
  auto_delegate: true
  auto_delegate_threshold: 600  # response length before auto-delegation check
  max_agents_per_task: 4
  parallel_execution: false  # future: run subagents in parallel

self_enhancement:
  enabled: true
  learn_from_orchestration: true
  learn_from_corrections: true
  prompt_evolution: false  # future: OBI refines his own system prompt

security:
  scan_inputs: true
  scan_tool_results: true
  log_requests: true
  bind_localhost_only: true
```

### 6.2 Load config in the bridge

Add config loading to `obi_bridge.py` startup:

```python
import yaml  # or fall back to JSON

CONFIG_FILE = os.path.expanduser("~/obi/config/obi.yaml")
_config = {}

def load_config():
    global _config
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                _config = yaml.safe_load(f) or {}
        except ImportError:
            # No yaml — try JSON fallback
            json_file = CONFIG_FILE.replace('.yaml', '.json')
            if os.path.isfile(json_file):
                with open(json_file) as f:
                    _config = json.load(f)
        except Exception as e:
            print(f"  [config] Failed to load {CONFIG_FILE}: {e}")
    return _config

def cfg(path, default=None):
    """Dot-path config access: cfg('memory.enabled', True)"""
    keys = path.split('.')
    val = _config
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return default
    return val if val is not None else default
```

---

## PHASE 7 — Launch Script

### 7.1 Create `~/obi/start.sh`

```bash
#!/data/data/com.termux/files/usr/bin/bash
# ════════════════════════════════════════════════════════════════
#  OBI — One-shot launch script
#  Usage: bash ~/obi/start.sh
# ════════════════════════════════════════════════════════════════

OBI_ROOT="$HOME/AionUi/obi-shell"
BRIDGE="$OBI_ROOT/bridge/obi_bridge.py"

# Export config
export OBI_ALLOW_EXEC="${OBI_ALLOW_EXEC:-0}"
export OBI_TOKEN="${OBI_TOKEN:-}"
export OBI_PORT="${OBI_PORT:-8420}"
export OBI_HOST="${OBI_HOST:-127.0.0.1}"
export OBI_SKILLS_DIR="$HOME/obi/skills/adversarial"
export OBI_COMMANDS_DIR="$HOME/obi/commands"
export PYTHONPATH="$HOME/obi/memory:$HOME/obi/skills/adversarial:$HOME/obi/commands:$PYTHONPATH"

# Start Ollama if available and not running
if command -v ollama &>/dev/null; then
  if ! pgrep -x ollama &>/dev/null; then
    echo "→ Starting Ollama in background..."
    ollama serve &>/dev/null &
    sleep 2
  fi
fi

# Kill any existing bridge
pkill -f obi_bridge.py 2>/dev/null
sleep 1

# Launch
echo "═══════════════════════════════════════════════════════"
echo "  Launching OBI..."
echo "═══════════════════════════════════════════════════════"
exec python "$BRIDGE" --port "$OBI_PORT" --host "$OBI_HOST" --dir "$OBI_ROOT"
```

```bash
chmod +x ~/obi/start.sh
```

---

## PHASE 8 — Verification

Run ALL of these checks. Every single one must pass before you report success.

### 8.1 Memory agent

```bash
cd ~/obi/memory
python -c "
import obi_memory as mem
mem.remember_fact('test_key', 'test_value', 'test')
assert mem.recall_facts('test')['test_key']['value'] == 'test_value'
mem.remember_preference('test_pref', 'yes')
assert mem.recall_preferences()['test_pref']['value'] == 'yes'
mem.save_session('test_session', [{'role':'you','text':'hello'},{'role':'obi','text':'greetings'}], 'test session summary')
sessions = mem.recall_sessions(limit=1)
assert len(sessions) > 0
results = mem.recall('test')
assert len(results) > 0
stats = mem.stats()
assert stats['facts'] > 0
print('ALL MEMORY TESTS PASSED')
"
```

### 8.2 Bridge starts

```bash
cd ~/AionUi/obi-shell/bridge
timeout 5 python obi_bridge.py --port 18420 &
sleep 2
# Health check
curl -s http://localhost:18420/health | python -m json.tool
# Memory stats endpoint
curl -s http://localhost:18420/memory/stats | python -m json.tool
# Memory store
curl -s -X POST http://localhost:18420/memory/remember -H 'Content-Type: application/json' -d '{"key":"bridge_test","value":"works","category":"test"}'
# Memory recall
curl -s -X POST http://localhost:18420/memory/recall -H 'Content-Type: application/json' -d '{"query":"bridge test"}'
# Kill test server
kill %1 2>/dev/null
echo "BRIDGE TESTS PASSED"
```

### 8.3 App loads

```bash
curl -s http://localhost:18420/ | head -5
# Should show <!doctype html>
```

### 8.4 Full startup

```bash
bash ~/obi/start.sh &
sleep 3
curl -s http://localhost:8420/health | python -m json.tool
# Verify: status=ok, memory=true, skills=(true or false depending on skill files)
kill %1 2>/dev/null
echo "FULL STARTUP VERIFIED"
```

---

## PHASE 9 — Final State Checklist

Before reporting completion, verify EACH of these is true:

- [ ] `~/obi/memory/obi_memory.py` exists and loads without errors
- [ ] `~/obi/memory/__init__.py` exists
- [ ] `~/obi/config/obi.yaml` exists with correct defaults
- [ ] `~/obi/start.sh` exists and is executable
- [ ] `~/obi/skills/adversarial/` directory exists
- [ ] `~/obi/commands/` directory exists
- [ ] `~/obi/logs/` directory exists
- [ ] `obi_bridge.py` has memory endpoints (`/memory/recall`, `/memory/remember`, `/memory/stats`, `/memory/sessions`, `/memory/save`, `/memory/learn`)
- [ ] `obi_bridge.py` `/health` endpoint reports `memory: true/false`
- [ ] `index.html` has the `PROVIDERS` object with `subscription` and `creditsUrl` fields
- [ ] `index.html` has `checkCredits()` function
- [ ] `index.html` has credits display UI (`#credits-info`, `#credits-amount`)
- [ ] `index.html` has `/remember`, `/memstats`, `/forget` slash commands
- [ ] `index.html` has auto-session-save on `visibilitychange`
- [ ] `index.html` has memory context injection before chat (recall relevant memories)
- [ ] `index.html` has auto-delegation detection after chat responses
- [ ] `index.html` has self-enhancement (saves orchestration patterns)
- [ ] `index.html` has connection health monitor (30s interval)
- [ ] `index.html` updated help text includes memory commands
- [ ] `index.html` updated hint chips include `/remember` and `/memstats`
- [ ] Bridge starts on `http://localhost:8420` and serves the app
- [ ] `bash ~/obi/start.sh` launches everything in one command
- [ ] Memory agent can store and recall facts
- [ ] Memory agent can save and search sessions
- [ ] Memory agent gracefully degrades without ChromaDB (uses keyword fallback)

---

## SUMMARY OF WHAT YOU ARE BUILDING

You are building OBI into a production-grade agent with:

1. **Persistent memory** — facts, preferences, session archives, learned skills — stored in ChromaDB (with keyword fallback) at `~/obi/memory/`. The bridge exposes memory via REST endpoints. The frontend injects recalled memories into OBI's context before answering, and auto-saves sessions when the user leaves.

2. **Subscription/credits support** — OpenRouter and Anthropic providers now show credit balance in Settings, link to add credits, and color-code low balance warnings. Users don't need to understand API keys vs subscriptions — they see "credits remaining" and a link to buy more.

3. **Auto-delegation** — OBI detects when his response is complex enough to warrant the team, and automatically triggers orchestration without the user typing `/team`.

4. **Self-enhancement** — every team orchestration is saved as a learned skill pattern. OBI accumulates institutional knowledge of what agent combinations and decomposition strategies work for which task types.

5. **Production hardening** — connection resilience with retry logic, health monitoring every 30 seconds with automatic reconnect notifications, error boundaries in orchestration (one agent failing doesn't abort the rest), request logging for debugging.

6. **One-command launch** — `bash ~/obi/start.sh` starts Ollama (if available), kills any stale bridge, and launches OBI with all environment variables wired.

Execute all phases. Do not stop until every verification check passes.
