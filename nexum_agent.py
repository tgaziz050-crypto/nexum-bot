#!/usr/bin/env python3
"""
NEXUM PC Agent v9
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Архитектура: User → Telegram → NEXUM Bot → NEXUM Core
             → Planner → Executor → NEXUM Agent

Возможности:
  СИСТЕМНЫЕ (нативно):
  ✅ screenshot / region capture        ← PIL/scrot
  ✅ mouse / keyboard control           ← pyautogui
  ✅ terminal commands (sync + bg)      ← subprocess
  ✅ filesystem (r/w/list/copy/move/delete/zip/search) ← pathlib
  ✅ clipboard read/write               ← pyperclip
  ✅ system notifications               ← plyer/osascript/notify-send
  ✅ window list/focus/close            ← wmctrl/osascript/powershell
  ✅ HTTP requests GET/POST/PUT/DELETE  ← requests
  ✅ browser open                       ← webbrowser
  ✅ app open                           ← subprocess
  ✅ sysinfo / processes / kill         ← psutil
  ✅ background processes               ← subprocess.Popen
  ✅ network info                       ← psutil+requests
  ✅ user identity autodetect           ← os/platform

  OPENCLAW CLI SKILLS:
  ✅ weather           ← wttr.in (HTTP)
  ✅ github            ← gh CLI
  ✅ google-workspace  ← gog CLI
  ✅ notion            ← Notion API
  ✅ obsidian          ← obsidian-cli / прямой доступ к vault
  ✅ apple-notes       ← memo CLI (macOS)
  ✅ apple-reminders   ← remindctl CLI (macOS)
  ✅ trello            ← Trello REST API
  ✅ slack             ← Slack API
  ✅ discord           ← Discord API
  ✅ spotify           ← spogo / spotify_player CLI
  ✅ tmux              ← tmux CLI
  ✅ video-frames      ← ffmpeg CLI
  ✅ whisper STT       ← whisper CLI / OpenAI API
  ✅ image gen         ← OpenAI Images API
  ✅ gemini            ← gemini CLI / Gemini API
  ✅ summarize         ← summarize CLI / HTTP fallback
  ✅ himalaya (email)  ← himalaya CLI
  ✅ 1password         ← op CLI
  ✅ coding-agent      ← claude/codex/opencode CLI
  ✅ healthcheck       ← requests
  ✅ openhue           ← openhue CLI
  ✅ sag TTS           ← sag CLI / ElevenLabs API
  ✅ skill-creator     ← ~/.nexum/skills

Установка:
  pip install websockets pyautogui pillow psutil requests pyperclip plyer

Запуск:
  python nexum_agent.py
  python nexum_agent.py wss://your-bot.railway.app/ws
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio, base64, io, json, os, platform, shutil, socket
import subprocess, sys, time, uuid, zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Auto-install core deps ────────────────────────────────────────────────────
_REQUIRED = {
    'websockets': 'websockets',
    'psutil':     'psutil',
    'requests':   'requests',
}
def _ensure_deps():
    missing = [pkg for imp, pkg in _REQUIRED.items() if not __import__(imp) if True else False]
    # safer check
    for imp, pkg in _REQUIRED.items():
        try: __import__(imp)
        except ImportError:
            print(f"📦 Installing {pkg}...")
            subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=True, capture_output=True)

_ensure_deps()
import websockets, psutil, requests

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_FILE   = Path.home() / ".nexum_agent.json"
DEFAULT_URL   = "ws://localhost:3000/ws"
SERVER_URL    = os.environ.get("NEXUM_SERVER", DEFAULT_URL)
DEVICE_ID: Optional[str] = None
UID: Optional[int]        = None
AGENT_VERSION             = "9.0.0"

def load_config():
    global DEVICE_ID, UID, SERVER_URL
    if CONFIG_FILE.exists():
        try:
            c = json.loads(CONFIG_FILE.read_text())
            DEVICE_ID = c.get("device_id")
            UID       = c.get("uid")
            if c.get("server_url"): SERVER_URL = c["server_url"]
        except Exception: pass
    if not DEVICE_ID:
        DEVICE_ID = str(uuid.uuid4())[:8].upper()
        save_config()

def save_config():
    CONFIG_FILE.write_text(json.dumps({
        "device_id":  DEVICE_ID,
        "uid":        UID,
        "server_url": SERVER_URL,
        "version":    AGENT_VERSION,
        "os_user":    os.getenv("USER") or os.getenv("USERNAME") or "unknown",
        "hostname":   socket.gethostname(),
        "platform":   f"{platform.system()} {platform.release()}",
        "updated":    datetime.now().isoformat(),
    }, indent=2))

def _env(k: str) -> str:
    return os.environ.get(k, "")

# ═══════════════════════════════════════════════════════════════════════════════
# СИСТЕМНЫЕ ФУНКЦИИ
# ═══════════════════════════════════════════════════════════════════════════════

def get_sysinfo() -> str:
    cpu  = psutil.cpu_percent(interval=0.5)
    ram  = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    boot = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M")
    net  = psutil.net_io_counters()
    return (
        f"💻 OS: {platform.system()} {platform.release()} ({platform.machine()})\n"
        f"🖥 Host: {socket.gethostname()}\n"
        f"🐍 Python: {platform.python_version()}\n"
        f"⚙️ CPU: {cpu}% · {psutil.cpu_count(logical=False)}c/{psutil.cpu_count()} threads\n"
        f"🧠 RAM: {ram.used//1024**2}MB / {ram.total//1024**2}MB ({ram.percent}%)\n"
        f"💾 Disk: {disk.used//1024**3}GB / {disk.total//1024**3}GB ({disk.percent}%)\n"
        f"🌐 Net ↑{net.bytes_sent//1024**2}MB ↓{net.bytes_recv//1024**2}MB\n"
        f"🕐 Boot: {boot}"
    )

def get_platform() -> str:
    return f"{platform.system()} {platform.release()} ({platform.machine()})"

def detect_identity() -> dict:
    info = {
        "os_user":  os.getenv("USER") or os.getenv("USERNAME") or "unknown",
        "hostname": socket.gethostname(),
        "home":     str(Path.home()),
        "platform": get_platform(),
        "lang":     os.getenv("LANG", ""),
    }
    try: info["tz"] = datetime.now().astimezone().tzname() or ""
    except: info["tz"] = ""
    return info

def get_processes(limit: int = 15) -> str:
    procs = []
    for p in psutil.process_iter(["pid","name","cpu_percent","memory_percent"]):
        try: procs.append(p.info)
        except: pass
    procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
    lines = ["PID     CPU%   MEM%   NAME"]
    for p in procs[:limit]:
        lines.append(f"{p['pid']:<7} {(p['cpu_percent'] or 0):>5.1f}  {(p['memory_percent'] or 0):>5.1f}  {(p['name'] or '')[:30]}")
    return "\n".join(lines)

def kill_process(target: str) -> str:
    try:
        if target.isdigit():
            psutil.Process(int(target)).terminate()
            return f"✅ Terminated PID {target}"
        killed = 0
        for p in psutil.process_iter(["pid","name"]):
            if target.lower() in (p.info.get("name") or "").lower():
                p.terminate(); killed += 1
        return f"✅ Killed {killed} process(es) matching '{target}'"
    except Exception as e: return f"Error: {e}"

def get_network_info() -> str:
    lines = [f"🌐 Hostname: {socket.gethostname()}"]
    try: lines.append(f"🌍 Public IP: {requests.get('https://api.ipify.org', timeout=5).text}")
    except: pass
    for name, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET:
                lines.append(f"📡 {name}: {addr.address}")
    net = psutil.net_io_counters()
    lines.append(f"↑ {net.bytes_sent//1024**2}MB  ↓ {net.bytes_recv//1024**2}MB")
    return "\n".join(lines)

# ── Background processes ──────────────────────────────────────────────────────
_bg: dict = {}

def run_background(cmd: str) -> str:
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(Path.home()))
    pid  = str(uuid.uuid4())[:6]
    _bg[pid] = proc
    return f"✅ Started [{pid}] PID={proc.pid}"

def stop_bg(pid: str) -> str:
    p = _bg.get(pid)
    if not p: return f"❌ [{pid}] not found"
    p.terminate(); del _bg[pid]
    return f"✅ Stopped [{pid}]"

def list_bg() -> str:
    if not _bg: return "No background processes"
    return "\n".join(f"[{k}] PID={v.pid} {'running' if v.poll() is None else 'done'}" for k,v in _bg.items())

# ── Terminal ──────────────────────────────────────────────────────────────────
def run_command(cmd: str, timeout: int = 60, cwd: Optional[str] = None) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd or str(Path.home()))
        out, err = r.stdout.strip(), r.stderr.strip()
        if out and err: return f"{out}\n\nSTDERR:\n{err}"
        return out or err or "(no output)"
    except subprocess.TimeoutExpired: return f"⏱ Timeout ({timeout}s)"
    except Exception as e: return f"Error: {e}"

# ── Screenshot ────────────────────────────────────────────────────────────────
def take_screenshot(region=None) -> Optional[str]:
    # Try PIL
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(bbox=region)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError: pass
    # Try pyautogui
    try:
        import pyautogui
        img = pyautogui.screenshot(region=region)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except: pass
    # Try CLI
    for cmd in [["scrot","-o","/tmp/nxss.png"], ["gnome-screenshot","-f","/tmp/nxss.png"]]:
        try:
            if subprocess.run(cmd, capture_output=True).returncode == 0:
                return base64.b64encode(open("/tmp/nxss.png","rb").read()).decode()
        except: pass
    return None

# ── Filesystem ────────────────────────────────────────────────────────────────
def filesystem_op(op: str, path_str: str, content: str = "") -> str:
    try:
        p = Path(path_str).expanduser()
        if op == "read":
            return p.read_text(errors="replace")[:4000] if p.exists() else f"❌ Not found: {path_str}"
        elif op == "write":
            p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content)
            return f"✅ Written → {path_str}"
        elif op == "append":
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p,"a") as f: f.write(content)
            return f"✅ Appended → {path_str}"
        elif op == "list":
            if not p.is_dir(): return f"❌ Not a directory: {path_str}"
            items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name))[:60]
            return "\n".join(("📁 " if i.is_dir() else "📄 ") + i.name + (f" ({i.stat().st_size//1024}KB)" if i.is_file() else "") for i in items) or "(empty)"
        elif op == "delete":
            if not p.exists(): return f"❌ Not found: {path_str}"
            shutil.rmtree(p) if p.is_dir() else p.unlink()
            return f"✅ Deleted {path_str}"
        elif op == "copy":
            dst = Path(content).expanduser()
            shutil.copytree(str(p),str(dst)) if p.is_dir() else shutil.copy2(str(p),str(dst))
            return f"✅ Copied → {content}"
        elif op == "move":
            Path(content).expanduser().parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), content)
            return f"✅ Moved → {content}"
        elif op == "info":
            if not p.exists(): return f"❌ Not found: {path_str}"
            s = p.stat()
            return f"📄 {p.name}\nPath: {p.resolve()}\nType: {'dir' if p.is_dir() else 'file'}\nSize: {s.st_size//1024}KB\nModified: {datetime.fromtimestamp(s.st_mtime).strftime('%Y-%m-%d %H:%M')}"
        elif op == "search":
            return "\n".join(str(r) for r in list(p.rglob(content or "*"))[:30]) or "(nothing found)"
        elif op == "mkdir":
            p.mkdir(parents=True, exist_ok=True); return f"✅ Created {path_str}"
        elif op == "zip":
            dst = content or str(p) + ".zip"
            with zipfile.ZipFile(dst,"w",zipfile.ZIP_DEFLATED) as zf:
                if p.is_dir(): [zf.write(f, f.relative_to(p.parent)) for f in p.rglob("*") if f.is_file()]
                else: zf.write(p, p.name)
            return f"✅ Archived → {dst}"
        elif op == "unzip":
            dst = content or str(p.parent / p.stem)
            with zipfile.ZipFile(str(p)) as zf: zf.extractall(dst)
            return f"✅ Extracted → {dst}"
        else: return f"❌ Unknown op: {op}"
    except PermissionError: return "❌ Permission denied"
    except Exception as e: return f"Error: {e}"

# ── Clipboard ─────────────────────────────────────────────────────────────────
def clipboard_op(op: str, text: str = "") -> str:
    try:
        import pyperclip
        if op == "read": return pyperclip.paste() or "(empty)"
        pyperclip.copy(text); return f"✅ Copied: {text[:80]}"
    except Exception as e: return f"Error: {e}"

# ── Notifications ──────────────────────────────────────────────────────────────
def send_notification(title: str, msg: str, timeout: int = 5) -> str:
    try:
        from plyer import notification
        notification.notify(title=title, message=msg, timeout=timeout)
        return "✅ Notification sent"
    except: pass
    sys_name = platform.system()
    try:
        if sys_name == "Darwin":
            subprocess.run(["osascript","-e",f'display notification "{msg}" with title "{title}"'])
        elif sys_name == "Windows":
            subprocess.run(["powershell","-Command",f'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show("{msg}","{title}")'])
        else:
            subprocess.run(["notify-send", title, msg])
        return "✅ Notification sent"
    except Exception as e: return f"Error: {e}"

# ── Window management ──────────────────────────────────────────────────────────
def window_op(op: str, win: str = "") -> str:
    sys_name = platform.system()
    try:
        if op == "list":
            if sys_name == "Darwin":
                r = subprocess.run(["osascript","-e",'tell application "System Events" to get name of every process whose background only is false'], capture_output=True, text=True)
                return r.stdout.strip()
            elif sys_name == "Linux":
                r = subprocess.run(["wmctrl","-l"], capture_output=True, text=True)
                return r.stdout.strip() or "(wmctrl not installed)"
            else:
                r = subprocess.run(["powershell","-Command","Get-Process | Where-Object {$_.MainWindowTitle} | Select Name,MainWindowTitle | ft"], capture_output=True, text=True)
                return r.stdout.strip()
        elif op == "focus":
            if sys_name == "Linux": subprocess.run(["wmctrl","-a",win])
            elif sys_name == "Darwin": subprocess.run(["osascript","-e",f'tell application "{win}" to activate'])
            return f"✅ Focused: {win}"
        elif op == "close":
            if sys_name == "Linux": subprocess.run(["wmctrl","-c",win])
            elif sys_name == "Darwin": subprocess.run(["osascript","-e",f'tell application "{win}" to quit'])
            return f"✅ Closed: {win}"
        return f"❌ Not supported on {sys_name}"
    except Exception as e: return f"Error: {e}"

# ── HTTP ───────────────────────────────────────────────────────────────────────
def http_request(method: str, url: str, body: str = "", headers_str: str = "") -> str:
    try:
        headers = {}
        for line in (headers_str or "").split("\n"):
            if ":" in line: k,v = line.split(":",1); headers[k.strip()] = v.strip()
        m = method.upper()
        if   m == "GET":    r = requests.get(url, headers=headers, timeout=15)
        elif m == "DELETE": r = requests.delete(url, headers=headers, timeout=15)
        elif m == "POST":
            try: r = requests.post(url, json=json.loads(body or "{}"), headers=headers, timeout=15)
            except: r = requests.post(url, data=body, headers=headers, timeout=15)
        elif m == "PUT":
            try: r = requests.put(url, json=json.loads(body or "{}"), headers=headers, timeout=15)
            except: r = requests.put(url, data=body, headers=headers, timeout=15)
        else: return f"❌ Unknown method: {method}"
        return f"Status: {r.status_code}\n\n{r.text[:3000]}"
    except Exception as e: return f"Error: {e}"

# ── Browser / Apps ─────────────────────────────────────────────────────────────
def open_browser(url: str) -> str:
    try:
        import webbrowser; webbrowser.open(url)
        return f"✅ Opened: {url}"
    except Exception as e: return f"Error: {e}"

def open_application(name: str) -> str:
    sys_name = platform.system()
    try:
        if sys_name == "Windows":    subprocess.Popen(["start", name], shell=True)
        elif sys_name == "Darwin":   subprocess.Popen(["open", "-a", name])
        else:
            try: subprocess.Popen([name])
            except: subprocess.Popen(["xdg-open", name])
        return f"✅ Opened: {name}"
    except Exception as e: return f"Error: {e}"

# ── Mouse / Keyboard ───────────────────────────────────────────────────────────
def mouse_control(action: str, x: int = 0, y: int = 0, text: str = "") -> str:
    try:
        import pyautogui; pyautogui.FAILSAFE = True
        if action == "click":          pyautogui.click(x, y);           return f"✅ Clicked ({x},{y})"
        elif action == "move":         pyautogui.moveTo(x, y, 0.3);     return f"✅ Moved ({x},{y})"
        elif action == "double_click": pyautogui.doubleClick(x, y);     return f"✅ DoubleClick ({x},{y})"
        elif action == "right_click":  pyautogui.rightClick(x, y);      return f"✅ RightClick ({x},{y})"
        elif action == "type":         pyautogui.typewrite(text, 0.03); return f"✅ Typed: {text[:60]}"
        elif action == "hotkey":
            pyautogui.hotkey(*[k.strip() for k in text.split("+")]); return f"✅ Hotkey: {text}"
        elif action == "press":        pyautogui.press(text);            return f"✅ Pressed: {text}"
        elif action == "scroll":       pyautogui.scroll(x);              return f"✅ Scrolled {x}"
        elif action == "position":
            pos = pyautogui.position(); return f"Mouse at ({pos.x},{pos.y})"
        elif action == "screen_size":
            sz = pyautogui.size();      return f"Screen: {sz.width}×{sz.height}"
        elif action == "drag":
            parts = [int(v.strip()) for v in text.split(",")]
            pyautogui.dragTo(parts[0], parts[1], 0.5); return f"✅ Dragged → ({parts[0]},{parts[1]})"
        else: return f"❌ Unknown action: {action}"
    except ImportError: return "❌ pyautogui not installed: pip install pyautogui"
    except Exception as e: return f"Error: {e}"

# ═══════════════════════════════════════════════════════════════════════════════
# OPENCLAW CLI SKILLS
# ═══════════════════════════════════════════════════════════════════════════════

def weather(location: str, mode: str = "current") -> str:
    try:
        loc = location.replace(" ","+")
        fmt = "v2" if mode == "forecast" else ("3" if mode == "oneline" else "0")
        url = f"https://wttr.in/{loc}?{fmt}" if fmt != "v2" else f"https://wttr.in/{loc}?format=v2"
        return requests.get(url, timeout=10).text[:2000]
    except Exception as e: return f"Error: {e}"

def github(subcmd: str) -> str:
    if not shutil.which("gh"): return "❌ gh CLI not installed: brew install gh"
    return run_command(f"gh {subcmd}", timeout=30)

def google_workspace(subcmd: str) -> str:
    if not shutil.which("gog"): return "❌ gog CLI not installed: brew install steipete/tap/gogcli"
    return run_command(f"gog {subcmd}", timeout=30)

def notion(method: str, endpoint: str, body: str = "", api_key: str = "") -> str:
    key = api_key or _env("NOTION_API_KEY")
    if not key: return "❌ NOTION_API_KEY not set"
    headers = {"Authorization":f"Bearer {key}","Notion-Version":"2022-06-28","Content-Type":"application/json"}
    url = f"https://api.notion.com/v1/{endpoint.lstrip('/')}"
    try:
        if method.upper()=="GET":    r = requests.get(url, headers=headers, timeout=15)
        elif method.upper()=="POST": r = requests.post(url, headers=headers, json=json.loads(body or "{}"), timeout=15)
        elif method.upper()=="PATCH": r = requests.patch(url, headers=headers, json=json.loads(body or "{}"), timeout=15)
        else: return f"❌ Unknown method"
        return f"Status: {r.status_code}\n\n{r.text[:3000]}"
    except Exception as e: return f"Error: {e}"

def obsidian(op: str, path_arg: str = "", content: str = "") -> str:
    if shutil.which("obsidian-cli"):
        if op == "list":   return run_command("obsidian-cli list")
        elif op == "open": return run_command(f'obsidian-cli open "{path_arg}"')
        elif op == "search": return run_command(f'obsidian-cli search "{path_arg}"')
    vault_config = Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    if vault_config.exists():
        try:
            cfg = json.loads(vault_config.read_text())
            vault_path = Path(list(cfg.get("vaults",{}).values())[0].get("path",""))
            if op == "list":   return filesystem_op("list", str(vault_path))
            elif op == "read": return filesystem_op("read", str(vault_path / path_arg))
            elif op == "write": return filesystem_op("write", str(vault_path / path_arg), content)
            elif op == "search": return "\n".join(str(r) for r in list(vault_path.rglob(f"*{path_arg}*"))[:20]) or "(nothing found)"
        except Exception as e: return f"Vault error: {e}"
    return "❌ obsidian-cli not installed and no vault found"

def apple_notes(op: str, arg: str = "") -> str:
    if not shutil.which("memo"): return "❌ memo not installed (macOS only)"
    cmds = {"list":"memo notes list","search":f'memo notes search "{arg}"',"add":f'memo notes add "{arg}"',"view":f'memo notes view "{arg}"'}
    return run_command(cmds.get(op, f"memo {op} {arg}"), timeout=15)

def apple_reminders(op: str, arg: str = "") -> str:
    if not shutil.which("remindctl"): return "❌ remindctl not installed (macOS only)"
    cmds = {"list":"remindctl list","add":f'remindctl add "{arg}"',"complete":f'remindctl complete "{arg}"'}
    return run_command(cmds.get(op, f"remindctl {op} {arg}"), timeout=15)

def trello(op: str, arg: str = "", body: dict = None) -> str:
    key   = _env("TRELLO_API_KEY"); token = _env("TRELLO_TOKEN")
    if not key or not token: return "❌ TRELLO_API_KEY and TRELLO_TOKEN not set"
    base  = "https://api.trello.com/1"; auth = f"key={key}&token={token}"
    try:
        if op == "boards":
            r = requests.get(f"{base}/members/me/boards?{auth}", timeout=10)
            return "\n".join(f"{b['name']} (id: {b['id']})" for b in r.json())
        elif op == "cards":
            r = requests.get(f"{base}/lists/{arg}/cards?{auth}", timeout=10)
            return "\n".join(f"{c['name']} (id: {c['id']})" for c in r.json())
        elif op == "create_card":
            d = body or {}
            r = requests.post(f"{base}/cards?{auth}", data={"idList":d.get("list_id",arg),"name":d.get("name","")}, timeout=10)
            c = r.json(); return f"✅ Created: {c.get('name')} (id: {c.get('id')})"
        return f"❌ Unknown op: {op}"
    except Exception as e: return f"Error: {e}"

def slack(op: str, channel: str = "", text: str = "", **kwargs) -> str:
    token = _env("SLACK_BOT_TOKEN")
    if not token: return "❌ SLACK_BOT_TOKEN not set"
    headers = {"Authorization":f"Bearer {token}","Content-Type":"application/json"}
    try:
        if op == "send":
            r = requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel":channel,"text":text}, timeout=10)
        elif op == "channels":
            r = requests.get("https://slack.com/api/conversations.list", headers=headers, params={"limit":30}, timeout=10)
            return "\n".join(f"#{c['name']} (id: {c['id']})" for c in r.json().get("channels",[]))
        elif op == "history":
            r = requests.get("https://slack.com/api/conversations.history", headers=headers, params={"channel":channel,"limit":10}, timeout=10)
            msgs = r.json().get("messages",[])
            return "\n".join(f"[{m.get('user','?')}]: {m.get('text','')}" for m in msgs)
        else: return f"❌ Unknown op: {op}"
        return f"Status: {r.status_code}\n{r.text[:1500]}"
    except Exception as e: return f"Error: {e}"

def discord(op: str, channel_id: str = "", text: str = "", **kwargs) -> str:
    token = _env("DISCORD_BOT_TOKEN")
    if not token: return "❌ DISCORD_BOT_TOKEN not set"
    headers = {"Authorization":f"Bot {token}","Content-Type":"application/json"}
    base = "https://discord.com/api/v10"
    try:
        if op == "send":
            r = requests.post(f"{base}/channels/{channel_id}/messages", headers=headers, json={"content":text}, timeout=10)
        elif op == "history":
            r = requests.get(f"{base}/channels/{channel_id}/messages?limit=10", headers=headers, timeout=10)
            return "\n".join(f"[{m['author']['username']}]: {m['content']}" for m in r.json())
        else: return f"❌ Unknown op: {op}"
        return f"Status: {r.status_code}\n{r.text[:1500]}"
    except Exception as e: return f"Error: {e}"

def spotify(op: str, arg: str = "") -> str:
    cli = shutil.which("spogo") or shutil.which("spotify_player")
    if not cli: return "❌ spogo or spotify_player not installed"
    name = Path(cli).name
    cmds_spogo = {"play":"spogo play","pause":"spogo pause","next":"spogo next","prev":"spogo prev","status":"spogo status","search":f'spogo search track "{arg}"'}
    cmds_sp    = {"play":"spotify_player playback play","pause":"spotify_player playback pause","next":"spotify_player playback next","status":"spotify_player playback"}
    cmds = cmds_spogo if name == "spogo" else cmds_sp
    return run_command(cmds.get(op, f"{name} {op} {arg}"), timeout=15)

def tmux(op: str, session: str = "main", pane: str = "", keys: str = "") -> str:
    if not shutil.which("tmux"): return "❌ tmux not installed"
    if op == "list":    return run_command("tmux list-sessions 2>/dev/null || echo 'No sessions'")
    elif op == "new":   return run_command(f"tmux new-session -d -s {session}")
    elif op == "kill":  return run_command(f"tmux kill-session -t {session}")
    elif op == "send":  return run_command(f"tmux send-keys -t {session}{':'+pane if pane else ''} '{keys}' Enter")
    elif op == "capture": return run_command(f"tmux capture-pane -t {session} -p")
    return run_command(f"tmux {op} {session}", timeout=10)

def video_frames(video_path: str, op: str = "frame", time_arg: str = "00:00:01", out: str = "") -> str:
    if not shutil.which("ffmpeg"): return "❌ ffmpeg not installed"
    out_path = out or f"/tmp/nexum_frame_{uuid.uuid4().hex[:6]}.jpg"
    if op == "frame":
        run_command(f'ffmpeg -y -i "{video_path}" -ss {time_arg} -vframes 1 "{out_path}" 2>/dev/null', timeout=30)
        return f"✅ Frame saved: {out_path}" if Path(out_path).exists() else "❌ Failed"
    elif op == "info":
        return run_command(f'ffprobe -v quiet -print_format json -show_format -show_streams "{video_path}"', timeout=10)
    return run_command(f'ffmpeg {op} -i "{video_path}" {out}', timeout=60)

def whisper_transcribe(audio_path: str, model: str = "base", api_key: str = "") -> str:
    if shutil.which("whisper"):
        return run_command(f'whisper "{audio_path}" --model {model} --output_format txt --output_dir /tmp', timeout=120)
    key = api_key or _env("OPENAI_API_KEY")
    if key:
        try:
            with open(audio_path,"rb") as f:
                r = requests.post("https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization":f"Bearer {key}"},
                    files={"file":f}, data={"model":"whisper-1"}, timeout=60)
            return r.json().get("text", r.text)
        except Exception as e: return f"Error: {e}"
    return "❌ whisper CLI not installed and OPENAI_API_KEY not set"

def openai_image_gen(prompt: str, model: str = "dall-e-3", size: str = "1024x1024", api_key: str = "") -> str:
    key = api_key or _env("OPENAI_API_KEY")
    if not key: return "❌ OPENAI_API_KEY not set"
    try:
        r = requests.post("https://api.openai.com/v1/images/generations",
            headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
            json={"model":model,"prompt":prompt,"n":1,"size":size}, timeout=90)
        data = r.json()
        if "data" in data:
            url = data["data"][0].get("url","")
            img_r = requests.get(url, timeout=30)
            fname = f"/tmp/nexum_img_{uuid.uuid4().hex[:6]}.png"
            with open(fname,"wb") as f: f.write(img_r.content)
            return f"✅ Image saved: {fname}\nURL: {url}"
        return f"Error: {data}"
    except Exception as e: return f"Error: {e}"

def gemini_query(prompt: str, api_key: str = "") -> str:
    if shutil.which("gemini"): return run_command(f'gemini "{prompt}"', timeout=30)
    key = api_key or _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")
    if key:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
                json={"contents":[{"parts":[{"text":prompt}]}]}, timeout=30)
            return r.json().get("candidates",[{}])[0].get("content",{}).get("parts",[{}])[0].get("text",r.text)
        except Exception as e: return f"Error: {e}"
    return "❌ gemini CLI not installed and GEMINI_API_KEY not set"

def summarize(target: str) -> str:
    if shutil.which("summarize"): return run_command(f'summarize "{target}"', timeout=60)
    if target.startswith("http"):
        try:
            r = requests.get(target, timeout=15, headers={"User-Agent":"Mozilla/5.0"})
            return f"Fetched content (3000 chars):\n{r.text[:3000]}"
        except Exception as e: return f"Error: {e}"
    return "❌ summarize CLI not installed"

def himalaya(subcmd: str) -> str:
    if not shutil.which("himalaya"): return "❌ himalaya not installed: brew install himalaya"
    return run_command(f"himalaya {subcmd}", timeout=20)

def onepassword(subcmd: str) -> str:
    if not shutil.which("op"): return "❌ op CLI not installed: brew install 1password-cli"
    return run_command(f"op {subcmd}", timeout=20)

def coding_agent(prompt: str, agent: str = "auto", project_dir: str = "") -> str:
    cwd = project_dir or str(Path.home())
    if agent == "auto":
        if shutil.which("claude"):     agent = "claude"
        elif shutil.which("codex"):    agent = "codex"
        elif shutil.which("opencode"): agent = "opencode"
        else: return "❌ No coding agent installed. Install: npm install -g @anthropic-ai/claude-code"
    if agent == "claude":
        return run_command(f'claude --permission-mode bypassPermissions --print "{prompt}"', timeout=120, cwd=cwd)
    elif agent == "codex":
        return run_command(f'codex exec "{prompt}"', timeout=120, cwd=cwd)
    elif agent == "opencode":
        return run_command(f'opencode "{prompt}"', timeout=120, cwd=cwd)
    return f"❌ Unknown agent: {agent}"

def healthcheck(url: str, method: str = "GET") -> str:
    try:
        start = time.time()
        r = requests.request(method, url, timeout=10)
        ms = int((time.time()-start)*1000)
        return f"{'✅' if r.status_code < 400 else '❌'} {url}\nStatus: {r.status_code} ({ms}ms)"
    except requests.exceptions.Timeout: return f"❌ {url}\nTimeout"
    except Exception as e: return f"❌ {url}\n{e}"

def openhue(subcmd: str) -> str:
    if not shutil.which("openhue"): return "❌ openhue not installed"
    return run_command(f"openhue {subcmd}", timeout=10)

def sag_tts(text: str, voice: str = "", api_key: str = "") -> str:
    if shutil.which("sag"):
        cmd = f'sag "{text}"'
        if voice: cmd += f' --voice "{voice}"'
        return run_command(cmd, timeout=30)
    key = api_key or _env("ELEVENLABS_API_KEY")
    if key:
        try:
            vid = voice or "21m00Tcm4TlvDq8ikWAM"
            r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
                headers={"xi-api-key":key,"Content-Type":"application/json"},
                json={"text":text,"model_id":"eleven_monolingual_v1"}, timeout=30)
            if r.status_code == 200:
                fname = f"/tmp/nexum_tts_{uuid.uuid4().hex[:6]}.mp3"
                with open(fname,"wb") as f: f.write(r.content)
                return f"✅ TTS saved: {fname}"
            return f"Error: {r.status_code} {r.text}"
        except Exception as e: return f"Error: {e}"
    return "❌ sag CLI not installed and ELEVENLABS_API_KEY not set"

def skill_creator(op: str, skill_name: str = "", content: str = "") -> str:
    skills_dir = Path.home() / ".nexum" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    if op == "list":
        return "\n".join(d.name for d in skills_dir.iterdir() if d.is_dir()) or "(no skills)"
    elif op == "create":
        skill_dir = skills_dir / skill_name; skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content or f"# {skill_name}\n\nSkill description here.")
        return f"✅ Skill created: {skill_dir}"
    elif op == "read":
        md = skills_dir / skill_name / "SKILL.md"
        return md.read_text() if md.exists() else f"❌ Not found: {skill_name}"
    elif op == "delete":
        sd = skills_dir / skill_name
        if sd.exists(): shutil.rmtree(sd); return f"✅ Deleted: {skill_name}"
        return f"❌ Not found: {skill_name}"
    return f"❌ Unknown op: {op}"

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN AGENT LOOP
# ═══════════════════════════════════════════════════════════════════════════════

async def agent_loop():
    global UID
    reconnect_delay = 2
    linked   = UID is not None
    identity = detect_identity()

    while True:
        try:
            print(f"\n🔌 Connecting → {SERVER_URL}")
            async with websockets.connect(SERVER_URL, ping_interval=25, ping_timeout=10) as ws:
                reconnect_delay = 2

                if linked and UID:
                    await ws.send(json.dumps({
                        "type": "register", "uid": UID, "device_id": DEVICE_ID,
                        "name": socket.gethostname(), "platform": get_platform(),
                        "version": AGENT_VERSION, "identity": identity,
                        "sysinfo": {"cpu": psutil.cpu_count(), "os": platform.system(), "ram_gb": psutil.virtual_memory().total//1024**3},
                    }))
                    print(f"✅ Registered — uid={UID}")
                else:
                    await ws.send(json.dumps({
                        "type": "request_link", "device_id": DEVICE_ID,
                        "platform": get_platform(), "identity": identity,
                    }))
                    print("⏳ Ожидаю привязки — получи код от бота...")

                # Heartbeat
                async def heartbeat():
                    while True:
                        await asyncio.sleep(20)
                        try: await ws.send(json.dumps({"type":"ping"}))
                        except: break

                hb = asyncio.create_task(heartbeat())

                async def reply(req_id: str, data):
                    if isinstance(data, (dict, list)): data = json.dumps(data, ensure_ascii=False)
                    await ws.send(json.dumps({"type":"result","reqId":req_id,"data":str(data)[:4000]}))

                try:
                    async for raw in ws:
                        msg   = json.loads(raw)
                        mtype = msg.get("type")
                        rid   = msg.get("reqId","")

                        # ── Linking ──────────────────────────────────────────
                        if mtype == "link_code":
                            code = msg.get("code")
                            print(f"\n{'='*50}\n  🔑 КОД ПРИВЯЗКИ: {code}\n  Отправь боту: /link {code}\n{'='*50}\n")

                        elif mtype == "linked":
                            UID    = msg.get("uid")
                            linked = True
                            save_config()
                            print(f"\n✅ Привязан uid={UID}  (сохранено в {CONFIG_FILE})")
                            print("   При следующем запуске привязка будет автоматической\n")

                        elif mtype == "registered":
                            print("✅ Agent active — ожидаю команды от NEXUM Bot")

                        elif mtype == "pong":
                            pass  # keepalive

                        # ══ СИСТЕМНЫЕ ════════════════════════════════════════
                        elif mtype == "screenshot":
                            print("📸 Screenshot...")
                            region = msg.get("region")
                            b64 = take_screenshot(tuple(region) if region else None)
                            await ws.send(json.dumps({"type":"screenshot_result","reqId":rid,"chatId":msg.get("chatId"),"data":b64 or ""}))

                        elif mtype == "run":
                            cmd = msg.get("command","")
                            print(f"⚙️  Run: {cmd[:60]}")
                            await reply(rid, run_command(cmd, msg.get("timeout",60), msg.get("cwd")))

                        elif mtype == "run_background":
                            await reply(rid, run_background(msg.get("command","")))

                        elif mtype == "bg_list":    await reply(rid, list_bg())
                        elif mtype == "bg_stop":    await reply(rid, stop_bg(msg.get("proc_id","")))
                        elif mtype == "sysinfo":    await reply(rid, get_sysinfo())
                        elif mtype == "processes":  await reply(rid, get_processes(msg.get("limit",15)))
                        elif mtype == "kill_process": await reply(rid, kill_process(msg.get("input","")))
                        elif mtype == "network":    await reply(rid, get_network_info())
                        elif mtype == "identity":   await reply(rid, json.dumps(detect_identity(), ensure_ascii=False))

                        elif mtype == "filesystem":
                            await reply(rid, filesystem_op(msg.get("op","read"), msg.get("path",""), msg.get("content","")))

                        elif mtype == "clipboard":
                            await reply(rid, clipboard_op(msg.get("op","read"), msg.get("text","")))

                        elif mtype == "notify":
                            await reply(rid, send_notification(msg.get("title","NEXUM"), msg.get("message",""), msg.get("timeout",5)))

                        elif mtype == "window":
                            await reply(rid, window_op(msg.get("op","list"), msg.get("window_id","")))

                        elif mtype == "http":
                            print(f"🌐 HTTP {msg.get('method','GET')} {msg.get('url','')[:60]}")
                            await reply(rid, http_request(msg.get("method","GET"), msg.get("url",""), msg.get("body",""), msg.get("headers","")))

                        elif mtype == "browser":    await reply(rid, open_browser(msg.get("input","")))
                        elif mtype == "open_app":   await reply(rid, open_application(msg.get("input","")))

                        elif mtype == "mouse":
                            await reply(rid, mouse_control(msg.get("action","position"), int(msg.get("x",0)), int(msg.get("y",0)), msg.get("text","")))

                        elif mtype == "keyboard":
                            await reply(rid, mouse_control(msg.get("action","type"), 0, 0, msg.get("text","")))

                        # ══ OPENCLAW SKILLS ═══════════════════════════════════
                        elif mtype == "weather":
                            await reply(rid, weather(msg.get("location",""), msg.get("mode","current")))

                        elif mtype == "github":
                            await reply(rid, github(msg.get("subcmd","")))

                        elif mtype == "google_workspace":
                            await reply(rid, google_workspace(msg.get("subcmd","")))

                        elif mtype == "notion":
                            await reply(rid, notion(msg.get("method","GET"), msg.get("endpoint",""), msg.get("body",""), msg.get("api_key","")))

                        elif mtype == "obsidian":
                            await reply(rid, obsidian(msg.get("op","list"), msg.get("path",""), msg.get("content","")))

                        elif mtype == "apple_notes":
                            await reply(rid, apple_notes(msg.get("op","list"), msg.get("arg","")))

                        elif mtype == "apple_reminders":
                            await reply(rid, apple_reminders(msg.get("op","list"), msg.get("arg","")))

                        elif mtype == "trello":
                            await reply(rid, trello(msg.get("op","boards"), msg.get("arg",""), msg.get("body")))

                        elif mtype == "slack":
                            await reply(rid, slack(msg.get("op","channels"), msg.get("channel",""), msg.get("text","")))

                        elif mtype == "discord":
                            await reply(rid, discord(msg.get("op","history"), msg.get("channel_id",""), msg.get("text","")))

                        elif mtype == "spotify":
                            await reply(rid, spotify(msg.get("op","status"), msg.get("arg","")))

                        elif mtype == "tmux":
                            await reply(rid, tmux(msg.get("op","list"), msg.get("session","main"), msg.get("pane",""), msg.get("keys","")))

                        elif mtype == "video_frames":
                            await reply(rid, video_frames(msg.get("path",""), msg.get("op","frame"), msg.get("time","00:00:01"), msg.get("out","")))

                        elif mtype == "whisper":
                            await reply(rid, whisper_transcribe(msg.get("path",""), msg.get("model","base"), msg.get("api_key","")))

                        elif mtype == "image_gen":
                            await reply(rid, openai_image_gen(msg.get("prompt",""), msg.get("model","dall-e-3"), msg.get("size","1024x1024"), msg.get("api_key","")))

                        elif mtype == "gemini":
                            await reply(rid, gemini_query(msg.get("prompt",""), msg.get("api_key","")))

                        elif mtype == "summarize":
                            await reply(rid, summarize(msg.get("target","")))

                        elif mtype == "himalaya":
                            await reply(rid, himalaya(msg.get("subcmd","envelope list")))

                        elif mtype == "onepassword":
                            await reply(rid, onepassword(msg.get("subcmd","item list")))

                        elif mtype == "coding_agent":
                            await reply(rid, coding_agent(msg.get("prompt",""), msg.get("agent","auto"), msg.get("dir","")))

                        elif mtype == "healthcheck":
                            await reply(rid, healthcheck(msg.get("url",""), msg.get("method","GET")))

                        elif mtype == "openhue":
                            await reply(rid, openhue(msg.get("subcmd","lights list")))

                        elif mtype == "sag_tts":
                            await reply(rid, sag_tts(msg.get("text",""), msg.get("voice",""), msg.get("api_key","")))

                        elif mtype == "skill_creator":
                            await reply(rid, skill_creator(msg.get("op","list"), msg.get("skill_name",""), msg.get("content","")))

                        else:
                            if mtype not in ("pong",): print(f"⚠️  Unknown message type: {mtype}")

                finally:
                    hb.cancel()

        except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            print(f"⚠️  Disconnected: {e}. Retry in {reconnect_delay}s...")
        except Exception as e:
            print(f"❌ Error: {e}. Retry in {reconnect_delay}s...")

        await asyncio.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, 30)

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print(f"  NEXUM PC Agent v{AGENT_VERSION}")
    print("=" * 60)

    if len(sys.argv) > 1:
        SERVER_URL = sys.argv[1]

    load_config()
    ident = detect_identity()

    print(f"  Device   : {DEVICE_ID}")
    print(f"  OS User  : {ident['os_user']}  @  {ident['hostname']}")
    print(f"  Platform : {ident['platform']}")
    print(f"  Server   : {SERVER_URL}")
    if UID:
        print(f"  UID      : {UID}  ← вшит в {CONFIG_FILE}")
    else:
        print(f"  Status   : Не привязан — ожидай код привязки")
    print("=" * 60)
    print()
    print("СИСТЕМНЫЕ: screenshot · mouse/keyboard · terminal · filesystem")
    print("           clipboard · notifications · windows · http · sysinfo")
    print()
    print("OPENCLAW : weather · github · google-workspace · notion · obsidian")
    print("           trello · slack · discord · spotify · tmux · video-frames")
    print("           whisper · image-gen · gemini · summarize · himalaya")
    print("           1password · coding-agent · healthcheck · openhue · sag-tts")
    print()

    try:
        asyncio.run(agent_loop())
    except KeyboardInterrupt:
        print("\n👋 NEXUM Agent stopped.")
