#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════╗
║                    NEXUM PC NODE v10.0                                   ║
║                                                                          ║
║  Подключи свой ПК к NEXUM одной командой в терминале.                   ║
║  Нода регистрируется через pairing-код и становится агентом              ║
║  с полным доступом к твоему железу.                                      ║
║                                                                          ║
║  ┌─────────────────────────────────────────────────────────────────┐    ║
║  │  python nexum_agent.py                                           │    ║
║  └─────────────────────────────────────────────────────────────────┘    ║
║                                                                          ║
║  Env (обязательно):                                                      ║
║    BOT_TOKEN=xxx          — токен бота                                   ║
║    AGENT_OWNER_ID=xxx     — твой Telegram ID                            ║
║  Env (опционально):                                                      ║
║    NEXUM_AI_KEY=xxx       — ключ AI (Anthropic/OpenAI/Groq/Gemini)      ║
║    NODE_NAME=мой_пк       — имя ноды (default: hostname)                ║
║    NEXUM_WORKSPACE=/path  — рабочая папка                               ║
║    CONFIRM_MODE=dangerous — always / dangerous / never                   ║
║                                                                          ║
║  Возможности:                                                            ║
║    📁 FS        read/write/edit/grep/find/ls/patch                      ║
║    ⚡ Runtime   exec/bash/process/run_code                              ║
║    🌐 Web       web_search/web_fetch/browser (Playwright)               ║
║    🖥  Nodes     screenshot/sysinfo/processes/network                   ║
║    🎨 Canvas    type/key/click/move/scroll (pyautogui)                  ║
║    ⏰ Cron      планировщик задач                                       ║
║    💓 Heartbeat проактивный мониторинг                                  ║
║    🧬 Skills    SKILL.md + шаблоны                                      ║
║    🤖 Agents    multi-agent routing                                      ║
║    🧠 Memory    персистентная память (MEMORY.md)                        ║
║    🔒 Policy    allow/deny групп инструментов                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import os, sys, json, time, asyncio, logging, subprocess, platform, shutil
import base64, tempfile, re, hashlib, signal, threading, sqlite3
import traceback, random, string
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple

# ── Авто-установка зависимостей ───────────────────────────────────────────
def _pip(*pkgs):
    for pkg in pkgs:
        mod = pkg.split("[")[0].replace("-", "_").split("==")[0]
        try:
            __import__(mod)
        except ImportError:
            print(f"  📦 {pkg}...", end=" ", flush=True)
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg, "-q", "--break-system-packages"],
                capture_output=True
            )
            print("✓" if r.returncode == 0 else "✗")

print("🔍 Проверяю зависимости...")
_pip("requests", "psutil", "apscheduler")
for pkg in ["pyautogui", "pyperclip", "pillow", "playwright"]:
    try:
        _pip(pkg)
    except:
        pass

import requests
import psutil
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    HAS_GUI = True
except:
    HAS_GUI = False

try:
    from PIL import Image
    import io as _io
    HAS_PIL = True
except:
    HAS_PIL = False

try:
    import pyperclip
    HAS_CLIP = True
except:
    HAS_CLIP = False

# ═══════════════════════════════════════════════════════════════════════════
#  КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

# Загружаем .env если есть
try:
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
except:
    pass

BOT_TOKEN   = os.getenv("BOT_TOKEN", "")
OWNER_ID    = int(os.getenv("AGENT_OWNER_ID", "0"))
AI_KEY      = os.getenv("NEXUM_AI_KEY") or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY", "")
AI_PROVIDER = os.getenv("NEXUM_AI_PROVIDER", "auto")
AI_MODEL    = os.getenv("NEXUM_AI_MODEL", "")
NODE_NAME   = os.getenv("NODE_NAME", f"node@{platform.node()}")
VERSION     = "10.0"
PLATFORM    = platform.system()

WORKSPACE = Path(os.getenv("NEXUM_WORKSPACE", Path.home() / ".nexum" / "workspace"))
WORKSPACE.mkdir(parents=True, exist_ok=True)

MEMORY_FILE    = WORKSPACE / "MEMORY.md"
SOUL_FILE      = WORKSPACE / "SOUL.md"
HEARTBEAT_FILE = WORKSPACE / "HEARTBEAT.md"
SKILLS_DIR     = WORKSPACE / "skills"
SKILLS_DIR.mkdir(exist_ok=True)
LOG_FILE = WORKSPACE / "node.log"
DB_PATH  = WORKSPACE / "node.db"

# ═══════════════════════════════════════════════════════════════════════════
#  ЛОГИРОВАНИЕ
# ═══════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
    ]
)
log = logging.getLogger("NEXUM")

# ═══════════════════════════════════════════════════════════════════════════
#  БАЗА ДАННЫХ
# ═══════════════════════════════════════════════════════════════════════════
def _db():
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS cron_jobs(
            id TEXT PRIMARY KEY, label TEXT,
            schedule TEXT, prompt TEXT,
            active INTEGER DEFAULT 1,
            delete_after INTEGER DEFAULT 0,
            ts TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS tool_policy(
            tool TEXT PRIMARY KEY, policy TEXT
        );
        CREATE TABLE IF NOT EXISTS tool_stats(
            tool TEXT, ts TEXT DEFAULT (datetime('now')), ok INTEGER DEFAULT 1
        );
        """)
    with _db() as c:
        for r in c.execute("SELECT tool,policy FROM tool_policy").fetchall():
            _tool_policy[r["tool"]] = r["policy"]

# ═══════════════════════════════════════════════════════════════════════════
#  СОСТОЯНИЕ
# ═══════════════════════════════════════════════════════════════════════════
_tool_policy:  Dict[str, str]   = {}
_confirm_mode: str              = os.getenv("CONFIRM_MODE", "dangerous")
_elevated:     bool             = False
_active_agent: str              = "main"
_session_start                  = datetime.now()
_running:      bool             = True
_pending:      Dict[str, Dict]  = {}
_bg_procs:     Dict[str, Dict]  = {}
_sub_sessions: Dict[str, Dict]  = {}
_browser_page                   = None

# pairing state
_paired:       bool             = False
_pair_code:    Optional[str]    = None
_offset:       int              = 0

TOOL_GROUPS = {
    "fs":       ["read","write","edit","apply_patch","ls","grep","find",
                 "delete_file","move_file","copy_file"],
    "runtime":  ["exec","bash","process","run_code"],
    "web":      ["web_search","web_fetch","browser"],
    "nodes":    ["nodes"],
    "cron":     ["cron"],
    "memory":   ["memory"],
    "sessions": ["sessions_spawn","sessions_list","sessions_send","sessions_history"],
    "canvas":   ["canvas"],
    "skills":   ["skill_list","skill_read","skill_write","skill_search","skill_install"],
}
TOOL_GROUPS["all"] = list({t for g in TOOL_GROUPS.values() for t in g})

def _allowed(tool: str) -> bool:
    pol = _tool_policy.get(tool) or _tool_policy.get("all", "allow")
    return pol != "deny"

def _stat(tool: str, ok: bool = True):
    try:
        with _db() as c:
            c.execute("INSERT INTO tool_stats(tool,ok) VALUES(?,?)", (tool, 1 if ok else 0))
    except:
        pass

# ═══════════════════════════════════════════════════════════════════════════
#  TELEGRAM API
# ═══════════════════════════════════════════════════════════════════════════
BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

def tg(method: str, **kw) -> dict:
    try:
        r = requests.post(f"{BASE}/{method}", json=kw, timeout=30)
        return r.json()
    except Exception as e:
        log.error(f"TG {method}: {e}")
        return {}

def send(chat_id: int, text: str, markup=None, parse="HTML") -> dict:
    text = str(text)[:4096]
    kw = {"chat_id": chat_id, "text": text, "parse_mode": parse}
    if markup:
        kw["reply_markup"] = json.dumps(markup)
    return tg("sendMessage", **kw)

def send_split(chat_id: int, text: str, parse="HTML"):
    for i, ch in enumerate([text[i:i+4000] for i in range(0, len(text), 4000)]):
        send(chat_id, ch, parse=parse)
        if i > 0:
            time.sleep(0.3)

def send_typing(chat_id: int):
    tg("sendChatAction", chat_id=chat_id, action="typing")

def send_photo(chat_id: int, data: bytes, caption: str = ""):
    try:
        requests.post(f"{BASE}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption[:1024]},
            files={"photo": ("img.png", data, "image/png")},
            timeout=30)
    except Exception as e:
        log.error(f"send_photo: {e}")

def send_doc(chat_id: int, data: bytes, name: str, caption: str = ""):
    try:
        requests.post(f"{BASE}/sendDocument",
            data={"chat_id": chat_id, "caption": caption[:1024]},
            files={"document": (name, data, "application/octet-stream")},
            timeout=60)
    except Exception as e:
        log.error(f"send_doc: {e}")

def answer_cb(cb_id: str, text: str = ""):
    tg("answerCallbackQuery", callback_query_id=cb_id, text=text)

def ikb(*rows):
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}

# ═══════════════════════════════════════════════════════════════════════════
#  PAIRING FLOW
#  1. Нода генерирует 6-значный код
#  2. Отправляет боту сообщение с кодом
#  3. Ждёт /pair <код> от пользователя в том же чате
#  4. После подтверждения — принимает команды
# ═══════════════════════════════════════════════════════════════════════════
def _gen_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def _do_pairing():
    global _pair_code, _paired, _offset

    if not BOT_TOKEN:
        _print_setup(); sys.exit(1)
    if not OWNER_ID:
        _print_setup(); sys.exit(1)

    _pair_code = _gen_code()

    print("\n" + "═" * 62)
    print(f"  NEXUM Node v{VERSION}")
    print("═" * 62)
    print(f"  Хост:      {platform.node()} ({PLATFORM} {platform.release()})")
    print(f"  Node:      {NODE_NAME}")
    print(f"  Workspace: {WORKSPACE}")
    print("═" * 62)
    print()
    print(f"  🔑 Pairing код:  \033[1;33m{_pair_code}\033[0m")
    print()
    print(f"  📱 Отправь боту в Telegram:")
    print(f"     \033[1;32m/pair {_pair_code}\033[0m")
    print()
    print(f"  ⏳ Жду подтверждения (10 мин)...")
    print("═" * 62 + "\n")

    # Отправляем уведомление боту
    result = send(OWNER_ID,
        f"🖥 <b>Новая нода запрашивает подключение</b>\n\n"
        f"Хост: <code>{platform.node()}</code> ({PLATFORM})\n"
        f"Нода: <code>{NODE_NAME}</code>\n\n"
        f"Для подтверждения отправь:\n"
        f"<code>/pair {_pair_code}</code>",
        parse="HTML"
    )
    if not result.get("ok"):
        print("❌ Не удалось отправить сообщение боту.")
        print("   Проверь BOT_TOKEN и напиши боту /start хотя бы раз.")
        sys.exit(1)

    # Polling пока не подтвердят (10 минут)
    deadline = time.time() + 600
    while time.time() < deadline and not _paired:
        try:
            r = requests.get(f"{BASE}/getUpdates",
                params={"offset": _offset, "timeout": 15,
                        "allowed_updates": ["message", "callback_query"]},
                timeout=20)
            if r.status_code != 200:
                time.sleep(2)
                continue
            for upd in r.json().get("result", []):
                _offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                text = msg.get("text", "").strip()
                from_id = msg.get("from", {}).get("id", 0)
                chat_id = msg.get("chat", {}).get("id", 0)
                if from_id == OWNER_ID and text.upper() == f"/PAIR {_pair_code}":
                    _paired = True
                    send(chat_id,
                        f"✅ <b>Нода подключена!</b>\n\n"
                        f"💻 <code>{NODE_NAME}</code> — {PLATFORM}\n"
                        f"📁 <code>{WORKSPACE}</code>\n\n"
                        f"Теперь пиши команды — нода выполнит на твоём ПК.\n"
                        f"/node_help — список команд ноды",
                        parse="HTML")
                    print(f"\n✅ Подключено! Принимаю команды.\n" + "═" * 62 + "\n")
                    break
        except Exception as e:
            log.debug(f"Pair poll: {e}")
            time.sleep(2)

    if not _paired:
        print("❌ Timeout. Запусти заново.")
        sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════
#  УТИЛИТЫ
# ═══════════════════════════════════════════════════════════════════════════
def _sz(b: int) -> str:
    for u, d in [("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)]:
        if b >= d:
            return f"{b/d:.1f}{u}"
    return f"{b}B"

def _resolve(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = WORKSPACE / p
    return p.resolve()

# ═══════════════════════════════════════════════════════════════════════════
#  ИНСТРУМЕНТЫ — group:fs
# ═══════════════════════════════════════════════════════════════════════════
def tool_read(path: str, offset: int = 0, limit: int = 300) -> str:
    if not _allowed("read"):
        return "❌ tool:read запрещён"
    try:
        p = _resolve(path)
        if not p.exists():
            return f"❌ Не найдено: {path}"
        if p.is_dir():
            items = sorted(p.iterdir())[:100]
            lines = [f"{'📂' if i.is_dir() else '📄'} {i.name}{'/' if i.is_dir() else f' ({_sz(i.stat().st_size)})'}"
                     for i in items]
            return f"📁 {p} ({len(items)} items)\n\n" + "\n".join(lines)
        if p.stat().st_size > 10 * 1024 * 1024:
            return f"⚠️ Слишком большой: {_sz(p.stat().st_size)}"
        for enc in ["utf-8", "utf-16", "cp1251", "latin-1"]:
            try:
                lines = p.read_text(encoding=enc).splitlines()
                total = len(lines)
                chunk = lines[offset:offset + limit]
                note = f"\n[строки {offset+1}-{min(offset+limit,total)} из {total}]" if total > limit or offset else f"\n[{total} строк]"
                return f"📄 {p}{note}\n\n" + "\n".join(chunk)
            except UnicodeDecodeError:
                continue
        return f"[бинарный {_sz(p.stat().st_size)}]\n{p.read_bytes()[:200].hex()}"
    except Exception as e:
        return f"❌ read: {e}"

def tool_write(path: str, content: str) -> str:
    if not _allowed("write"):
        return "❌ tool:write запрещён"
    try:
        p = _resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"✅ Записано: {p} ({len(content)} символов)"
    except Exception as e:
        return f"❌ write: {e}"

def tool_edit(path: str, old_str: str, new_str: str) -> str:
    if not _allowed("edit"):
        return "❌ tool:edit запрещён"
    try:
        p = _resolve(path)
        if not p.exists():
            return f"❌ Не найдено: {path}"
        content = p.read_text(encoding="utf-8")
        if old_str not in content:
            return f"❌ Текст не найден:\n{old_str[:100]}"
        p.write_text(content.replace(old_str, new_str, 1), encoding="utf-8")
        return f"✅ Отредактировано: {p}"
    except Exception as e:
        return f"❌ edit: {e}"

def tool_apply_patch(path: str, patch: str) -> str:
    if not _allowed("apply_patch"):
        return "❌ запрещён"
    try:
        p = _resolve(path)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
            f.write(patch)
            pf = f.name
        r = subprocess.run(["patch", str(p), pf], capture_output=True, text=True, timeout=30)
        os.unlink(pf)
        return f"✅ Патч применён: {p}" if r.returncode == 0 else f"❌ {r.stderr[:500]}"
    except Exception as e:
        return f"❌ apply_patch: {e}"

def tool_ls(path: str = ".", pattern: str = "*", recursive: bool = False) -> str:
    if not _allowed("read"):
        return "❌ запрещён"
    try:
        p = _resolve(path)
        if not p.exists():
            return f"❌ Не найдено: {path}"
        items = list(p.rglob(pattern) if recursive else p.glob(pattern))[:200]
        lines = [f"{'📂' if i.is_dir() else '📄'} {i.relative_to(p) if p.is_dir() else i}"
                 f"{'/' if i.is_dir() else f' ({_sz(i.stat().st_size)})'}"
                 for i in sorted(items)]
        return f"📁 {p} ({len(lines)} items)\n\n" + "\n".join(lines)
    except Exception as e:
        return f"❌ ls: {e}"

def tool_grep(pattern: str, path: str = ".", recursive: bool = True) -> str:
    try:
        p = _resolve(path)
        results = []
        files = list(p.rglob("*") if recursive else p.glob("*"))
        for f in files[:500]:
            if f.is_file() and f.stat().st_size < 2 * 1024 * 1024:
                try:
                    for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                        if re.search(pattern, line, re.IGNORECASE):
                            rel = str(f.relative_to(p)) if p.is_dir() else f.name
                            results.append(f"<code>{rel}:{i}</code>: {line.strip()[:120]}")
                            if len(results) >= 60:
                                break
                except:
                    pass
            if len(results) >= 60:
                break
        return (f"🔍 {len(results)} совпадений:\n\n" + "\n".join(results)) if results else f"🔍 Ничего: {pattern}"
    except Exception as e:
        return f"❌ grep: {e}"

def tool_find(pattern: str, path: str = ".", file_type: str = "any") -> str:
    try:
        p = _resolve(path)
        results = []
        for item in p.rglob(pattern):
            if file_type == "file" and not item.is_file():
                continue
            if file_type == "dir" and not item.is_dir():
                continue
            results.append(f"{'📄' if item.is_file() else '📂'} {item}")
            if len(results) >= 80:
                break
        return f"🔍 {len(results)} найдено:\n" + "\n".join(results) if results else f"🔍 Ничего: {pattern}"
    except Exception as e:
        return f"❌ find: {e}"

def tool_delete(path: str) -> str:
    if not _allowed("write"):
        return "❌ запрещён"
    try:
        p = _resolve(path)
        if not p.exists():
            return f"❌ Не найдено: {path}"
        if p.is_dir():
            shutil.rmtree(p)
            return f"✅ Папка удалена: {p}"
        p.unlink()
        return f"✅ Файл удалён: {p}"
    except Exception as e:
        return f"❌ delete: {e}"

def tool_move(src: str, dst: str) -> str:
    try:
        s, d = _resolve(src), _resolve(dst)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s), str(d))
        return f"✅ {s} → {d}"
    except Exception as e:
        return f"❌ move: {e}"

def tool_copy(src: str, dst: str) -> str:
    try:
        s, d = _resolve(src), _resolve(dst)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(s), str(d)) if s.is_dir() else shutil.copy2(str(s), str(d))
        return f"✅ Скопировано: {s} → {d}"
    except Exception as e:
        return f"❌ copy: {e}"

# ═══════════════════════════════════════════════════════════════════════════
#  ИНСТРУМЕНТЫ — group:runtime
# ═══════════════════════════════════════════════════════════════════════════
def tool_exec(cmd: str, workdir: str = None, timeout: int = 60,
              background: bool = False, shell: str = "auto") -> dict:
    if not _allowed("exec"):
        return {"error": "tool:exec запрещён", "status": "denied"}
    wd = _resolve(workdir) if workdir else WORKSPACE
    if not wd.exists():
        wd = Path.home()
    if background:
        sid = hashlib.md5(f"{cmd}{time.time()}".encode()).hexdigest()[:10]
        try:
            proc = subprocess.Popen(
                ["cmd", "/c", cmd] if PLATFORM == "Windows" else cmd,
                shell=(PLATFORM != "Windows"), cwd=str(wd),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE, text=True, encoding="utf-8", errors="replace"
            )
            _bg_procs[sid] = {"proc": proc, "cmd": cmd, "pid": proc.pid,
                               "output": "", "started": time.time()}
            return {"status": "running", "session_id": sid, "pid": proc.pid}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    t0 = time.time()
    try:
        if PLATFORM == "Windows":
            full = ["powershell", "-Command", cmd] if shell == "powershell" else ["cmd", "/c", cmd]
            r = subprocess.run(full, capture_output=True, text=True, timeout=timeout,
                               cwd=str(wd), encoding="utf-8", errors="replace")
        else:
            sh = {"bash": "bash", "zsh": "zsh", "sh": "sh"}.get(shell, os.environ.get("SHELL", "bash"))
            r = subprocess.run([sh, "-c", cmd], capture_output=True, text=True, timeout=timeout,
                               cwd=str(wd), encoding="utf-8", errors="replace")
        return {
            "status": "done", "stdout": r.stdout[:6000], "stderr": r.stderr[:2000],
            "returncode": r.returncode, "duration": round(time.time() - t0, 2)
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "stdout": "", "stderr": f"Timeout {timeout}s", "returncode": -1}
    except Exception as e:
        return {"status": "error", "stdout": "", "stderr": str(e), "returncode": -1}

def tool_bash(code: str, workdir: str = None, timeout: int = 60) -> dict:
    return tool_exec(code, workdir=workdir, timeout=timeout, shell="bash")

def tool_process(session_id: str, action: str = "poll", keys: str = None) -> dict:
    if session_id not in _bg_procs:
        return {"error": f"Нет процесса: {session_id}"}
    s = _bg_procs[session_id]
    proc = s["proc"]
    rc = proc.poll()
    if rc is None:
        try:
            import select
            if hasattr(select, 'select'):
                rdy = select.select([proc.stdout], [], [], 0.1)[0]
                if rdy:
                    s["output"] += proc.stdout.read(4096) or ""
        except:
            pass
    else:
        try:
            out, _ = proc.communicate(timeout=0.5)
            s["output"] += out or ""
        except:
            pass
    if action == "kill":
        proc.kill()
        del _bg_procs[session_id]
        return {"status": "killed"}
    elif action == "send-keys" and keys:
        try:
            proc.stdin.write(keys + "\n")
            proc.stdin.flush()
            return {"status": "sent"}
        except Exception as e:
            return {"error": str(e)}
    return {
        "status": "done" if rc is not None else "running",
        "session_id": session_id, "pid": s["pid"], "cmd": s["cmd"],
        "returncode": rc, "output": s["output"][-5000:],
        "elapsed": round(time.time() - s["started"], 1)
    }

def tool_run_code(code: str, lang: str = "python", timeout: int = 30) -> str:
    ext = {"python": ".py", "python3": ".py", "js": ".js", "node": ".js",
           "bash": ".sh", "ruby": ".rb", "powershell": ".ps1"}.get(lang, ".py")
    interp = {
        "python": sys.executable, "python3": sys.executable,
        "node": shutil.which("node") or "node",
        "js":   shutil.which("node") or "node",
        "bash": shutil.which("bash") or "bash",
        "ruby": shutil.which("ruby") or "ruby",
        "powershell": "powershell",
    }.get(lang, sys.executable)
    with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False, encoding="utf-8") as f:
        f.write(code)
        fn = f.name
    try:
        r = subprocess.run([interp, fn], capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        return r.stdout[:5000] or r.stderr[:2000] or "(нет вывода)"
    except subprocess.TimeoutExpired:
        return f"⏱ Timeout {timeout}s"
    except Exception as e:
        return f"❌ {e}"
    finally:
        try:
            os.unlink(fn)
        except:
            pass

# ═══════════════════════════════════════════════════════════════════════════
#  ИНСТРУМЕНТЫ — group:web
# ═══════════════════════════════════════════════════════════════════════════
def _ensure_playwright() -> bool:
    global _browser_page
    if _browser_page:
        return True
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True,
                                      args=["--no-sandbox", "--disable-dev-shm-usage"])
        _browser_page = browser.new_page()
        _browser_page.set_default_timeout(20000)
        log.info("✅ Playwright запущен")
        return True
    except Exception as e:
        log.warning(f"Playwright: {e}")
        return False

def tool_web_search(query: str) -> str:
    if not _allowed("web_search"):
        return "❌ запрещён"
    try:
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 NEXUM/10"})
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', r.text, re.DOTALL)
        titles   = re.findall(r'class="result__a"[^>]*>(.*?)</a>',       r.text, re.DOTALL)
        urls_raw = re.findall(r'class="result__url"[^>]*>(.*?)</a>',     r.text, re.DOTALL)
        results = []
        for t, s, u in zip(titles[:6], snippets[:6], urls_raw[:6]):
            tc = re.sub(r'<[^>]+>', '', t).strip()
            sc = re.sub(r'<[^>]+>', '', s).strip()
            uc = re.sub(r'<[^>]+>', '', u).strip()
            results.append(f"• <b>{tc}</b>\n  {sc}\n  {uc}")
        return "🔍 <b>Результаты:</b>\n\n" + "\n\n".join(results) if results else "🔍 Ничего не найдено"
    except Exception as e:
        return f"❌ web_search: {e}"

def tool_web_fetch(url: str, selector: str = None) -> str:
    if not _allowed("web_fetch"):
        return "❌ запрещён"
    if _ensure_playwright() and _browser_page:
        try:
            _browser_page.goto(url, wait_until="domcontentloaded", timeout=20000)
            if selector:
                el = _browser_page.query_selector(selector)
                text = el.inner_text() if el else ""
            else:
                text = _browser_page.evaluate("()=>document.body.innerText")
            lines = [l.strip() for l in (text or "").splitlines() if l.strip()][:150]
            return f"🌐 {url}\n\n" + "\n".join(lines)
        except:
            pass
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 NEXUM/10"})
        text = re.sub(r'<[^>]+>', '', r.text)
        text = re.sub(r'\s+', ' ', text).strip()
        return f"🌐 {url}\n\n{text[:5000]}"
    except Exception as e:
        return f"❌ web_fetch: {e}"

def tool_browser(action: str, **params) -> str:
    if not _allowed("browser"):
        return "❌ запрещён"
    if not _ensure_playwright():
        return "❌ Playwright не установлен:\npip install playwright && playwright install chromium"
    p = _browser_page
    try:
        if action == "navigate":
            url = params.get("url", "")
            if not url.startswith("http"):
                url = "https://" + url
            p.goto(url, wait_until="domcontentloaded", timeout=20000)
            return f"✅ Открыто: {p.title()}\n{url}"
        elif action == "click":
            sel = params.get("selector")
            x, y = params.get("x"), params.get("y")
            if sel:
                p.click(sel)
            elif x and y:
                p.mouse.click(int(x), int(y))
            return f"✅ Клик: {sel or f'({x},{y})'}"
        elif action == "type":
            sel = params.get("selector")
            text = params.get("text", "")
            if sel:
                p.fill(sel, text)
            else:
                p.keyboard.type(text)
            return f"✅ Набрано: {text[:60]}"
        elif action == "press":
            p.keyboard.press(params.get("key", ""))
            return f"✅ Нажато: {params.get('key')}"
        elif action in ["screenshot", "screen"]:
            return f"SCREENSHOT:{base64.b64encode(p.screenshot()).decode()}"
        elif action in ["snapshot", "content", "text"]:
            text = p.evaluate("()=>document.body.innerText")
            lines = [l.strip() for l in (text or "").splitlines() if l.strip()][:100]
            return f"🌐 {p.title()}\n{p.url}\n\n" + "\n".join(lines)
        elif action == "evaluate":
            result = p.evaluate(params.get("fn", "()=>null"))
            return f"✅ JS: {json.dumps(result, ensure_ascii=False)[:2000]}"
        elif action == "pdf":
            return f"PDF:{base64.b64encode(p.pdf()).decode()}"
        elif action == "scroll":
            p.mouse.wheel(0, params.get("delta_y", 300))
            return "✅ Прокрутка"
        elif action == "hover":
            p.hover(params.get("selector", ""))
            return "✅ Hover"
        elif action == "wait":
            p.wait_for_selector(params.get("selector", ""),
                                timeout=params.get("timeout", 5000))
            return "✅ Найдено"
        elif action == "url":   return p.url
        elif action == "title": return p.title()
        return f"❌ browser: {action}"
    except Exception as e:
        return f"❌ browser.{action}: {e}"

# ═══════════════════════════════════════════════════════════════════════════
#  ИНСТРУМЕНТЫ — group:nodes
# ═══════════════════════════════════════════════════════════════════════════
def tool_nodes(action: str = "info", **params) -> str:
    if not _allowed("nodes"):
        return "❌ запрещён"
    if action == "info":
        return _nodes_info()
    elif action == "screenshot":
        data = _take_screenshot()
        return f"SCREENSHOT:{base64.b64encode(data).decode()}" if data else "❌ Скриншот не удался"
    elif action == "processes":
        filt = params.get("filter", "")
        procs = sorted(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                       key=lambda x: x.info.get("cpu_percent") or 0, reverse=True)
        lines = [
            f"[{p.info['pid']}] {p.info['name'][:28]}"
            f" CPU:{p.info.get('cpu_percent',0):.1f}%"
            f" MEM:{p.info.get('memory_percent',0):.1f}%"
            for p in procs[:30]
            if not filt or filt.lower() in p.info["name"].lower()
        ]
        return "⚙️ Процессы:\n\n" + "\n".join(lines[:25])
    elif action == "kill":
        target = params.get("target", "")
        try:
            if str(target).isdigit():
                proc = psutil.Process(int(target))
                name = proc.name()
                proc.kill()
                return f"✅ Завершён: {name} (PID {target})"
            killed = []
            for proc in psutil.process_iter(["pid", "name"]):
                if target.lower() in proc.info["name"].lower():
                    proc.kill()
                    killed.append(f"{proc.info['name']}({proc.info['pid']})")
            return f"✅ {', '.join(killed)}" if killed else f"⚠️ Не найдено: {target}"
        except Exception as e:
            return f"❌ {e}"
    elif action == "network":
        net = psutil.net_io_counters()
        lines = [f"↓{_sz(net.bytes_recv)} ↑{_sz(net.bytes_sent)}\n"]
        for c in psutil.net_connections()[:15]:
            if c.status == "ESTABLISHED":
                lines.append(f"  {c.laddr} → {c.raddr}")
        return "\n".join(lines)
    elif action == "run":
        return json.dumps(tool_exec(params.get("command", ""), timeout=params.get("timeout", 30)))
    return f"❌ nodes: {action}"

def _nodes_info() -> str:
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    try:
        disk = psutil.disk_usage("C:\\" if PLATFORM == "Windows" else "/")
        disk_s = f"{disk.percent}% ({_sz(disk.used)}/{_sz(disk.total)})"
    except:
        disk_s = "N/A"
    net = psutil.net_io_counters()
    bat = ""
    try:
        b = psutil.sensors_battery()
        if b:
            bat = f"\n🔋 {b.percent:.0f}% {'🔌' if b.power_plugged else '🔋'}"
    except:
        pass
    ext_ip = ""
    try:
        ext_ip = f"\n🌍 {requests.get('https://api.ipify.org', timeout=3).text}"
    except:
        pass
    procs = sorted(psutil.process_iter(["name", "cpu_percent", "memory_percent"]),
                   key=lambda x: x.info.get("cpu_percent") or 0, reverse=True)[:5]
    top = "\n".join(
        f"  {p.info['name'][:24]} CPU:{p.info.get('cpu_percent',0):.1f}%"
        f" MEM:{p.info.get('memory_percent',0):.1f}%"
        for p in procs
    )
    return (f"🖥 <b>{platform.node()}</b> | {PLATFORM} {platform.release()}\n"
            f"⚡ CPU: {cpu}% ({psutil.cpu_count()}c)\n"
            f"🧠 RAM: {mem.percent}% ({_sz(mem.used)}/{_sz(mem.total)})\n"
            f"💾 Disk: {disk_s}\n"
            f"🌐 Net: ↓{_sz(net.bytes_recv)} ↑{_sz(net.bytes_sent)}{bat}{ext_ip}\n"
            f"📊 Топ процессы:\n{top}\n"
            f"🤖 NEXUM Node v{VERSION} | ⏱ {str(datetime.now()-_session_start).split('.')[0]}")

def _take_screenshot() -> Optional[bytes]:
    if HAS_GUI and HAS_PIL:
        try:
            import io
            img = pyautogui.screenshot()
            buf = io.BytesIO()
            img.save(buf, "PNG")
            return buf.getvalue()
        except:
            pass
    if HAS_PIL:
        try:
            import io
            from PIL import ImageGrab
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, "PNG")
            return buf.getvalue()
        except:
            pass
    if PLATFORM == "Linux":
        for cmd in [["scrot", "-"], ["import", "-window", "root", "-"]]:
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=5)
                if r.returncode == 0 and r.stdout:
                    return r.stdout
            except:
                pass
    elif PLATFORM == "Darwin":
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            fn = f.name
        if subprocess.run(["screencapture", "-x", fn], timeout=5).returncode == 0:
            data = Path(fn).read_bytes()
            os.unlink(fn)
            return data
    return None

# ═══════════════════════════════════════════════════════════════════════════
#  ИНСТРУМЕНТЫ — group:canvas
# ═══════════════════════════════════════════════════════════════════════════
def tool_canvas(action: str, **params) -> str:
    if not HAS_GUI:
        return "❌ pyautogui не установлен. pip install pyautogui"
    try:
        if action == "type":
            pyautogui.typewrite(params.get("text", ""), interval=0.03)
            return f"✅ Набрано: {str(params.get('text',''))[:60]}"
        elif action == "key":
            key = params.get("key", "")
            keys = [k.strip() for k in key.split("+")]
            if len(keys) > 1:
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(key)
            return f"✅ Нажато: {key}"
        elif action == "click":
            x, y = params.get("x"), params.get("y")
            btn = params.get("button", "left")
            if x is not None:
                pyautogui.click(int(x), int(y), button=btn)
            else:
                pyautogui.click(button=btn)
            return f"✅ Клик ({btn})" + (f" @ ({x},{y})" if x else "")
        elif action == "move":
            pyautogui.moveTo(int(params.get("x", 0)), int(params.get("y", 0)), duration=0.3)
            return f"✅ Курсор → ({params.get('x')},{params.get('y')})"
        elif action == "scroll":
            pyautogui.scroll(int(params.get("clicks", 3)))
            return "✅ Прокрутка"
        elif action == "screenshot":
            data = _take_screenshot()
            return f"SCREENSHOT:{base64.b64encode(data).decode()}" if data else "❌ Нет скриншота"
        elif action == "position":
            pos = pyautogui.position()
            return f"📍 Курсор: ({pos.x},{pos.y})"
        elif action == "size":
            sz = pyautogui.size()
            return f"🖥 Экран: {sz.width}×{sz.height}"
        return f"❌ canvas: {action}"
    except Exception as e:
        return f"❌ canvas.{action}: {e}"

# ═══════════════════════════════════════════════════════════════════════════
#  ИНСТРУМЕНТЫ — group:cron
# ═══════════════════════════════════════════════════════════════════════════
_scheduler   = BackgroundScheduler(timezone="UTC")
_cron_chatid = OWNER_ID

def _parse_schedule(s: str):
    s = s.strip()
    m = re.match(r'in\s+(\d+)\s*(s|sec|m|min|h|hour|d|day)', s, re.I)
    if m:
        n, u = int(m.group(1)), m.group(2).lower()
        secs = {"s":1,"sec":1,"m":60,"min":60,"h":3600,"hour":3600,"d":86400,"day":86400}[u] * n
        return DateTrigger(run_date=datetime.utcnow() + timedelta(seconds=secs))
    m2 = re.match(r'every\s+(\d+)?\s*(s|sec|m|min|h|hour|d|day)', s, re.I)
    if m2:
        n = int(m2.group(1) or 1)
        u = m2.group(2).lower()
        secs = {"s":1,"sec":1,"m":60,"min":60,"h":3600,"hour":3600,"d":86400,"day":86400}[u] * n
        return IntervalTrigger(seconds=secs)
    named = {
        "daily": IntervalTrigger(hours=24), "hourly": IntervalTrigger(hours=1),
        "weekly": IntervalTrigger(weeks=1), "minutely": IntervalTrigger(minutes=1),
    }
    if s.lower() in named:
        return named[s.lower()]
    try:
        return CronTrigger.from_crontab(s)
    except:
        pass
    m3 = re.match(r'через\s+(\d+)\s*(минут|час|сек)', s, re.I)
    if m3:
        n = int(m3.group(1))
        u = m3.group(2).lower()
        secs = {"минут": 60, "час": 3600, "сек": 1}[u] * n
        return DateTrigger(run_date=datetime.utcnow() + timedelta(seconds=secs))
    return None

def tool_cron(action: str, **params) -> str:
    if not _allowed("cron"):
        return "❌ запрещён"
    if action == "add":
        label    = params.get("label", "job")
        schedule = params.get("schedule", "daily")
        prompt   = params.get("prompt", "")
        da       = params.get("delete_after", False)
        job_id   = hashlib.md5(f"{label}{time.time()}".encode()).hexdigest()[:10]
        trigger  = _parse_schedule(schedule)
        if not trigger:
            return f"❌ Неверное расписание: {schedule}"

        def _fire(lbl=label, pr=prompt, jid=job_id, da2=da):
            try:
                result = _cron_exec(pr)
                if result and result.strip() not in ("OK", "HEARTBEAT_OK", ""):
                    send(_cron_chatid, f"⏰ <b>Крон: {lbl}</b>\n\n{result}", parse="HTML")
                if da2:
                    try:
                        _scheduler.remove_job(jid)
                    except:
                        pass
                    with _db() as c:
                        c.execute("UPDATE cron_jobs SET active=0 WHERE id=?", (jid,))
            except Exception as e:
                log.error(f"Cron {lbl}: {e}")

        _scheduler.add_job(_fire, trigger, id=job_id, replace_existing=True)
        with _db() as c:
            c.execute("INSERT OR REPLACE INTO cron_jobs(id,label,schedule,prompt,delete_after) VALUES(?,?,?,?,?)",
                      (job_id, label, schedule, prompt, 1 if da else 0))
        return f"✅ Крон: <b>{label}</b>\n⏰ {schedule}\n🆔 {job_id}"
    elif action == "list":
        with _db() as c:
            rows = c.execute("SELECT id,label,schedule,active FROM cron_jobs ORDER BY ts DESC").fetchall()
        if not rows:
            return "📅 Нет задач"
        lines = ["📅 <b>Крон:</b>\n"]
        for r in rows:
            lines.append(f"{'🟢' if r['active'] else '🔴'} [{r['id'][:6]}] <b>{r['label']}</b> — {r['schedule']}")
        return "\n".join(lines)
    elif action == "delete":
        jid = params.get("job_id", "")
        try:
            _scheduler.remove_job(jid)
        except:
            pass
        with _db() as c:
            c.execute("DELETE FROM cron_jobs WHERE id=?", (jid,))
        return f"✅ Удалено: {jid}"
    elif action == "run":
        return _cron_exec(params.get("prompt", ""))
    return f"❌ cron: {action}"

def _cron_exec(prompt: str) -> str:
    if prompt.startswith("$") or prompt.startswith("!"):
        r = tool_exec(prompt.lstrip("$! ").strip(), timeout=120)
        return r.get("stdout", "") or r.get("stderr", "") or "OK"
    return prompt

# ═══════════════════════════════════════════════════════════════════════════
#  ИНСТРУМЕНТЫ — group:memory
# ═══════════════════════════════════════════════════════════════════════════
def tool_memory(action: str, **params) -> str:
    if action in ("read", "get"):
        return MEMORY_FILE.read_text(encoding="utf-8") if MEMORY_FILE.exists() else "(MEMORY.md пуст)"
    elif action in ("write", "memory_write"):
        content = params.get("content", "")
        if params.get("append", True) and MEMORY_FILE.exists():
            existing = MEMORY_FILE.read_text(encoding="utf-8")
            MEMORY_FILE.write_text(
                existing + f"\n\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{content}",
                encoding="utf-8"
            )
        else:
            MEMORY_FILE.write_text(content, encoding="utf-8")
        return "✅ MEMORY.md обновлён"
    elif action in ("search", "memory_search"):
        q = params.get("query", "")
        if not MEMORY_FILE.exists():
            return "(память пуста)"
        lines = MEMORY_FILE.read_text(encoding="utf-8").splitlines()
        q_words = set(q.lower().split())
        results = []
        for i, line in enumerate(lines):
            if any(w in line.lower() for w in q_words if len(w) > 2):
                ctx = "\n".join(lines[max(0, i-1):min(len(lines), i+3)])
                results.append(ctx)
        return "🧠 Из памяти:\n\n" + "\n---\n".join(results[:5]) if results else f"🔍 Не найдено: {q}"
    elif action == "clear":
        MEMORY_FILE.write_text("", encoding="utf-8")
        return "✅ Память очищена"
    return f"❌ memory: {action}"

# ═══════════════════════════════════════════════════════════════════════════
#  ИНСТРУМЕНТЫ — group:sessions
# ═══════════════════════════════════════════════════════════════════════════
def tool_sessions_spawn(agent_id: str, prompt: str) -> dict:
    if not _allowed("sessions_spawn"):
        return {"error": "запрещён"}
    sid = f"sub:{agent_id}:{hashlib.md5(f'{prompt}{time.time()}'.encode()).hexdigest()[:8]}"
    _sub_sessions[sid] = {"status": "running", "prompt": prompt, "result": "", "started": time.time()}

    def _run():
        try:
            result = _agent_loop(prompt, max_steps=10, chat_id=None)
            _sub_sessions[sid]["status"] = "done"
            _sub_sessions[sid]["result"] = result
        except Exception as e:
            _sub_sessions[sid]["status"] = "error"
            _sub_sessions[sid]["result"] = str(e)

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "accepted", "session_id": sid}

def tool_sessions_list() -> str:
    if not _sub_sessions:
        return "📋 Нет активных сессий"
    lines = ["📋 Сессии:\n"]
    for sid, s in list(_sub_sessions.items()):
        lines.append(f"• {sid[:30]} [{s['status']}] {round(time.time()-s['started'])}s")
    return "\n".join(lines)

def tool_sessions_send(session_id: str, message: str) -> str:
    if session_id not in _sub_sessions:
        return f"❌ Нет сессии: {session_id}"
    _sub_sessions[session_id].setdefault("inbox", []).append(message)
    return f"✅ Сообщение доставлено в {session_id[:20]}"

def tool_sessions_history(session_id: str) -> str:
    if session_id not in _sub_sessions:
        return f"❌ Нет сессии: {session_id}"
    s = _sub_sessions[session_id]
    return (f"📋 {session_id[:30]}\nСтатус: {s['status']}\n"
            f"Промпт: {s['prompt'][:200]}\nРезультат: {s.get('result','...')[:500]}\n"
            f"Время: {round(time.time()-s['started'])}s")

# ═══════════════════════════════════════════════════════════════════════════
#  ИНСТРУМЕНТЫ — group:skills
# ═══════════════════════════════════════════════════════════════════════════
_SKILL_TEMPLATES = {
    "git":        "# Git\n$ git status\n$ git add -A && git commit -m \"{task}\"\n$ git push\n$ git log --oneline -10\n",
    "python-env": "# Python Venv\n$ python -m venv .venv\n$ source .venv/bin/activate\n$ pip install -r requirements.txt\n",
    "docker":     "# Docker\n$ docker ps -a\n$ docker build -t {task} .\n$ docker run -d --name {task} {image}\n$ docker logs {task} --tail 50\n",
    "backup":     "# Backup\n$ tar -czf backup_$(date +%Y%m%d).tar.gz {task}\n",
    "monitor":    "# Monitor\n$ top -bn1 | head -20\n$ df -h\n$ ss -tuln\n$ journalctl -p err --since \"1h ago\"\n",
    "web-scraper":"# Web Scraper\n## Используй browser: navigate → snapshot → extract\n$ curl -s {url} | python -m json.tool\n",
    "nginx":      "# Nginx\n$ nginx -t\n$ systemctl restart nginx\n$ tail -f /var/log/nginx/error.log\n",
    "deploy":     "# Deploy\n$ git pull origin main\n$ pip install -r requirements.txt\n$ systemctl restart {service}\n",
}

def tool_skills_list() -> str:
    skills = list(SKILLS_DIR.glob("*/SKILL.md")) + list(SKILLS_DIR.glob("*.md"))
    if not skills:
        return "🧬 Нет скиллов.\nУстанови: /skill install git"
    lines = ["🧬 <b>Скиллы:</b>\n"]
    for s in skills:
        name = s.parent.name if s.name == "SKILL.md" else s.stem
        first = s.read_text(encoding="utf-8", errors="ignore").splitlines()[0][:80] if s.stat().st_size > 0 else ""
        lines.append(f"• <b>{name}</b> — {first}")
    return "\n".join(lines)

def tool_skill_read(name: str) -> str:
    for p in [SKILLS_DIR/name/"SKILL.md", SKILLS_DIR/f"{name}.md"]:
        if p.exists():
            return p.read_text(encoding="utf-8")
    return f"❌ Скилл не найден: {name}"

def tool_skill_write(name: str, content: str) -> str:
    p = SKILLS_DIR / name / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"✅ Скилл сохранён: {name}"

def tool_skill_search(query: str) -> str:
    q = query.lower()
    results = []
    for name, tmpl in _SKILL_TEMPLATES.items():
        if q in name or q in tmpl.lower():
            results.append(f"🌐 <b>{name}</b> (шаблон)\n{tmpl.splitlines()[0]}")
    for s in SKILLS_DIR.glob("*/SKILL.md"):
        name = s.parent.name
        content = s.read_text(encoding="utf-8", errors="ignore")[:200]
        if q in name.lower() or q in content.lower():
            results.append(f"📦 <b>{name}</b> (local)\n{content.splitlines()[0][:80] if content else ''}")
    return ("🔍 Найдено:\n\n" + "\n\n".join(results[:8])) if results else (
        f"🔍 Ничего: {query}\nДоступные шаблоны: {', '.join(_SKILL_TEMPLATES.keys())}"
    )

def tool_skill_install(name: str) -> str:
    if name not in _SKILL_TEMPLATES:
        return f"❌ Нет шаблона '{name}'.\nДоступные: {', '.join(_SKILL_TEMPLATES.keys())}"
    p = SKILLS_DIR / name / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_SKILL_TEMPLATES[name], encoding="utf-8")
    return f"✅ Скилл установлен: <b>{name}</b>\n📁 {p}"

def _get_relevant_skills(query: str) -> str:
    skills = list(SKILLS_DIR.glob("*/SKILL.md")) + list(SKILLS_DIR.glob("*.md"))
    q_words = set(query.lower().split())
    relevant = []
    for s in skills:
        name = s.parent.name if s.name == "SKILL.md" else s.stem
        if any(w in name.lower() for w in q_words if len(w) > 3):
            content = s.read_text(encoding="utf-8", errors="ignore")[:300]
            relevant.append(f"[skill:{name}]\n{content}")
    return "\n\n".join(relevant[:2])

# ── Misc tools ──────────────────────────────────────────────────────────────
def tool_notify(title: str, message: str) -> str:
    try:
        if PLATFORM == "Windows":
            ps_cmd = f'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show("{message}","{title}")'
            tool_exec(f'powershell -Command "{ps_cmd}"', shell="powershell")
        elif PLATFORM == "Darwin":
            tool_exec(f'osascript -e \'display notification "{message}" with title "{title}"\'')
        else:
            tool_exec(f'notify-send "{title}" "{message}"')
        return f"✅ Уведомление: {title}"
    except Exception as e:
        return f"❌ {e}"

def tool_clipboard(action: str = "get", text: str = "") -> str:
    if action == "get":
        if HAS_CLIP:
            try:
                return pyperclip.paste() or "(пусто)"
            except:
                pass
        if PLATFORM == "Windows":
            r = tool_exec("powershell Get-Clipboard", shell="powershell")
            return r.get("stdout", "").strip() or "(пусто)"
        elif PLATFORM == "Darwin":
            r = tool_exec("pbpaste")
            return r.get("stdout", "").strip() or "(пусто)"
    elif action == "set":
        if HAS_CLIP:
            try:
                pyperclip.copy(text)
                return f"✅ Скопировано: {text[:60]}"
            except:
                pass
        if PLATFORM == "Windows":
            tool_exec(f'powershell Set-Clipboard -Value "{text}"', shell="powershell")
        elif PLATFORM == "Darwin":
            subprocess.run(["pbcopy"], input=text.encode(), timeout=5)
        return "✅ Скопировано"
    return "❌ Укажи action=get или set"

def tool_location() -> str:
    try:
        r = requests.get("https://ipapi.co/json/", timeout=5).json()
        return (f"📍 {r.get('city','?')}, {r.get('country_name','?')}\n"
                f"IP: {r.get('ip','?')}\n"
                f"Lat: {r.get('latitude','?')}, Lon: {r.get('longitude','?')}")
    except Exception as e:
        return f"❌ location: {e}"


# ═══════════════════════════════════════════════════════════════════════════
#  EMAIL — отправка/чтение
# ═══════════════════════════════════════════════════════════════════════════
def tool_email(action: str, **params) -> str:
    import smtplib, imaplib, email as emaillib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    smtp_user = os.getenv("SMTP_USER",""); smtp_pass = os.getenv("SMTP_PASS","")
    smtp_host = os.getenv("SMTP_HOST","smtp.gmail.com"); smtp_port = int(os.getenv("SMTP_PORT","587"))
    if action == "send":
        if not smtp_user or not smtp_pass:
            return "❌ Email не настроен. Добавь SMTP_USER и SMTP_PASS в .env\nApp Password: myaccount.google.com → Безопасность → Пароли приложений"
        to = params.get("to",""); subject = params.get("subject","Письмо от NEXUM"); body = params.get("body","")
        if not to: return "❌ Укажи получателя: to=email@example.com"
        try:
            msg = MIMEMultipart(); msg["From"]=smtp_user; msg["To"]=to; msg["Subject"]=subject
            msg.attach(MIMEText(body,"plain","utf-8"))
            with smtplib.SMTP(smtp_host,smtp_port,timeout=15) as srv:
                srv.starttls(); srv.login(smtp_user,smtp_pass); srv.send_message(msg)
            return f"✅ Письмо отправлено → {to}\n📧 Тема: {subject}"
        except Exception as e: return f"❌ Ошибка отправки: {e}"
    elif action == "read":
        if not smtp_user or not smtp_pass: return "❌ Email не настроен."
        count = int(params.get("count",5))
        try:
            imap_host = os.getenv("IMAP_HOST","imap.gmail.com")
            with imaplib.IMAP4_SSL(imap_host) as imap:
                imap.login(smtp_user,smtp_pass); imap.select("INBOX")
                _,msgs = imap.search(None,"ALL"); ids = msgs[0].split()[-count:]
                result = []
                for mid in reversed(ids):
                    _,data = imap.fetch(mid,"(RFC822)")
                    msg = emaillib.message_from_bytes(data[0][1])
                    body_text = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type()=="text/plain":
                                body_text = part.get_payload(decode=True).decode("utf-8","ignore")[:300]; break
                    else:
                        body_text = msg.get_payload(decode=True).decode("utf-8","ignore")[:300]
                    result.append(f"📧 От: {msg.get('From','?')}\n📌 {msg.get('Subject','?')}\n{body_text}\n{'─'*30}")
            return "\n".join(result) or "📭 Нет писем"
        except Exception as e: return f"❌ {e}"
    elif action == "search":
        if not smtp_user or not smtp_pass: return "❌ Email не настроен."
        query = params.get("query","")
        try:
            with imaplib.IMAP4_SSL(os.getenv("IMAP_HOST","imap.gmail.com")) as imap:
                imap.login(smtp_user,smtp_pass); imap.select("INBOX")
                _,msgs = imap.search(None,f'SUBJECT "{query}"'); ids = msgs[0].split()[-10:]
                result = []
                for mid in reversed(ids):
                    _,data = imap.fetch(mid,"(RFC822)")
                    msg = emaillib.message_from_bytes(data[0][1])
                    result.append(f"📧 {msg.get('From','?')} | {msg.get('Subject','?')} | {msg.get('Date','?')}")
            return "\n".join(result) or f"📭 Писем с '{query}' не найдено"
        except Exception as e: return f"❌ {e}"
    return "❌ action: send / read / search"


# ═══════════════════════════════════════════════════════════════════════════
#  CALENDAR — локальный календарь
# ═══════════════════════════════════════════════════════════════════════════
_CAL_FILE = os.path.join(os.path.expanduser("~"), ".nexum_calendar.json")
def _cal_load():
    try:
        with open(_CAL_FILE) as f: return json.load(f)
    except: return []
def _cal_save(ev):
    with open(_CAL_FILE,"w") as f: json.dump(ev,f,ensure_ascii=False,indent=2)

def tool_calendar(action: str, **params) -> str:
    events = _cal_load()
    if action == "add":
        title=params.get("title","Событие"); date=params.get("date",""); time_=params.get("time",""); note=params.get("note","")
        if not date: return "❌ Укажи дату: date=2026-03-15"
        event={"id":str(int(time.time())),"title":title,"date":date,"time":time_,"note":note,"created":datetime.now().isoformat()}
        events.append(event); _cal_save(events)
        return f"✅ Добавлено: {title} | {date} {time_}"
    elif action == "list":
        df=params.get("date","")
        res=[f"📅 {e['date']} {e.get('time','')} — {e['title']}" + (f"\n   {e['note']}" if e.get("note") else "") for e in sorted(events,key=lambda x:x.get("date","")) if not df or e["date"].startswith(df)]
        return "\n".join(res) or "📭 Событий нет"
    elif action == "today":
        today=datetime.now().strftime("%Y-%m-%d")
        res=[e for e in events if e.get("date")==today]
        return "\n".join(f"⏰ {e.get('time','')} — {e['title']}" for e in res) or f"📅 Сегодня событий нет"
    elif action == "week":
        from datetime import timedelta
        today=datetime.now(); dates=[(today+timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        res=[e for e in events if e.get("date","") in dates]
        return "\n".join(f"📅 {e['date']} {e.get('time','')} — {e['title']}" for e in sorted(res,key=lambda x:x.get("date",""))) or "📅 На неделе событий нет"
    elif action == "delete":
        eid=params.get("id",""); ttl=params.get("title","")
        before=len(events); events=[e for e in events if e.get("id")!=eid and e.get("title")!=ttl]
        _cal_save(events); return f"✅ Удалено {before-len(events)} событий"
    return "❌ action: add / list / today / week / delete"


# ═══════════════════════════════════════════════════════════════════════════
#  SCREEN VISION — AI видит экран
# ═══════════════════════════════════════════════════════════════════════════
def tool_screen_vision(query: str = "Что на экране?") -> str:
    screenshot_data = _take_screenshot()
    if not screenshot_data: return "❌ Не удалось сделать скриншот"
    b64 = base64.b64encode(screenshot_data).decode()
    gemini_keys = [k for k in [os.getenv(f"G{i}","") for i in range(1,11)] if k]
    for key in gemini_keys:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}",
                json={"contents":[{"parts":[{"text":f"Проанализируй скриншот. {query} Опиши что видишь: окна, текст, кнопки."},{"inline_data":{"mime_type":"image/png","data":b64}}]}]},
                timeout=30
            )
            if r.status_code == 200:
                return f"👁 Анализ экрана:\n{r.json()['candidates'][0]['content']['parts'][0]['text']}"
        except: continue
    return "❌ Нет AI ключа для анализа экрана"


# ═══════════════════════════════════════════════════════════════════════════
#  APP CONTROL — открыть/закрыть приложения
# ═══════════════════════════════════════════════════════════════════════════
def tool_app(action: str, **params) -> str:
    app = params.get("app","")
    if action == "open":
        if not app: return "❌ Укажи app="
        app_map = {
            "telegram":{"win":"start ms-telegram:","mac":"open -a Telegram","lin":"telegram-desktop &"},
            "chrome":{"win":"start chrome","mac":"open -a 'Google Chrome'","lin":"google-chrome &"},
            "firefox":{"win":"start firefox","mac":"open -a Firefox","lin":"firefox &"},
            "vscode":{"win":"code","mac":"open -a 'Visual Studio Code'","lin":"code &"},
            "notepad":{"win":"notepad","mac":"open -a TextEdit","lin":"gedit &"},
            "explorer":{"win":"explorer .","mac":"open .","lin":"xdg-open . &"},
            "calculator":{"win":"calc","mac":"open -a Calculator","lin":"gnome-calculator &"},
            "terminal":{"win":"start cmd","mac":"open -a Terminal","lin":"x-terminal-emulator &"},
            "spotify":{"win":"start spotify:","mac":"open -a Spotify","lin":"spotify &"},
        }
        al = app.lower()
        pk = {"Windows":"win","Darwin":"mac"}.get(PLATFORM,"lin")
        cmd = app_map.get(al,{}).get(pk, app)
        result = tool_exec(cmd)
        return f"✅ Открываю {app}"
    elif action == "close":
        if PLATFORM=="Windows": tool_exec(f"taskkill /F /IM {app}.exe",shell="powershell")
        elif PLATFORM=="Darwin": tool_exec(f"pkill -f '{app}'")
        else: tool_exec(f"pkill -f '{app}'")
        return f"✅ {app} закрыт"
    elif action == "list":
        procs = []
        for p in psutil.process_iter(["pid","name"]):
            try: procs.append(f"{p.info['pid']:6d}  {p.info['name']}")
            except: pass
        return "Процессы:\n" + "\n".join(procs[:30])
    return "❌ action: open / close / list"


# ═══════════════════════════════════════════════════════════════════════════
#  VOICE — озвучка текста системным TTS
# ═══════════════════════════════════════════════════════════════════════════
def tool_voice(action: str, **params) -> str:
    text = params.get("text","")
    if action == "say":
        if not text: return "❌ Укажи text="
        try:
            if PLATFORM=="Windows":
                tool_exec(f'powershell -Command "Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Speak(\'\'{text}\'\')"\'', shell="powershell")
            elif PLATFORM=="Darwin": tool_exec(f'say "{text}"')
            else:
                if shutil.which("espeak"): tool_exec(f'espeak "{text}"')
                else: return "❌ Установи espeak: sudo apt install espeak"
            return f"✅ Озвучено: {text[:50]}"
        except Exception as e: return f"❌ {e}"
    elif action == "volume":
        level=params.get("level",50)
        if PLATFORM=="Darwin": tool_exec(f"osascript -e 'set volume output volume {level}'")
        elif PLATFORM=="Linux": tool_exec(f"amixer set Master {level}%")
        return f"✅ Громкость: {level}%"
    return "❌ action: say / volume"


# ═══════════════════════════════════════════════════════════════════════════
#  DOWNLOAD — скачать файл из интернета
# ═══════════════════════════════════════════════════════════════════════════
def tool_download(url: str, path: str = "", **params) -> str:
    if not url: return "❌ Укажи url="
    try:
        filename = path or os.path.join(WORKSPACE, url.split("/")[-1].split("?")[0] or "download")
        r = requests.get(url,stream=True,timeout=60,allow_redirects=True); r.raise_for_status()
        with open(filename,"wb") as f:
            for chunk in r.iter_content(8192): f.write(chunk)
        size_mb = os.path.getsize(filename)/1024/1024
        return f"✅ Скачано: {filename}\n📦 {size_mb:.1f} MB"
    except Exception as e: return f"❌ {e}"


# ═══════════════════════════════════════════════════════════════════════════
#  NETWORK — ping, ports, ip
# ═══════════════════════════════════════════════════════════════════════════
def tool_network(action: str, **params) -> str:
    if action == "ping":
        host=params.get("host","google.com"); count=params.get("count",4)
        flag="-n" if PLATFORM=="Windows" else "-c"
        r=tool_exec(f"ping {flag} {count} {host}")
        return r.get("stdout","") or r.get("stderr","")
    elif action == "ports":
        import socket
        host=params.get("host","localhost")
        ports=[21,22,25,53,80,443,3000,3306,5432,6379,8080,8443,27017]
        open_ports=[]
        for port in ports:
            try: s=socket.create_connection((host,port),timeout=1); s.close(); open_ports.append(port)
            except: pass
        return f"🌐 Открытые порты {host}: {open_ports}"
    elif action == "myip":
        try: return f"🌐 IP: {requests.get('https://api.ipify.org?format=json',timeout=5).json()['ip']}"
        except Exception as e: return f"❌ {e}"
    return "❌ action: ping / ports / myip"


# ═══════════════════════════════════════════════════════════════════════════
#  MONITOR — мониторинг папок
# ═══════════════════════════════════════════════════════════════════════════
_monitors: Dict[str, dict] = {}
def _send_to_telegram_notify(text: str):
    try:
        bt=os.getenv("BOT_TOKEN","")
        if bt and OWNER_ID:
            requests.post(f"https://api.telegram.org/bot{bt}/sendMessage",
                json={"chat_id":OWNER_ID,"text":text[:4000]},timeout=10)
    except: pass

def tool_monitor(action: str, **params) -> str:
    if action == "watch":
        path=params.get("path","."); label=params.get("label",path); interval=int(params.get("interval",60))
        def _check():
            snapshot={}
            while label in _monitors:
                try:
                    current={}; p=Path(path)
                    items = [p] if p.is_file() else list(p.iterdir()) if p.is_dir() else []
                    for f in items: current[str(f)]=f.stat().st_mtime
                    if snapshot:
                        added=set(current)-set(snapshot); removed=set(snapshot)-set(current)
                        changed={k for k in set(current)&set(snapshot) if current[k]!=snapshot[k]}
                        msgs=[]
                        if added: msgs.append(f"➕ {', '.join(Path(f).name for f in added)}")
                        if removed: msgs.append(f"➖ {', '.join(Path(f).name for f in removed)}")
                        if changed: msgs.append(f"✏️ {', '.join(Path(f).name for f in changed)}")
                        if msgs: _send_to_telegram_notify(f"👁 [{label}]:\n"+"\n".join(msgs))
                    snapshot=current
                except Exception as e: log.error(f"Monitor {label}: {e}")
                time.sleep(interval)
        threading.Thread(target=_check,daemon=True).start()
        _monitors[label]={"path":path,"interval":interval}
        return f"✅ Мониторинг: {path} каждые {interval}с"
    elif action == "list":
        return "\n".join(f"👁 {l}: {m['path']}" for l,m in _monitors.items()) or "📭 Нет мониторингов"
    elif action == "unwatch":
        label=params.get("label","")
        if label in _monitors: del _monitors[label]; return f"✅ Остановлен: {label}"
        return "❌ Не найден"
    return "❌ action: watch / list / unwatch"


# ═══════════════════════════════════════════════════════════════════════════
#  TELEGRAM SEND — отправка в любой чат
# ═══════════════════════════════════════════════════════════════════════════
def tool_telegram_send(action: str = "send", **params) -> str:
    bt=os.getenv("BOT_TOKEN","")
    if not bt: return "❌ BOT_TOKEN не задан"
    if action == "send":
        chat_id=params.get("chat_id",OWNER_ID); text=params.get("text","")
        if not text: return "❌ Укажи text="
        try:
            r=requests.post(f"https://api.telegram.org/bot{bt}/sendMessage",
                json={"chat_id":chat_id,"text":text,"parse_mode":"HTML"},timeout=10)
            return "✅ Отправлено" if r.ok else f"❌ {r.text}"
        except Exception as e: return f"❌ {e}"
    elif action == "send_file":
        chat_id=params.get("chat_id",OWNER_ID); path=params.get("path",""); caption=params.get("caption","")
        if not path or not os.path.exists(path): return f"❌ Файл не найден: {path}"
        try:
            with open(path,"rb") as f:
                r=requests.post(f"https://api.telegram.org/bot{bt}/sendDocument",
                    data={"chat_id":chat_id,"caption":caption},files={"document":f},timeout=60)
            return "✅ Файл отправлен" if r.ok else f"❌ {r.text}"
        except Exception as e: return f"❌ {e}"
    return "❌ action: send / send_file"


# ═══════════════════════════════════════════════════════════════════════════
#  TOOL DISPATCHER
# ═══════════════════════════════════════════════════════════════════════════
TOOLS_SCHEMA = [
    {"type":"function","function":{"name":"read","description":"Читает файл или директорию.","parameters":{"type":"object","properties":{"path":{"type":"string"},"offset":{"type":"integer"},"limit":{"type":"integer"}},"required":["path"]}}},
    {"type":"function","function":{"name":"write","description":"Записывает файл.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}},
    {"type":"function","function":{"name":"edit","description":"Заменяет фрагмент в файле.","parameters":{"type":"object","properties":{"path":{"type":"string"},"old_str":{"type":"string"},"new_str":{"type":"string"}},"required":["path","old_str","new_str"]}}},
    {"type":"function","function":{"name":"exec","description":"Выполняет shell команду.","parameters":{"type":"object","properties":{"cmd":{"type":"string"},"workdir":{"type":"string"},"timeout":{"type":"integer"},"background":{"type":"boolean"},"shell":{"type":"string","enum":["auto","bash","powershell","zsh"]}},"required":["cmd"]}}},
    {"type":"function","function":{"name":"bash","description":"Выполняет bash скрипт.","parameters":{"type":"object","properties":{"code":{"type":"string"},"workdir":{"type":"string"},"timeout":{"type":"integer"}},"required":["code"]}}},
    {"type":"function","function":{"name":"process","description":"Управляет фоновыми процессами.","parameters":{"type":"object","properties":{"session_id":{"type":"string"},"action":{"type":"string","enum":["poll","kill","send-keys"]},"keys":{"type":"string"}},"required":["session_id"]}}},
    {"type":"function","function":{"name":"ls","description":"Список файлов.","parameters":{"type":"object","properties":{"path":{"type":"string"},"pattern":{"type":"string"},"recursive":{"type":"boolean"}}}}},
    {"type":"function","function":{"name":"grep","description":"Поиск в файлах.","parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"},"recursive":{"type":"boolean"}},"required":["pattern"]}}},
    {"type":"function","function":{"name":"find","description":"Поиск файлов по маске.","parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"},"file_type":{"type":"string","enum":["any","file","dir"]}},"required":["pattern"]}}},
    {"type":"function","function":{"name":"web_search","description":"Поиск в интернете.","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}},
    {"type":"function","function":{"name":"web_fetch","description":"Получает содержимое страницы.","parameters":{"type":"object","properties":{"url":{"type":"string"},"selector":{"type":"string"}},"required":["url"]}}},
    {"type":"function","function":{"name":"browser","description":"Управление браузером Chromium.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["navigate","click","type","press","screenshot","snapshot","evaluate","pdf","scroll","hover","wait","url","title"]},"url":{"type":"string"},"selector":{"type":"string"},"text":{"type":"string"},"key":{"type":"string"},"fn":{"type":"string"},"x":{"type":"number"},"y":{"type":"number"},"delta_y":{"type":"number"}},"required":["action"]}}},
    {"type":"function","function":{"name":"nodes","description":"Система, скриншот, процессы, сеть.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["info","screenshot","processes","kill","network","run"]},"filter":{"type":"string"},"target":{"type":"string"},"command":{"type":"string"}},"required":["action"]}}},
    {"type":"function","function":{"name":"canvas","description":"GUI автоматизация: type/key/click/scroll.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["type","key","click","move","scroll","screenshot","position","size"]},"text":{"type":"string"},"key":{"type":"string"},"x":{"type":"number"},"y":{"type":"number"},"button":{"type":"string"},"clicks":{"type":"integer"}},"required":["action"]}}},
    {"type":"function","function":{"name":"cron","description":"Планировщик: in 30min / every 1h / 0 9 * * *.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["add","list","delete","run"]},"label":{"type":"string"},"schedule":{"type":"string"},"prompt":{"type":"string"},"delete_after":{"type":"boolean"},"job_id":{"type":"string"}},"required":["action"]}}},
    {"type":"function","function":{"name":"memory","description":"Работа с MEMORY.md.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["read","write","search","clear"]},"content":{"type":"string"},"query":{"type":"string"},"append":{"type":"boolean"}},"required":["action"]}}},
    {"type":"function","function":{"name":"sessions_spawn","description":"Запускает параллельный суб-агент.","parameters":{"type":"object","properties":{"agent_id":{"type":"string"},"prompt":{"type":"string"}},"required":["agent_id","prompt"]}}},
    {"type":"function","function":{"name":"sessions_list","description":"Список активных сессий.","parameters":{"type":"object","properties":{}}}},
    {"type":"function","function":{"name":"sessions_send","description":"Отправить сообщение в сессию.","parameters":{"type":"object","properties":{"session_id":{"type":"string"},"message":{"type":"string"}},"required":["session_id","message"]}}},
    {"type":"function","function":{"name":"skill_list","description":"Список скиллов.","parameters":{"type":"object","properties":{}}}},
    {"type":"function","function":{"name":"skill_read","description":"Читает SKILL.md.","parameters":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}}},
    {"type":"function","function":{"name":"skill_write","description":"Создаёт скилл.","parameters":{"type":"object","properties":{"name":{"type":"string"},"content":{"type":"string"}},"required":["name","content"]}}},
    {"type":"function","function":{"name":"skill_search","description":"Поиск скиллов.","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}},
    {"type":"function","function":{"name":"skill_install","description":"Устанавливает шаблон скилла.","parameters":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}}},
    {"type":"function","function":{"name":"clipboard","description":"Буфер обмена get/set.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["get","set"]},"text":{"type":"string"}},"required":["action"]}}},
    {"type":"function","function":{"name":"notify","description":"Системное уведомление на экране.","parameters":{"type":"object","properties":{"title":{"type":"string"},"message":{"type":"string"}},"required":["title","message"]}}},
    {"type":"function","function":{"name":"delete_file","description":"Удаляет файл или папку.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
    {"type":"function","function":{"name":"move_file","description":"Перемещает файл или папку.","parameters":{"type":"object","properties":{"src":{"type":"string"},"dst":{"type":"string"}},"required":["src","dst"]}}},
    {"type":"function","function":{"name":"copy_file","description":"Копирует файл или папку.","parameters":{"type":"object","properties":{"src":{"type":"string"},"dst":{"type":"string"}},"required":["src","dst"]}}},
    {"type":"function","function":{"name":"run_code","description":"Запускает код (python/node/bash).","parameters":{"type":"object","properties":{"code":{"type":"string"},"lang":{"type":"string","enum":["python","python3","node","js","bash","ruby","powershell"]}},"required":["code"]}}},
    {"type":"function","function":{"name":"location","description":"Геолокация по IP.","parameters":{"type":"object","properties":{}}}},
    {"type":"function","function":{"name":"email","description":"Email: send/read/search. send требует to,subject,body. read/search не требуют параметров.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["send","read","search"]},"to":{"type":"string"},"subject":{"type":"string"},"body":{"type":"string"},"query":{"type":"string"},"count":{"type":"integer"}},"required":["action"]}}},
    {"type":"function","function":{"name":"calendar","description":"Календарь: add/list/today/week/delete событий.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["add","list","today","week","delete"]},"title":{"type":"string"},"date":{"type":"string"},"time":{"type":"string"},"note":{"type":"string"},"id":{"type":"string"}},"required":["action"]}}},
    {"type":"function","function":{"name":"screen_vision","description":"AI анализирует скриншот экрана — видит что открыто, читает текст.","parameters":{"type":"object","properties":{"query":{"type":"string"}}}}},
    {"type":"function","function":{"name":"app","description":"Управление приложениями: open/close/list. app=telegram/chrome/firefox/vscode/spotify и др.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["open","close","list"]},"app":{"type":"string"}},"required":["action"]}}},
    {"type":"function","function":{"name":"voice","description":"Голосовые функции: say озвучивает текст, volume меняет громкость.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["say","volume","mute"]},"text":{"type":"string"},"level":{"type":"integer"}},"required":["action"]}}},
    {"type":"function","function":{"name":"download","description":"Скачать файл из интернета по URL.","parameters":{"type":"object","properties":{"url":{"type":"string"},"path":{"type":"string"}},"required":["url"]}}},
    {"type":"function","function":{"name":"network","description":"Сеть: ping/ports/myip.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["ping","ports","myip"]},"host":{"type":"string"},"count":{"type":"integer"}},"required":["action"]}}},
    {"type":"function","function":{"name":"monitor","description":"Мониторинг папок/файлов — уведомляет при изменениях.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["watch","list","unwatch"]},"path":{"type":"string"},"label":{"type":"string"},"interval":{"type":"integer"}},"required":["action"]}}},
    {"type":"function","function":{"name":"telegram_send","description":"Отправить сообщение или файл в Telegram.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["send","send_file"]},"text":{"type":"string"},"path":{"type":"string"},"chat_id":{"type":"integer"}},"required":["action"]}}},
]

def call_tool(name: str, args: dict) -> str:
    try:
        _stat(name)
        if   name == "read":              return tool_read(args["path"], args.get("offset",0), args.get("limit",300))
        elif name == "write":             return tool_write(args["path"], args["content"])
        elif name == "edit":              return tool_edit(args["path"], args["old_str"], args["new_str"])
        elif name == "apply_patch":       return tool_apply_patch(args["path"], args["patch"])
        elif name == "ls":                return tool_ls(args.get("path","."), args.get("pattern","*"), args.get("recursive",False))
        elif name == "grep":              return tool_grep(args["pattern"], args.get("path","."), args.get("recursive",True))
        elif name == "find":              return tool_find(args["pattern"], args.get("path","."), args.get("file_type","any"))
        elif name == "delete_file":       return tool_delete(args["path"])
        elif name == "move_file":         return tool_move(args["src"], args["dst"])
        elif name == "copy_file":         return tool_copy(args["src"], args["dst"])
        elif name == "exec":              return json.dumps(tool_exec(args["cmd"],args.get("workdir"),args.get("timeout",60),args.get("background",False),shell=args.get("shell","auto")),ensure_ascii=False)
        elif name == "bash":              return json.dumps(tool_bash(args["code"],args.get("workdir"),args.get("timeout",60)),ensure_ascii=False)
        elif name == "process":           return json.dumps(tool_process(args["session_id"],args.get("action","poll"),args.get("keys")),ensure_ascii=False)
        elif name == "run_code":          return tool_run_code(args["code"], args.get("lang","python"))
        elif name == "web_search":        return tool_web_search(args["query"])
        elif name == "web_fetch":         return tool_web_fetch(args["url"], args.get("selector"))
        elif name == "browser":           a=args.pop("action"); return tool_browser(a, **args)
        elif name == "nodes":             a=args.pop("action"); return tool_nodes(a, **args)
        elif name == "canvas":            a=args.pop("action"); return tool_canvas(a, **args)
        elif name == "cron":              a=args.pop("action"); return tool_cron(a, **args)
        elif name == "memory":            a=args.pop("action"); return tool_memory(a, **args)
        elif name == "sessions_spawn":    return json.dumps(tool_sessions_spawn(args["agent_id"],args["prompt"]),ensure_ascii=False)
        elif name == "sessions_list":     return tool_sessions_list()
        elif name == "sessions_send":     return tool_sessions_send(args["session_id"],args["message"])
        elif name == "sessions_history":  return tool_sessions_history(args["session_id"])
        elif name == "skill_list":        return tool_skills_list()
        elif name == "skill_read":        return tool_skill_read(args["name"])
        elif name == "skill_write":       return tool_skill_write(args["name"],args["content"])
        elif name == "skill_search":      return tool_skill_search(args.get("query",""))
        elif name == "skill_install":     return tool_skill_install(args.get("name",""))
        elif name == "clipboard":         a=args.pop("action"); return tool_clipboard(a, **args)
        elif name == "notify":            return tool_notify(args.get("title","NEXUM"),args.get("message",""))
        elif name == "location":          return tool_location()
        elif name == "email":             a=args.pop("action"); return tool_email(a, **args)
        elif name == "calendar":          a=args.pop("action"); return tool_calendar(a, **args)
        elif name == "screen_vision":     return tool_screen_vision(args.get("query","Что на экране?"))
        elif name == "app":               a=args.pop("action"); return tool_app(a, **args)
        elif name == "voice":             a=args.pop("action"); return tool_voice(a, **args)
        elif name == "download":          return tool_download(args.get("url",""), args.get("path",""))
        elif name == "network":           a=args.pop("action"); return tool_network(a, **args)
        elif name == "monitor":           a=args.pop("action"); return tool_monitor(a, **args)
        elif name == "telegram_send":     a=args.pop("action"); return tool_telegram_send(a, **args)
        else:                             return f"❌ Инструмент не найден: {name}"
    except Exception as e:
        log.error(f"Tool {name}: {traceback.format_exc()}")
        return f"❌ tool:{name}: {e}"

# ═══════════════════════════════════════════════════════════════════════════
#  AI ПРОВАЙДЕРЫ
# ═══════════════════════════════════════════════════════════════════════════
def _detect_provider() -> Tuple[str, str]:
    if AI_PROVIDER != "auto":
        model = AI_MODEL or {
            "anthropic": "claude-haiku-4-5-20251001",
            "openai":    "gpt-4.1-mini",
            "groq":      "llama-3.3-70b-versatile",
            "cerebras":  "llama3.1-8b-instant",
            "gemini":    "gemini-2.0-flash",
        }.get(AI_PROVIDER, "gpt-4.1-mini")
        return AI_PROVIDER, model
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic", "claude-haiku-4-5-20251001"
    if os.getenv("OPENAI_API_KEY"):
        return "openai", "gpt-4.1-mini"
    if os.getenv("GROQ_API_KEY") or any(os.getenv(f"GR{i}") for i in range(1, 11)):
        return "groq", "llama-3.3-70b-versatile"
    if any(os.getenv(f"CB{i}") for i in range(1, 11)):
        return "cerebras", "llama3.1-8b-instant"
    if any(os.getenv(f"G{i}") for i in range(1, 11)):
        return "gemini", "gemini-2.0-flash"
    return "openai", "gpt-4.1-mini"

def _get_api_key(provider: str) -> str:
    if AI_KEY:
        return AI_KEY
    for k in {
        "anthropic": ["ANTHROPIC_API_KEY"] + [f"CL{i}" for i in range(1, 5)],
        "openai":    ["OPENAI_API_KEY"],
        "groq":      ["GROQ_API_KEY"] + [f"GR{i}" for i in range(1, 11)],
        "cerebras":  [f"CB{i}" for i in range(1, 11)],
        "gemini":    [f"G{i}" for i in range(1, 11)],
        "together":  ["TOGETHER_API_KEY"],
    }.get(provider, []):
        v = os.getenv(k)
        if v:
            return v
    return ""

def call_llm(messages: List[dict], tools: list = None, system: str = "") -> dict:
    provider, model = _detect_provider()
    api_key = _get_api_key(provider)
    if not api_key:
        return {"role": "assistant",
                "content": "[Нет AI ключа. Задай NEXUM_AI_KEY или ключ провайдера]",
                "tool_calls": []}
    if provider == "anthropic": return _call_anthropic(api_key, model, messages, tools, system)
    elif provider == "gemini":  return _call_gemini(api_key, model, messages, tools, system)
    else:                       return _call_openai(api_key, model, messages, tools, system, provider)

def _call_anthropic(key, model, messages, tools, system):
    ant_tools = [{"name": t["function"]["name"], "description": t["function"]["description"],
                  "input_schema": t["function"]["parameters"]} for t in (tools or [])]
    payload = {"model": model, "max_tokens": 4096, "messages": messages}
    if ant_tools: payload["tools"] = ant_tools
    if system:    payload["system"] = system
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json=payload, timeout=60)
        data = r.json()
        if "error" in data:
            return {"role": "assistant", "content": f"API error: {data['error']}", "tool_calls": []}
        tool_calls = []
        text_parts = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block["text"])
            elif block.get("type") == "tool_use":
                tool_calls.append({"id": block["id"], "name": block["name"],
                                   "arguments": block.get("input", {})})
        return {"role": "assistant", "content": "\n".join(text_parts), "tool_calls": tool_calls}
    except Exception as e:
        return {"role": "assistant", "content": f"❌ Anthropic: {e}", "tool_calls": []}

def _call_openai(key, model, messages, tools, system, provider):
    endpoints = {
        "openai":    "https://api.openai.com/v1/chat/completions",
        "groq":      "https://api.groq.com/openai/v1/chat/completions",
        "cerebras":  "https://inference.cerebras.ai/v1/chat/completions",
        "together":  "https://api.together.xyz/v1/chat/completions",
        "mistral":   "https://api.mistral.ai/v1/chat/completions",
    }
    url  = endpoints.get(provider, endpoints["openai"])
    msgs = list(messages)
    if system:
        msgs = [{"role": "system", "content": system}] + msgs
    payload = {"model": model, "max_tokens": 4096, "messages": msgs}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    try:
        r = requests.post(url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload, timeout=60)
        data = r.json()
        if "error" in data:
            return {"role": "assistant", "content": f"API error: {data['error']}", "tool_calls": []}
        choice = data["choices"][0]["message"]
        tool_calls = []
        if choice.get("tool_calls"):
            for tc in choice["tool_calls"]:
                try:
                    args = json.loads(tc["function"]["arguments"])
                except:
                    args = {}
                tool_calls.append({"id": tc["id"], "name": tc["function"]["name"], "arguments": args})
        return {"role": "assistant", "content": choice.get("content") or "", "tool_calls": tool_calls}
    except Exception as e:
        return {"role": "assistant", "content": f"❌ {provider}: {e}", "tool_calls": []}

def _call_gemini(key, model, messages, tools, system):
    try:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        payload = {"contents": [{"role": "user", "parts": [{"text": last_user}]}]}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        r = requests.post(url, json=payload, timeout=30)
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return {"role": "assistant", "content": text, "tool_calls": []}
    except Exception as e:
        return {"role": "assistant", "content": f"❌ Gemini: {e}", "tool_calls": []}

# ═══════════════════════════════════════════════════════════════════════════
#  MULTI-AGENT ROUTING
# ═══════════════════════════════════════════════════════════════════════════
_BASE_SYS = (
    f"Ты NEXUM — персональный AI агент на ПК пользователя.\n"
    f"Доступ: файловая система, браузер, shell, GUI.\n"
    f"Workspace: {WORKSPACE}\nOS: {PLATFORM} {platform.release()}\nHost: {platform.node()}\n"
    f"Действуй самостоятельно. Читай файлы, выполняй команды, открывай браузер без лишних вопросов.\n"
    f"Отвечай кратко и по делу."
)

_AGENTS: Dict[str, Dict] = {
    "main":  {"description": "Главный помощник",    "system": _BASE_SYS},
    "code":  {"description": "Специалист по коду",  "system": _BASE_SYS + "\n\nТы CODE SPECIALIST. Пиши production-ready код, всегда тестируй, используй exec/bash/run_code."},
    "web":   {"description": "Веб-исследователь",   "system": _BASE_SYS + "\n\nТы WEB RESEARCHER. Используй browser/web_search/web_fetch."},
    "ops":   {"description": "DevOps/Sysops агент", "system": _BASE_SYS + "\n\nТы SYSOPS. Мониторь процессы, управляй сервисами."},
    "files": {"description": "Файловый менеджер",   "system": _BASE_SYS + "\n\nТы FILE MANAGER. Организуй и обрабатывай файлы."},
}

def tool_agent_route(name: str) -> str:
    global _active_agent
    if name not in _AGENTS:
        return f"❌ Нет агента '{name}'.\n\n" + "\n".join(f"• {k} — {v['description']}" for k, v in _AGENTS.items())
    _active_agent = name
    return f"✅ Активный агент: <b>{name}</b> — {_AGENTS[name]['description']}"

def tool_agent_list() -> str:
    lines = ["🤖 <b>Агенты:</b>\n"]
    for k, v in _AGENTS.items():
        lines.append(f"{'▶️' if k == _active_agent else '•'} <b>{k}</b> — {v['description']}")
    return "\n".join(lines) + f"\n\nАктивный: <b>{_active_agent}</b>"

# ═══════════════════════════════════════════════════════════════════════════
#  AGENT LOOP
# ═══════════════════════════════════════════════════════════════════════════
def _needs_confirm(name: str, args: dict) -> bool:
    if _confirm_mode == "never" or _elevated:
        return False
    if _confirm_mode == "always":
        return True
    if name not in {"exec", "bash", "delete_file", "move_file", "apply_patch"}:
        return False
    cmd = args.get("cmd","") or args.get("code","") or args.get("path","")
    return any(re.search(p, str(cmd), re.I) for p in
               [r'\brm\s+-rf\b', r'\bformat\b', r'\bshutdown\b', r'\bdd\s+if=', r'\bmkfs\b'])

def _ask_approval(chat_id: int, tool: str, details: str) -> str:
    token = hashlib.md5(f"{tool}{time.time()}".encode()).hexdigest()[:8]
    _pending[token] = {"status": "pending"}
    send(chat_id,
         f"⚠️ <b>Подтверждение</b>\n"
         f"Инструмент: <code>{tool}</code>\n<code>{details[:400]}</code>\n\nВыполнить?",
         markup=ikb([("✅ Да", f"ok:{token}"), ("❌ Нет", f"no:{token}")]))
    return token

def _compact(messages: List[dict]) -> List[dict]:
    if len(messages) < 14:
        return messages
    old, recent = messages[:-8], messages[-8:]
    parts = []
    for m in old:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text","") for c in content
                               if isinstance(c, dict) and c.get("type") == "text")
        if content and len(str(content)) > 10:
            parts.append(f"{role}: {str(content)[:200]}")
    return ([{"role": "user",      "content": "Контекст прошлых шагов:\n" + "\n".join(parts[:20])},
             {"role": "assistant", "content": "Контекст загружен."}] + recent)

def _agent_loop(user_message: str, chat_id: Optional[int] = None,
                max_steps: int = 20, agent_name: str = None) -> str:
    agent_name = agent_name or _active_agent
    agent = _AGENTS.get(agent_name, _AGENTS["main"])
    messages: List[dict] = []

    # Память
    if MEMORY_FILE.exists():
        mem = MEMORY_FILE.read_text(encoding="utf-8")[:2000]
        if mem.strip():
            messages += [{"role": "user",      "content": f"[MEMORY.md]\n{mem}"},
                         {"role": "assistant", "content": "Память загружена."}]

    # Релевантные скиллы
    skill_hint = _get_relevant_skills(user_message)
    if skill_hint:
        messages += [{"role": "user",      "content": f"[SKILLS]\n{skill_hint}"},
                     {"role": "assistant", "content": "Скиллы загружены."}]

    messages.append({"role": "user", "content": user_message})

    steps = 0
    final_text = ""

    while steps < max_steps:
        steps += 1
        if len(messages) > 34:
            messages = _compact(messages)
        if chat_id:
            send_typing(chat_id)

        response    = call_llm(messages, tools=TOOLS_SCHEMA, system=agent["system"])
        tool_calls  = response.get("tool_calls", [])
        text        = response.get("content", "")

        if tool_calls:
            msg: dict = {"role": "assistant", "content": []}
            if text:
                msg["content"].append({"type": "text", "text": text})
            for tc in tool_calls:
                msg["content"].append({"type": "tool_use", "id": tc["id"],
                                       "name": tc["name"], "input": tc["arguments"]})
            messages.append(msg)
        else:
            messages.append({"role": "assistant", "content": text or "(нет ответа)"})

        if not tool_calls:
            final_text = text or "(нет ответа)"
            break

        tool_results = []
        for tc in tool_calls:
            t_name = tc["name"]
            t_args = dict(tc.get("arguments", {}))
            t_id   = tc.get("id", "tc0")
            log.info(f"🔧 [{agent_name}] {t_name} {json.dumps(t_args, ensure_ascii=False)[:100]}")

            if _needs_confirm(t_name, t_args) and chat_id:
                token = _ask_approval(chat_id, t_name, json.dumps(t_args, ensure_ascii=False)[:300])
                for _ in range(60):
                    time.sleep(1)
                    st = _pending.get(token, {}).get("status")
                    if st == "approved":
                        del _pending[token]
                        break
                    elif st == "denied":
                        del _pending[token]
                        tool_results.append({"tool_use_id": t_id, "type": "tool_result",
                                             "content": "[Отклонено пользователем]"})
                        t_name = None
                        break
                else:
                    tool_results.append({"tool_use_id": t_id, "type": "tool_result",
                                         "content": "[Timeout ожидания подтверждения]"})
                    t_name = None
                if t_name is None:
                    continue

            result = call_tool(t_name, t_args)

            if isinstance(result, str) and result.startswith("SCREENSHOT:"):
                img_data = base64.b64decode(result[11:])
                if chat_id:
                    send_photo(chat_id, img_data, f"📸 {t_name}")
                result = "[скриншот отправлен в Telegram]"
            elif isinstance(result, str) and result.startswith("PDF:"):
                pdf_data = base64.b64decode(result[4:])
                if chat_id:
                    send_doc(chat_id, pdf_data, "page.pdf", "📄 PDF")
                result = "[PDF отправлен в Telegram]"

            log.info(f"  → {str(result)[:80]}")
            tool_results.append({"tool_use_id": t_id, "type": "tool_result",
                                  "content": str(result)[:8000]})

        messages.append({"role": "user", "content": tool_results})
        if text and chat_id and len(text.strip()) > 10:
            send(chat_id, f"💭 {text[:500]}", parse="HTML")

    if len(user_message) > 30 and chat_id:
        threading.Thread(target=_auto_memorize, args=(user_message, final_text), daemon=True).start()

    return final_text

def _auto_memorize(prompt: str, response: str):
    try:
        if any(w in prompt.lower() for w in ["помни","запомни","важно","remember","save","сохрани"]):
            tool_memory("write", content=f"Запрос: {prompt[:200]}\nОтвет: {response[:300]}", append=True)
    except:
        pass

# ═══════════════════════════════════════════════════════════════════════════
#  HEARTBEAT — проактивный мониторинг каждые 30 мин
# ═══════════════════════════════════════════════════════════════════════════
def _heartbeat():
    if not HEARTBEAT_FILE.exists():
        return
    hb = HEARTBEAT_FILE.read_text(encoding="utf-8").strip()
    if not hb:
        return
    log.info("💓 Heartbeat")
    try:
        result = _agent_loop(f"[HEARTBEAT]\n{hb}", chat_id=None, max_steps=5)
        if result and result.strip() not in ("", "OK", "HEARTBEAT_OK"):
            send(OWNER_ID, f"💓 <b>Heartbeat</b>\n\n{result[:2000]}", parse="HTML")
    except Exception as e:
        log.error(f"Heartbeat: {e}")

# ═══════════════════════════════════════════════════════════════════════════
#  ДИСПЕТЧЕР КОМАНД
# ═══════════════════════════════════════════════════════════════════════════
def dispatch(chat_id: int, text: str):
    t  = text.strip()
    tl = t.lower()

    # ── Системные ─────────────────────────────────────────────────────────
    if tl in ["/start", "/help", "/node_help", "/h", "/?"]:
        send(chat_id, _help()); return
    if tl in ["/ping", "/status", "/node"]:
        prov, mdl = _detect_provider()
        has_key   = bool(_get_api_key(prov))
        uptime    = str(datetime.now() - _session_start).split(".")[0]
        send(chat_id,
             f"🤖 <b>NEXUM Node v{VERSION}</b>\n"
             f"💻 {platform.node()} | {PLATFORM} {platform.release()}\n"
             f"⏱ Uptime: {uptime}\n"
             f"🧠 AI: {prov}/{mdl} {'✅' if has_key else '❌ нет ключа'}\n"
             f"🔒 Confirm: {_confirm_mode}"
             f"{' 🔓 ELEVATED' if _elevated else ''}\n"
             f"🤖 Агент: {_active_agent}\n"
             f"📁 <code>{WORKSPACE}</code>\n"
             f"🖥 GUI: {'✅' if HAS_GUI else '❌'} | "
             f"Browser: {'✅' if _browser_page else '⚠️'}")
        return
    if tl in ["/info", "/sysinfo"]:
        send(chat_id, _nodes_info()); return
    if tl in ["/screenshot", "/ss"]:
        data = _take_screenshot()
        if data: send_photo(chat_id, data, f"📸 {platform.node()}")
        else:    send(chat_id, "❌ pip install pyautogui pillow")
        return
    if tl in ["/memory", "/mem"]:
        send_split(chat_id, "🧠 <b>MEMORY.md:</b>\n\n" + tool_memory("read")); return
    if tl == "/soul":
        soul = SOUL_FILE.read_text(encoding="utf-8") if SOUL_FILE.exists() else "(пуст)"
        send_split(chat_id, f"👤 <b>SOUL.md:</b>\n\n{soul}"); return
    if tl in ["/heartbeat", "/hb"]:
        hb = HEARTBEAT_FILE.read_text(encoding="utf-8") if HEARTBEAT_FILE.exists() else "(пуст)"
        send_split(chat_id, f"💓 <b>HEARTBEAT.md:</b>\n\n{hb}"); return
    if t.startswith("/hb ") or t.startswith("/hb_write "):
        content = t.split(None, 1)[1].strip()
        HEARTBEAT_FILE.write_text(content, encoding="utf-8")
        send(chat_id, "✅ HEARTBEAT.md обновлён. Проверяется каждые 30 мин."); return
    if tl in ["/cron"]:                    send(chat_id, tool_cron("list")); return
    if tl in ["/skills"]:                  send(chat_id, tool_skills_list()); return
    if t.startswith("/skill search "):     send(chat_id, tool_skill_search(t[14:].strip())); return
    if t.startswith("/skill install "):    send(chat_id, tool_skill_install(t[15:].strip())); return
    if tl in ["/workspace", "/ws"]:        send(chat_id, f"📁 <code>{WORKSPACE}</code>\n\n" + tool_ls(str(WORKSPACE))); return
    if tl in ["/sessions"]:               send(chat_id, tool_sessions_list()); return
    if tl in ["/agents"]:                 send(chat_id, tool_agent_list()); return
    if t.startswith("/agent "):           send(chat_id, tool_agent_route(t[7:].strip())); return
    if tl in ["/location"]:               send(chat_id, tool_location()); return

    # ── Elevated / compact ─────────────────────────────────────────────────
    if tl.startswith("/elevated"):
        global _elevated, _confirm_mode
        if "on" in tl:
            _elevated = True; _confirm_mode = "never"
            send(chat_id, "🔓 <b>Elevated mode ON</b> — команды выполняются без подтверждений")
        elif "off" in tl:
            _elevated = False; _confirm_mode = "dangerous"
            send(chat_id, "🔒 <b>Elevated mode OFF</b> — защита включена")
        else:
            send(chat_id, f"🔐 Elevated: {'ON 🔓' if _elevated else 'OFF 🔒'}\n/elevated on|off")
        return
    if tl == "/compact":
        send(chat_id, "✅ Контекст будет сжат при следующем вызове агента."); return

    # ── Tool policy ─────────────────────────────────────────────────────────
    if t.startswith("/allow "):
        g = t[7:].strip()
        tools = TOOL_GROUPS.get(g, [g])
        for tool in tools:
            _tool_policy[tool] = "allow"
        with _db() as c:
            for tool in tools:
                c.execute("INSERT OR REPLACE INTO tool_policy VALUES(?,?)", (tool, "allow"))
        send(chat_id, f"✅ Разрешено: <b>{g}</b> ({len(tools)} инструментов)"); return
    if t.startswith("/deny "):
        g = t[6:].strip()
        tools = TOOL_GROUPS.get(g, [g])
        for tool in tools:
            _tool_policy[tool] = "deny"
        with _db() as c:
            for tool in tools:
                c.execute("INSERT OR REPLACE INTO tool_policy VALUES(?,?)", (tool, "deny"))
        send(chat_id, f"🚫 Запрещено: <b>{g}</b>"); return
    if t.startswith("/confirm"):
        if "always" in tl:   _confirm_mode = "always";    send(chat_id, "🔐 Спрашивать всегда")
        elif "never" in tl:  _confirm_mode = "never";     send(chat_id, "🔓 Без подтверждений")
        elif "danger" in tl: _confirm_mode = "dangerous"; send(chat_id, "⚠️ Только опасные")
        else:                send(chat_id, f"Режим: <b>{_confirm_mode}</b>\n/confirm always|dangerous|never")
        return

    # ── $ прямое выполнение ─────────────────────────────────────────────────
    if t.startswith("$ ") or t.startswith("> "):
        cmd = t[2:].strip()
        send_typing(chat_id)
        r  = tool_exec(cmd, timeout=60)
        rc = r.get("returncode", 0)
        icon = "✅" if rc == 0 else "❌"
        out  = r.get("stdout", "").strip()
        err  = r.get("stderr", "").strip()
        msg  = f"💻 <code>{cmd[:200]}</code>\n{icon} rc:{rc} | {r.get('duration',0)}s"
        if out:  msg += f"\n\n<pre>{out[:3500]}</pre>"
        elif err: msg += f"\n\n<pre>{err[:1000]}</pre>"
        send_split(chat_id, msg)
        return

    # ── Agent loop ──────────────────────────────────────────────────────────
    send_typing(chat_id)
    log.info(f"🤖 [{_active_agent}] {text[:80]}")
    try:
        result = _agent_loop(text, chat_id=chat_id, agent_name=_active_agent)
        if result.strip():
            send_split(chat_id, result)
    except Exception as e:
        log.error(traceback.format_exc())
        send(chat_id, f"❌ {e}")

def _help() -> str:
    prov, mdl = _detect_provider()
    has_key   = bool(_get_api_key(prov))
    return (
        f"🤖 <b>NEXUM Node v{VERSION}</b>\n"
        f"🧠 {prov}/{mdl} {'✅' if has_key else '❌ задай NEXUM_AI_KEY'}\n\n"
        f"<b>💬 Просто пиши задачу — агент выполнит на ПК:</b>\n"
        f'  "найди все .py файлы в Downloads"\n'
        f'  "сделай скриншот и опиши что видишь"\n'
        f'  "открой сайт и достань данные"\n'
        f'  "напиши и запусти скрипт"\n\n'
        f"<b>⚡ Быстрые команды:</b>\n"
        f"<code>$ команда</code> — shell без AI\n"
        f"/info — система\n"
        f"/screenshot — скриншот экрана\n"
        f"/memory — память агента\n"
        f"/heartbeat — проактивный мониторинг\n"
        f"/cron — планировщик задач\n"
        f"/skills — список скиллов\n"
        f"/skill search git\n"
        f"/skill install docker\n"
        f"/sessions — параллельные агенты\n"
        f"/workspace — рабочая папка\n"
        f"/location — геолокация\n\n"
        f"<b>🤖 Multi-agent routing:</b>\n"
        f"/agents — список агентов\n"
        f"/agent code|web|ops|files|main\n\n"
        f"<b>🔐 Права и политики:</b>\n"
        f"/elevated on|off — режим без подтверждений\n"
        f"/compact — сжать контекст\n"
        f"/allow fs|runtime|web|nodes|canvas|all\n"
        f"/deny <группа>\n"
        f"/confirm always|dangerous|never\n\n"
        f"/status — статус ноды"
    )

# ═══════════════════════════════════════════════════════════════════════════
#  ОБРАБОТЧИК TELEGRAM UPDATES
# ═══════════════════════════════════════════════════════════════════════════
def handle_update(upd: dict):
    # Callback кнопки (подтверждения)
    if "callback_query" in upd:
        cb      = upd["callback_query"]
        data    = cb.get("data", "")
        cb_id   = cb["id"]
        from_id = cb["from"]["id"]
        chat_id = cb["message"]["chat"]["id"]
        if from_id != OWNER_ID:
            answer_cb(cb_id, "❌")
            return
        if data.startswith("ok:"):
            token = data[3:]
            if token in _pending:
                _pending[token]["status"] = "approved"
                answer_cb(cb_id, "✅ Выполняю...")
            tg("editMessageReplyMarkup", chat_id=chat_id,
               message_id=cb["message"]["message_id"],
               reply_markup=json.dumps({"inline_keyboard": []}))
        elif data.startswith("no:"):
            token = data[3:]
            if token in _pending:
                _pending[token]["status"] = "denied"
            answer_cb(cb_id, "❌ Отклонено")
            tg("editMessageReplyMarkup", chat_id=chat_id,
               message_id=cb["message"]["message_id"],
               reply_markup=json.dumps({"inline_keyboard": []}))
        return

    if "message" not in upd:
        return
    msg     = upd["message"]
    from_id = msg.get("from", {}).get("id", 0)
    chat_id = msg["chat"]["id"]
    text    = msg.get("text", "").strip()
    doc     = msg.get("document")

    if from_id != OWNER_ID:
        send(chat_id, "🔒 Нет доступа.")
        return

    # Загрузка документа
    if doc:
        fid     = doc["file_id"]
        name    = doc.get("file_name", "upload")
        caption = msg.get("caption", "").strip()
        try:
            fp   = requests.get(f"{BASE}/getFile", params={"file_id": fid}, timeout=10).json()["result"]["file_path"]
            data = requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{fp}", timeout=60).content
            save = WORKSPACE / name
            save.write_bytes(data)
            send(chat_id, f"✅ Сохранено: <code>{save}</code> ({_sz(len(data))})")
            if caption:
                send_typing(chat_id)
                result = _agent_loop(f"{caption}\n[Файл: {save}]", chat_id=chat_id)
                if result:
                    send_split(chat_id, result)
        except Exception as e:
            send(chat_id, f"❌ {e}")
        return

    if not text:
        return

    log.info(f"← {text[:80]}")
    try:
        dispatch(chat_id, text)
    except Exception as e:
        log.error(traceback.format_exc())
        send(chat_id, f"❌ {e}")

# ═══════════════════════════════════════════════════════════════════════════
#  ВОССТАНОВЛЕНИЕ CRON
# ═══════════════════════════════════════════════════════════════════════════
def _restore_cron():
    with _db() as c:
        rows = c.execute("SELECT * FROM cron_jobs WHERE active=1").fetchall()
    for r in rows:
        try:
            trigger = _parse_schedule(r["schedule"])
            if not trigger:
                continue
            label, prompt, jid, da = r["label"], r["prompt"], r["id"], bool(r["delete_after"])

            def _fire(lbl=label, pr=prompt, jid2=jid, da2=da):
                result = _cron_exec(pr)
                if result and result.strip() not in ("OK", ""):
                    send(_cron_chatid, f"⏰ <b>Крон: {lbl}</b>\n\n{result}", parse="HTML")
                if da2:
                    try:
                        _scheduler.remove_job(jid2)
                    except:
                        pass

            _scheduler.add_job(_fire, trigger, id=jid, replace_existing=True)
            log.info(f"Cron восстановлен: {label}")
        except Exception as e:
            log.error(f"Restore cron: {e}")

# ═══════════════════════════════════════════════════════════════════════════
#  SETUP GUIDE
# ═══════════════════════════════════════════════════════════════════════════
def _print_setup():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                  NEXUM Node — Быстрый старт                     ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  1. Получи BOT_TOKEN у @BotFather в Telegram                    ║
║  2. Узнай свой Telegram ID у @userinfobot                       ║
║  3. Получи AI ключ (один из):                                   ║
║     • Anthropic:  https://console.anthropic.com                 ║
║     • OpenAI:     https://platform.openai.com                   ║
║     • Groq:       https://console.groq.com  (бесплатно!)        ║
║     • Gemini:     https://makersuite.google.com (бесплатно!)    ║
║                                                                  ║
║  Windows (PowerShell):                                           ║
║    $env:BOT_TOKEN="токен_бота"                                  ║
║    $env:AGENT_OWNER_ID="твой_telegram_id"                       ║
║    $env:NEXUM_AI_KEY="ai_ключ"                                  ║
║    python nexum_agent.py                                         ║
║                                                                  ║
║  Linux / macOS:                                                  ║
║    BOT_TOKEN="..." AGENT_OWNER_ID="..." NEXUM_AI_KEY="..." \\   ║
║      python nexum_agent.py                                       ║
║                                                                  ║
║  Или создай файл .env:                                          ║
║    BOT_TOKEN=токен                                               ║
║    AGENT_OWNER_ID=id                                             ║
║    NEXUM_AI_KEY=ключ                                             ║
║    python nexum_agent.py                                         ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""")

# ═══════════════════════════════════════════════════════════════════════════
#  POLLING LOOP
# ═══════════════════════════════════════════════════════════════════════════
def _poll():
    global _offset
    try:
        r = requests.get(
            f"{BASE}/getUpdates",
            params={"offset": _offset, "timeout": 30,
                    "allowed_updates": ["message", "callback_query"]},
            timeout=35
        )
        if r.status_code != 200:
            time.sleep(5)
            return
        for upd in r.json().get("result", []):
            _offset = upd["update_id"] + 1
            handle_update(upd)
    except requests.Timeout:
        pass
    except Exception as e:
        log.error(f"Poll: {e}")
        time.sleep(5)

# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не задан!\n")
        _print_setup()
        sys.exit(1)

    init_db()

    # Pairing flow — нода регистрируется у бота
    _do_pairing()

    # Планировщик
    _scheduler.start()
    _restore_cron()
    _scheduler.add_job(_heartbeat, IntervalTrigger(minutes=30),
                       id="heartbeat", replace_existing=True)

    prov, mdl = _detect_provider()
    has_key   = bool(_get_api_key(prov))

    log.info("=" * 62)
    log.info(f"  NEXUM Node v{VERSION} — готова к работе")
    log.info(f"  Host:      {platform.node()} | {PLATFORM}")
    log.info(f"  Workspace: {WORKSPACE}")
    log.info(f"  AI:        {prov}/{mdl} {'✅' if has_key else '❌ НЕТ КЛЮЧА'}")
    log.info(f"  GUI:       {'✅' if HAS_GUI else '❌ (pip install pyautogui pillow)'}")
    log.info(f"  Browser:   {'⚠️ pip install playwright && playwright install chromium' if not shutil.which('playwright') else '✅'}")
    log.info("=" * 62)

    def _sig(s, f):
        global _running
        _running = False
        _scheduler.shutdown(wait=False)
        log.info("👋 Нода остановлена.")
        sys.exit(0)

    signal.signal(signal.SIGINT,  _sig)
    try:
        signal.signal(signal.SIGTERM, _sig)
    except:
        pass

    log.info("✅ Слушаю команды...")

    while _running:
        try:
            _poll()
        except KeyboardInterrupt:
            _sig(None, None)


if __name__ == "__main__":
    main()
