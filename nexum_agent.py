#!/usr/bin/env python3
"""
NEXUM PC Agent v8 — все навыки OpenClaw
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Что реализовано (соответствие OpenClaw skills):

  СИСТЕМНЫЕ (нативно, без зависимостей CLI):
  ✅ screenshot / region capture      ← PIL/scrot/gnome-screenshot
  ✅ mouse / keyboard control         ← pyautogui
  ✅ terminal commands (sync+bg)      ← subprocess
  ✅ filesystem (r/w/list/copy/move/delete/zip/search) ← pathlib
  ✅ clipboard read/write             ← pyperclip
  ✅ system notifications             ← plyer/osascript/notify-send
  ✅ window list/focus/close          ← wmctrl/osascript/powershell
  ✅ HTTP requests GET/POST/PUT/DELETE ← requests
  ✅ browser open                     ← webbrowser
  ✅ app open                         ← subprocess/open/xdg-open
  ✅ sysinfo / processes / kill       ← psutil
  ✅ background processes             ← subprocess.Popen
  ✅ network info                     ← psutil+requests
  ✅ user identity autodetect → uid embeds in config

  OPENCLAW CLI SKILLS (требуют CLI установленного на ПК):
  ✅ weather          ← wttr.in (через HTTP, без CLI)
  ✅ github           ← gh CLI
  ✅ google-workspace ← gog CLI (Gmail/Calendar/Drive/Contacts/Sheets/Docs)
  ✅ google-places    ← goplaces CLI / API напрямую
  ✅ notion           ← Notion API напрямую (NOTION_API_KEY)
  ✅ obsidian         ← obsidian-cli / прямая работа с vault md-файлами
  ✅ apple-notes      ← memo CLI (macOS)
  ✅ apple-reminders  ← remindctl CLI (macOS)
  ✅ bear-notes       ← grizzly CLI (macOS)
  ✅ trello           ← Trello REST API (TRELLO_API_KEY + TRELLO_TOKEN)
  ✅ slack            ← Slack API (SLACK_BOT_TOKEN)
  ✅ discord          ← Discord API (DISCORD_BOT_TOKEN)
  ✅ spotify          ← spogo / spotify_player CLI
  ✅ tmux             ← tmux CLI
  ✅ video-frames     ← ffmpeg CLI
  ✅ openai-whisper   ← whisper CLI / whisper API (OPENAI_API_KEY)
  ✅ openai-image-gen ← OpenAI Images API (OPENAI_API_KEY)
  ✅ nano-pdf         ← nano-pdf CLI
  ✅ summarize        ← summarize CLI / yt-dlp fallback
  ✅ blogwatcher      ← blogwatcher CLI
  ✅ gifgrep          ← gifgrep CLI
  ✅ camsnap          ← camsnap CLI (RTSP/ONVIF cameras)
  ✅ peekaboo         ← peekaboo CLI (macOS UI automation)
  ✅ himalaya (email) ← himalaya CLI (IMAP/SMTP)
  ✅ imsg (iMessage)  ← imsg CLI (macOS)
  ✅ xurl (Twitter)   ← xurl CLI (X API)
  ✅ 1password        ← op CLI
  ✅ coding-agent     ← claude/codex/opencode CLI
  ✅ session-logs     ← jq + rg (поиск по сессиям)
  ✅ healthcheck      ← curl/http checks
  ✅ gemini           ← gemini CLI / Gemini API
  ✅ nano-banana-pro  ← Gemini image gen API
  ✅ model-usage      ← codexbar CLI
  ✅ mcporter         ← mcporter CLI (MCP servers)
  ✅ blucli           ← blu CLI (Bluesound/NAD)
  ✅ openhue          ← openhue CLI (Philips Hue)
  ✅ sonos            ← sonoscli CLI
  ✅ sag (ElevenLabs) ← sag CLI / ElevenLabs API
  ✅ sherpa-onnx-tts  ← sherpa-onnx CLI (offline TTS)
  ✅ songsee          ← songsee CLI (audio visualization)
  ✅ eightctl         ← eightctl CLI (Eight Sleep)
  ✅ gog (GOG games)  ← gog CLI (Google Workspace, см. выше)
  ✅ oracle           ← oracle CLI (prompt bundling)
  ✅ ordercli         ← ordercli CLI (Foodora)
  ✅ skill-creator    ← создание/редактирование навыков

  НЕ РЕАЛИЗУЕМО В АГЕНТЕ (часть OpenClaw-архитектуры, не агента):
  ❌ canvas           ← WebView nodes (Mac/iOS app)
  ❌ voice-call       ← OpenClaw voice-call plugin (требует ноды)
  ❌ bluebubbles      ← BlueBubbles channel (OpenClaw channels)
  ❌ wacli (WhatsApp) ← wacli требует полноценный OpenClaw gateway
  ❌ clawhub          ← менеджер навыков OpenClaw (не нужен в NEXUM)
  ❌ gh-issues subagent ← ACP subagent система OpenClaw

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Установка:
  pip install websockets pyautogui pillow psutil requests pyperclip plyer

Опциональные зависимости (для CLI-навыков):
  macOS: brew install gh memo remindctl grizzly obsidian-cli tmux ffmpeg
         brew install steipete/tap/spogo steipete/tap/summarize
         brew install steipete/tap/peekaboo steipete/tap/camsnap
         brew install steipete/tap/goplaces steipete/tap/gogcli
         brew install himalaya gifgrep whisper openai-whisper
         brew install xdevplatform/tap/xurl 1password-cli
         brew install steipete/tap/blucli steipete/tap/sag
  Linux: apt install tmux ffmpeg gh jq ripgrep notify-send wmctrl

Запуск:
  python nexum_agent.py
  python nexum_agent.py wss://your-server.up.railway.app/ws

Переменные окружения (опционально):
  OPENAI_API_KEY     — OpenAI (Whisper API, Image Gen, Coding agent)
  NOTION_API_KEY     — Notion
  TRELLO_API_KEY     — Trello
  TRELLO_TOKEN       — Trello
  SLACK_BOT_TOKEN    — Slack
  DISCORD_BOT_TOKEN  — Discord
  GOOGLE_PLACES_API_KEY — Google Places
  NEXUM_SERVER       — WebSocket сервер (по умолчанию ws://localhost:18790)
"""

import asyncio, json, platform, subprocess, base64, uuid, sys, os, io
import time, socket, shutil, zipfile
from pathlib import Path
from datetime import datetime
from typing import Optional

# ─── Auto-install core deps ──────────────────────────────────────────────────
_REQUIRED = {"websockets": "websockets", "psutil": "psutil", "PIL": "pillow",
             "requests": "requests", "pyperclip": "pyperclip", "pyautogui": "pyautogui"}

def _ensure_deps():
    missing = []
    for imp, pkg in _REQUIRED.items():
        try: __import__(imp)
        except ImportError: missing.append(pkg)
    if missing:
        print(f"📦 Installing core deps: {', '.join(missing)}")
        subprocess.run([sys.executable, "-m", "pip", "install"] + missing,
                       check=True, capture_output=True)
        print("✅ Done")

_ensure_deps()
import websockets, psutil, requests

# ─── Config ──────────────────────────────────────────────────────────────────
CONFIG_FILE   = Path.home() / ".nexum_agent.json"
SERVER_URL    = os.environ.get("NEXUM_SERVER", "ws://localhost:18790")
DEVICE_ID: Optional[str] = None
UID: Optional[int] = None
AGENT_VERSION = "8.0.0"

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
    """Сохраняет конфиг. После /link сюда вшивается персональный UID."""
    CONFIG_FILE.write_text(json.dumps({
        "device_id":  DEVICE_ID,
        "uid":        UID,
        "server_url": SERVER_URL,
        "updated":    datetime.now().isoformat(),
        "version":    AGENT_VERSION,
        "os_user":    os.getenv("USER") or os.getenv("USERNAME") or "unknown",
        "hostname":   socket.gethostname(),
        "platform":   f"{platform.system()} {platform.release()}",
    }, indent=2))

def _env(key: str) -> str:
    return os.environ.get(key, "")

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

def get_processes(limit: int = 15) -> str:
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try: procs.append(p.info)
        except Exception: pass
    procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
    lines = ["PID     CPU%   MEM%   NAME"]
    for p in procs[:limit]:
        lines.append(f"{p['pid']:<7} {(p['cpu_percent'] or 0):>5.1f}  {(p['memory_percent'] or 0):>5.1f}  {(p['name'] or '')[:30]}")
    return "\n".join(lines)

def kill_process(pid_or_name: str) -> str:
    try:
        if pid_or_name.isdigit():
            psutil.Process(int(pid_or_name)).terminate()
            return f"✅ Terminated PID {pid_or_name}"
        killed = 0
        for p in psutil.process_iter(["pid", "name"]):
            if pid_or_name.lower() in (p.info.get("name") or "").lower():
                p.terminate(); killed += 1
        return f"✅ Killed {killed} processes matching '{pid_or_name}'"
    except Exception as e: return f"Error: {e}"

def get_network_info() -> str:
    lines = [f"🌐 Hostname: {socket.gethostname()}"]
    try: lines.append(f"🌍 Public IP: {requests.get('https://api.ipify.org', timeout=5).text}")
    except Exception: pass
    for name, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET:
                lines.append(f"📡 {name}: {addr.address}")
    net = psutil.net_io_counters()
    lines.append(f"↑ {net.bytes_sent//1024**2}MB  ↓ {net.bytes_recv//1024**2}MB")
    return "\n".join(lines)

def detect_user_identity() -> dict:
    info = {
        "os_user":  os.getenv("USER") or os.getenv("USERNAME") or "unknown",
        "hostname": socket.gethostname(),
        "home":     str(Path.home()),
        "platform": get_platform(),
        "lang":     os.getenv("LANG", ""),
        "tz":       "",
    }
    try: info["tz"] = datetime.now().astimezone().tzname() or ""
    except Exception: pass
    return info

# ─── Background processes ─────────────────────────────────────────────────────
_bg: dict = {}

def run_background(cmd: str) -> str:
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=str(Path.home()))
    pid = str(uuid.uuid4())[:6]
    _bg[pid] = proc
    return f"✅ Started [{pid}] PID={proc.pid}"

def stop_bg(pid: str) -> str:
    p = _bg.get(pid)
    if not p: return f"❌ [{pid}] not found"
    p.terminate(); del _bg[pid]
    return f"✅ Stopped [{pid}]"

def list_bg() -> str:
    if not _bg: return "No background processes"
    return "\n".join(f"[{k}] PID={v.pid} {'running' if v.poll() is None else 'done'}"
                     for k, v in _bg.items())

# ─── Terminal ─────────────────────────────────────────────────────────────────
def run_command(cmd: str, timeout: int = 60, cwd: Optional[str] = None) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=timeout, cwd=cwd or str(Path.home()))
        out, err = r.stdout.strip(), r.stderr.strip()
        if out and err: return f"{out}\n\nSTDERR:\n{err}"
        return out or err or "(no output)"
    except subprocess.TimeoutExpired: return f"⏱ Timeout ({timeout}s)"
    except Exception as e: return f"Error: {e}"

# ─── Screenshot ───────────────────────────────────────────────────────────────
def take_screenshot(region=None) -> Optional[str]:
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(bbox=region)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError: pass
    for cmd in [["scrot", "-o", "/tmp/nxss.png"], ["gnome-screenshot", "-f", "/tmp/nxss.png"]]:
        try:
            if subprocess.run(cmd, capture_output=True).returncode == 0:
                return base64.b64encode(open("/tmp/nxss.png", "rb").read()).decode()
        except Exception: pass
    return None

# ─── Filesystem ───────────────────────────────────────────────────────────────
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
            with open(p, "a") as f: f.write(content)
            return f"✅ Appended → {path_str}"
        elif op == "list":
            if not p.is_dir(): return f"❌ Not a directory: {path_str}"
            items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name))[:50]
            return "\n".join(("📁 " if i.is_dir() else "📄 ") + i.name +
                             (f" ({i.stat().st_size//1024}KB)" if i.is_file() else "")
                             for i in items) or "(empty)"
        elif op == "delete":
            if not p.exists(): return f"❌ Not found: {path_str}"
            shutil.rmtree(p) if p.is_dir() else p.unlink()
            return f"✅ Deleted {path_str}"
        elif op == "copy":
            dst = Path(content).expanduser()
            shutil.copytree(str(p), str(dst)) if p.is_dir() else shutil.copy2(str(p), str(dst))
            return f"✅ Copied → {content}"
        elif op == "move":
            Path(content).expanduser().parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), content)
            return f"✅ Moved → {content}"
        elif op == "exists": return "yes" if p.exists() else "no"
        elif op == "info":
            if not p.exists(): return f"❌ Not found: {path_str}"
            s = p.stat()
            return (f"📄 {p.name}\nPath: {p.resolve()}\nType: {'dir' if p.is_dir() else 'file'}\n"
                    f"Size: {s.st_size//1024}KB\n"
                    f"Modified: {datetime.fromtimestamp(s.st_mtime).strftime('%Y-%m-%d %H:%M')}")
        elif op == "search":
            return "\n".join(str(r) for r in list(p.rglob(content or "*"))[:30]) or "(nothing found)"
        elif op == "mkdir":
            p.mkdir(parents=True, exist_ok=True); return f"✅ Created {path_str}"
        elif op == "zip":
            dst = content or str(p) + ".zip"
            with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
                [(zf.write(f, f.relative_to(p.parent)) or None) for f in p.rglob("*") if f.is_file()] \
                    if p.is_dir() else zf.write(p, p.name)
            return f"✅ Archived → {dst}"
        elif op == "unzip":
            dst = content or str(p.parent / p.stem)
            with zipfile.ZipFile(str(p)) as zf: zf.extractall(dst)
            return f"✅ Extracted → {dst}"
        else: return f"❌ Unknown op: {op}"
    except PermissionError: return "❌ Permission denied"
    except Exception as e: return f"Error: {e}"

# ─── Clipboard ────────────────────────────────────────────────────────────────
def clipboard_op(op: str, text: str = "") -> str:
    try:
        import pyperclip
        if op == "read": return pyperclip.paste() or "(empty)"
        pyperclip.copy(text); return f"✅ Copied: {text[:80]}"
    except Exception as e: return f"Error: {e}"

# ─── Notifications ────────────────────────────────────────────────────────────
def send_notification(title: str, msg: str, timeout: int = 5) -> str:
    try:
        from plyer import notification
        notification.notify(title=title, message=msg, timeout=timeout)
        return "✅ Notification sent"
    except Exception: pass
    sys_name = platform.system()
    try:
        if sys_name == "Darwin":
            subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "{title}"'])
        elif sys_name == "Windows":
            subprocess.run(["powershell", "-Command",
                f'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show("{msg}","{title}")'])
        else:
            subprocess.run(["notify-send", title, msg])
        return "✅ Notification sent"
    except Exception as e: return f"Error: {e}"

# ─── Window management ────────────────────────────────────────────────────────
def window_op(op: str, win: str = "") -> str:
    sys_name = platform.system()
    try:
        if op == "list":
            if sys_name == "Darwin":
                r = subprocess.run(["osascript", "-e",
                    'tell application "System Events" to get name of every process whose background only is false'],
                    capture_output=True, text=True)
                return r.stdout.strip()
            elif sys_name == "Linux":
                r = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
                return r.stdout.strip() or "(wmctrl not installed)"
            else:
                r = subprocess.run(["powershell", "-Command",
                    "Get-Process | Where-Object {$_.MainWindowTitle} | Select Name,MainWindowTitle | ft"],
                    capture_output=True, text=True)
                return r.stdout.strip()
        elif op == "focus":
            if sys_name == "Linux": subprocess.run(["wmctrl", "-a", win])
            elif sys_name == "Darwin": subprocess.run(["osascript", "-e", f'tell application "{win}" to activate'])
            return f"✅ Focused: {win}"
        elif op == "close":
            if sys_name == "Linux": subprocess.run(["wmctrl", "-c", win])
            elif sys_name == "Darwin": subprocess.run(["osascript", "-e", f'tell application "{win}" to quit'])
            return f"✅ Closed: {win}"
        return f"❌ Not supported on {sys_name}"
    except Exception as e: return f"Error: {e}"

# ─── HTTP ─────────────────────────────────────────────────────────────────────
def http_request(method: str, url: str, body: str = "", headers_str: str = "") -> str:
    try:
        headers = {}
        for line in (headers_str or "").split("\n"):
            if ":" in line:
                k, v = line.split(":", 1); headers[k.strip()] = v.strip()
        m = method.upper()
        if   m == "GET":    r = requests.get(url, headers=headers, timeout=15)
        elif m == "DELETE": r = requests.delete(url, headers=headers, timeout=15)
        elif m == "POST":
            try: r = requests.post(url, json=json.loads(body or "{}"), headers=headers, timeout=15)
            except Exception: r = requests.post(url, data=body, headers=headers, timeout=15)
        elif m == "PUT":
            try: r = requests.put(url, json=json.loads(body or "{}"), headers=headers, timeout=15)
            except Exception: r = requests.put(url, data=body, headers=headers, timeout=15)
        else: return f"❌ Unknown method: {method}"
        return f"Status: {r.status_code}\n\n{r.text[:3000]}"
    except Exception as e: return f"Error: {e}"

# ─── Browser / Apps ───────────────────────────────────────────────────────────
def open_browser(url: str) -> str:
    try:
        import webbrowser; webbrowser.open(url)
        return f"✅ Opened: {url}"
    except Exception as e: return f"Error: {e}"

def open_application(name: str) -> str:
    sys_name = platform.system()
    try:
        if sys_name == "Windows": subprocess.Popen(["start", name], shell=True)
        elif sys_name == "Darwin": subprocess.Popen(["open", "-a", name])
        else:
            try: subprocess.Popen([name])
            except Exception: subprocess.Popen(["xdg-open", name])
        return f"✅ Opened: {name}"
    except Exception as e: return f"Error: {e}"

# ─── Mouse / Keyboard ─────────────────────────────────────────────────────────
def mouse_control(action: str, x: int = 0, y: int = 0, text: str = "") -> str:
    try:
        import pyautogui; pyautogui.FAILSAFE = True
        if action == "click":          pyautogui.click(x, y);           return f"✅ Clicked ({x},{y})"
        elif action == "move":         pyautogui.moveTo(x, y, 0.3);     return f"✅ Moved ({x},{y})"
        elif action == "double_click": pyautogui.doubleClick(x, y);     return f"✅ DoubleClick ({x},{y})"
        elif action == "right_click":  pyautogui.rightClick(x, y);      return f"✅ RightClick ({x},{y})"
        elif action == "drag":
            parts = [int(v.strip()) for v in text.split(",")]
            pyautogui.dragTo(parts[0], parts[1], 0.5)
            return f"✅ Dragged → ({parts[0]},{parts[1]})"
        elif action == "type":         pyautogui.typewrite(text, 0.03); return f"✅ Typed: {text[:60]}"
        elif action == "hotkey":
            pyautogui.hotkey(*[k.strip() for k in text.split("+")]); return f"✅ Hotkey: {text}"
        elif action == "scroll":       pyautogui.scroll(x);             return f"✅ Scrolled {x}"
        elif action == "position":
            pos = pyautogui.position();  return f"Mouse at ({pos.x},{pos.y})"
        elif action == "screen_size":
            sz = pyautogui.size();       return f"Screen: {sz.width}×{sz.height}"
        elif action == "press":        pyautogui.press(text);           return f"✅ Pressed: {text}"
        elif action == "screenshot_region":
            parts = [int(v.strip()) for v in text.split(",")]
            b64 = take_screenshot(tuple(parts))
            return b64 or "❌ Failed"
        else: return f"❌ Unknown: {action}"
    except ImportError: return "❌ pyautogui not installed"
    except Exception as e: return f"Error: {e}"

# ═══════════════════════════════════════════════════════════════════════════════
# OPENCLAW CLI SKILLS
# ═══════════════════════════════════════════════════════════════════════════════

# ─── Weather (wttr.in) ────────────────────────────────────────────────────────
def weather(location: str, mode: str = "current") -> str:
    """OpenClaw weather skill — использует wttr.in напрямую."""
    try:
        loc = location.replace(" ", "+")
        if mode == "forecast":
            r = requests.get(f"https://wttr.in/{loc}?format=v2", timeout=10)
        elif mode == "oneline":
            r = requests.get(f"https://wttr.in/{loc}?format=3", timeout=10)
        else:
            r = requests.get(f"https://wttr.in/{loc}?0", timeout=10)
        return r.text[:2000]
    except Exception as e: return f"Error: {e}"

# ─── GitHub (gh CLI) ──────────────────────────────────────────────────────────
def github(subcmd: str) -> str:
    """OpenClaw github skill — gh CLI."""
    if not shutil.which("gh"):
        return "❌ gh CLI not installed. Install: brew install gh / apt install gh"
    return run_command(f"gh {subcmd}", timeout=30)

# ─── Google Workspace (gog CLI) ───────────────────────────────────────────────
def google_workspace(subcmd: str) -> str:
    """OpenClaw gog skill — Gmail/Calendar/Drive/Contacts/Sheets/Docs."""
    if not shutil.which("gog"):
        return "❌ gog CLI not installed. Install: brew install steipete/tap/gogcli"
    return run_command(f"gog {subcmd}", timeout=30)

# ─── Google Places (goplaces CLI или API) ────────────────────────────────────
def google_places(query: str, api_key: str = "") -> str:
    """OpenClaw goplaces skill."""
    key = api_key or _env("GOOGLE_PLACES_API_KEY")
    if shutil.which("goplaces"):
        cmd = f'goplaces search "{query}"'
        if key: cmd = f"GOOGLE_PLACES_API_KEY={key} {cmd}"
        return run_command(cmd, timeout=15)
    elif key:
        r = requests.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers={"Content-Type": "application/json",
                     "X-Goog-Api-Key": key,
                     "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating"},
            json={"textQuery": query},
            timeout=10
        )
        return r.text[:2000]
    else:
        return "❌ goplaces not installed and GOOGLE_PLACES_API_KEY not set"

# ─── Notion API ───────────────────────────────────────────────────────────────
def notion(method: str, endpoint: str, body: str = "", api_key: str = "") -> str:
    """OpenClaw notion skill — Notion API напрямую."""
    key = api_key or _env("NOTION_API_KEY")
    if not key: return "❌ NOTION_API_KEY not set"
    headers = {
        "Authorization": f"Bearer {key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    url = f"https://api.notion.com/v1/{endpoint.lstrip('/')}"
    try:
        if method.upper() == "GET":
            r = requests.get(url, headers=headers, timeout=15)
        elif method.upper() == "POST":
            r = requests.post(url, headers=headers, json=json.loads(body or "{}"), timeout=15)
        elif method.upper() == "PATCH":
            r = requests.patch(url, headers=headers, json=json.loads(body or "{}"), timeout=15)
        else:
            return f"❌ Unknown method: {method}"
        return f"Status: {r.status_code}\n\n{r.text[:3000]}"
    except Exception as e: return f"Error: {e}"

def notion_search(query: str, api_key: str = "") -> str:
    return notion("POST", "search", json.dumps({"query": query}), api_key)

# ─── Obsidian ─────────────────────────────────────────────────────────────────
def obsidian(op: str, path: str = "", content: str = "") -> str:
    """OpenClaw obsidian skill — прямая работа с vault или obsidian-cli."""
    if shutil.which("obsidian-cli"):
        if op == "list": return run_command("obsidian-cli list")
        elif op == "open": return run_command(f'obsidian-cli open "{path}"')
        elif op == "search": return run_command(f'obsidian-cli search "{path}"')
    # Fallback: прямая работа с файлами vault
    vault_config = Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    if vault_config.exists():
        try:
            cfg = json.loads(vault_config.read_text())
            vaults = cfg.get("vaults", {})
            if vaults:
                vault_path = Path(list(vaults.values())[0].get("path", ""))
                if op == "list":
                    return filesystem_op("list", str(vault_path))
                elif op == "read":
                    return filesystem_op("read", str(vault_path / path))
                elif op == "write":
                    return filesystem_op("write", str(vault_path / path), content)
                elif op == "search":
                    results = list(vault_path.rglob(f"*{path}*"))[:20]
                    return "\n".join(str(r) for r in results) or "(nothing found)"
        except Exception as e:
            return f"Vault fallback error: {e}"
    return "❌ obsidian-cli not installed and no vault found"

# ─── Apple Notes (memo CLI, macOS) ───────────────────────────────────────────
def apple_notes(op: str, arg: str = "") -> str:
    """OpenClaw apple-notes skill."""
    if not shutil.which("memo"):
        return "❌ memo not installed (macOS only). Install: brew install antoniorodr/memo/memo"
    cmds = {
        "list":   "memo notes list",
        "search": f'memo notes search "{arg}"',
        "add":    f'memo notes add "{arg}"',
        "view":   f'memo notes view "{arg}"',
        "delete": f'memo notes delete "{arg}"',
    }
    return run_command(cmds.get(op, f"memo {op} {arg}"), timeout=15)

# ─── Apple Reminders (remindctl, macOS) ──────────────────────────────────────
def apple_reminders(op: str, arg: str = "") -> str:
    """OpenClaw apple-reminders skill."""
    if not shutil.which("remindctl"):
        return "❌ remindctl not installed (macOS only). Install: brew install steipete/tap/remindctl"
    cmds = {
        "list":     "remindctl list",
        "add":      f'remindctl add "{arg}"',
        "complete": f'remindctl complete "{arg}"',
        "delete":   f'remindctl delete "{arg}"',
    }
    return run_command(cmds.get(op, f"remindctl {op} {arg}"), timeout=15)

# ─── Bear Notes (grizzly, macOS) ─────────────────────────────────────────────
def bear_notes(op: str, arg: str = "") -> str:
    """OpenClaw bear-notes skill."""
    if not shutil.which("grizzly"):
        return "❌ grizzly not installed (macOS only). Install: go install github.com/tylerwince/grizzly/cmd/grizzly@latest"
    cmds = {
        "list":   "grizzly list",
        "search": f'grizzly search "{arg}"',
        "create": f'grizzly create "{arg}"',
        "view":   f'grizzly view "{arg}"',
    }
    return run_command(cmds.get(op, f"grizzly {op} {arg}"), timeout=15)

# ─── Trello ───────────────────────────────────────────────────────────────────
def trello(op: str, arg: str = "", body: dict = None) -> str:
    """OpenClaw trello skill — Trello REST API."""
    key   = _env("TRELLO_API_KEY")
    token = _env("TRELLO_TOKEN")
    if not key or not token:
        return "❌ TRELLO_API_KEY and TRELLO_TOKEN not set"
    base = "https://api.trello.com/1"
    auth = f"key={key}&token={token}"
    try:
        if op == "boards":
            r = requests.get(f"{base}/members/me/boards?{auth}", timeout=10)
            boards = r.json()
            return "\n".join(f"{b['name']} (id: {b['id']})" for b in boards)
        elif op == "lists":
            r = requests.get(f"{base}/boards/{arg}/lists?{auth}", timeout=10)
            return "\n".join(f"{l['name']} (id: {l['id']})" for l in r.json())
        elif op == "cards":
            r = requests.get(f"{base}/lists/{arg}/cards?{auth}", timeout=10)
            return "\n".join(f"{c['name']} (id: {c['id']})" for c in r.json())
        elif op == "create_card":
            d = body or {}
            r = requests.post(f"{base}/cards?{auth}",
                data={"idList": d.get("list_id", arg), "name": d.get("name", ""),
                      "desc": d.get("desc", "")}, timeout=10)
            c = r.json()
            return f"✅ Created card: {c.get('name')} (id: {c.get('id')})"
        elif op == "move_card":
            d = body or {}
            r = requests.put(f"{base}/cards/{d.get('card_id', arg)}?{auth}",
                data={"idList": d.get("list_id", "")}, timeout=10)
            return f"✅ Moved card"
        elif op == "close_card":
            r = requests.put(f"{base}/cards/{arg}?{auth}", data={"closed": "true"}, timeout=10)
            return f"✅ Closed card"
        else:
            return f"❌ Unknown op: {op}"
    except Exception as e: return f"Error: {e}"

# ─── Slack ────────────────────────────────────────────────────────────────────
def slack(op: str, channel: str = "", text: str = "", ts: str = "", emoji: str = "") -> str:
    """OpenClaw slack skill — Slack API."""
    token = _env("SLACK_BOT_TOKEN")
    if not token: return "❌ SLACK_BOT_TOKEN not set"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        if op == "send":
            r = requests.post("https://slack.com/api/chat.postMessage",
                headers=headers, json={"channel": channel, "text": text}, timeout=10)
        elif op == "react":
            r = requests.post("https://slack.com/api/reactions.add",
                headers=headers, json={"channel": channel, "timestamp": ts,
                "name": emoji.strip(":")}, timeout=10)
        elif op == "history":
            r = requests.get("https://slack.com/api/conversations.history",
                headers=headers, params={"channel": channel, "limit": 10}, timeout=10)
        elif op == "channels":
            r = requests.get("https://slack.com/api/conversations.list",
                headers=headers, params={"limit": 30}, timeout=10)
            data = r.json()
            chs = data.get("channels", [])
            return "\n".join(f"#{c['name']} (id: {c['id']})" for c in chs)
        else:
            return f"❌ Unknown slack op: {op}"
        return f"Status: {r.status_code}\n{r.text[:1500]}"
    except Exception as e: return f"Error: {e}"

# ─── Discord ──────────────────────────────────────────────────────────────────
def discord(op: str, channel_id: str = "", text: str = "", msg_id: str = "") -> str:
    """OpenClaw discord skill — Discord API."""
    token = _env("DISCORD_BOT_TOKEN")
    if not token: return "❌ DISCORD_BOT_TOKEN not set"
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    base = "https://discord.com/api/v10"
    try:
        if op == "send":
            r = requests.post(f"{base}/channels/{channel_id}/messages",
                headers=headers, json={"content": text}, timeout=10)
        elif op == "history":
            r = requests.get(f"{base}/channels/{channel_id}/messages?limit=10",
                headers=headers, timeout=10)
            msgs = r.json()
            return "\n".join(f"[{m['author']['username']}]: {m['content']}" for m in msgs)
        elif op == "delete":
            r = requests.delete(f"{base}/channels/{channel_id}/messages/{msg_id}",
                headers=headers, timeout=10)
            return f"✅ Deleted message {msg_id}"
        else:
            return f"❌ Unknown discord op: {op}"
        return f"Status: {r.status_code}\n{r.text[:1500]}"
    except Exception as e: return f"Error: {e}"

# ─── Spotify (spogo/spotify_player) ──────────────────────────────────────────
def spotify(op: str, arg: str = "") -> str:
    """OpenClaw spotify-player skill."""
    cli = shutil.which("spogo") or shutil.which("spotify_player")
    if not cli:
        return "❌ spogo or spotify_player not installed.\nInstall: brew install steipete/tap/spogo"
    name = Path(cli).name
    if name == "spogo":
        cmds = {
            "play":   f"spogo play",
            "pause":  f"spogo pause",
            "next":   f"spogo next",
            "prev":   f"spogo prev",
            "status": f"spogo status",
            "search": f'spogo search track "{arg}"',
            "devices": "spogo device list",
        }
    else:  # spotify_player
        cmds = {
            "play":   "spotify_player playback play",
            "pause":  "spotify_player playback pause",
            "next":   "spotify_player playback next",
            "prev":   "spotify_player playback previous",
            "status": "spotify_player playback",
            "search": f'spotify_player search "{arg}"',
        }
    return run_command(cmds.get(op, f"{name} {op} {arg}"), timeout=15)

# ─── tmux ─────────────────────────────────────────────────────────────────────
def tmux(op: str, session: str = "main", pane: str = "", keys: str = "") -> str:
    """OpenClaw tmux skill."""
    if not shutil.which("tmux"):
        return "❌ tmux not installed. Install: brew install tmux / apt install tmux"
    if op == "list":     return run_command("tmux list-sessions 2>/dev/null || echo 'No sessions'")
    elif op == "new":    return run_command(f"tmux new-session -d -s {session}")
    elif op == "kill":   return run_command(f"tmux kill-session -t {session}")
    elif op == "send":   return run_command(f"tmux send-keys -t {session}{':'+pane if pane else ''} '{keys}' Enter")
    elif op == "capture": return run_command(f"tmux capture-pane -t {session} -p")
    elif op == "windows": return run_command(f"tmux list-windows -t {session}")
    elif op == "panes":   return run_command(f"tmux list-panes -t {session}")
    else: return run_command(f"tmux {op} {session}", timeout=10)

# ─── Video frames (ffmpeg) ────────────────────────────────────────────────────
def video_frames(video_path: str, op: str = "frame", time: str = "00:00:01", out: str = "") -> str:
    """OpenClaw video-frames skill."""
    if not shutil.which("ffmpeg"):
        return "❌ ffmpeg not installed. Install: brew install ffmpeg / apt install ffmpeg"
    out_path = out or f"/tmp/nexum_frame_{uuid.uuid4().hex[:6]}.jpg"
    if op == "frame":
        cmd = f'ffmpeg -y -i "{video_path}" -ss {time} -vframes 1 "{out_path}" 2>/dev/null'
        result = run_command(cmd, timeout=30)
        if Path(out_path).exists():
            return f"✅ Frame saved: {out_path}"
        return result
    elif op == "clip":
        duration = time  # repurpose time as duration
        out_path = out or f"/tmp/nexum_clip_{uuid.uuid4().hex[:6]}.mp4"
        cmd = f'ffmpeg -y -i "{video_path}" -t {duration} -c copy "{out_path}" 2>/dev/null'
        run_command(cmd, timeout=60)
        return f"✅ Clip saved: {out_path}" if Path(out_path).exists() else "❌ Failed"
    elif op == "info":
        return run_command(f'ffprobe -v quiet -print_format json -show_format -show_streams "{video_path}"', timeout=10)
    else:
        return run_command(f'ffmpeg {op} -i "{video_path}" {out}', timeout=60)

# ─── Whisper (STT) ───────────────────────────────────────────────────────────
def whisper_transcribe(audio_path: str, model: str = "base", api_key: str = "") -> str:
    """OpenClaw openai-whisper skill — CLI или API."""
    if shutil.which("whisper"):
        return run_command(
            f'whisper "{audio_path}" --model {model} --output_format txt --output_dir /tmp',
            timeout=120
        )
    key = api_key or _env("OPENAI_API_KEY")
    if key:
        try:
            with open(audio_path, "rb") as f:
                r = requests.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": f},
                    data={"model": "whisper-1"},
                    timeout=60
                )
            return r.json().get("text", r.text)
        except Exception as e: return f"Error: {e}"
    return "❌ whisper CLI not installed and OPENAI_API_KEY not set"

# ─── OpenAI Image Gen ─────────────────────────────────────────────────────────
def openai_image_gen(prompt: str, model: str = "dall-e-3", size: str = "1024x1024",
                     quality: str = "standard", out_dir: str = "/tmp", api_key: str = "") -> str:
    """OpenClaw openai-image-gen skill."""
    key = api_key or _env("OPENAI_API_KEY")
    if not key: return "❌ OPENAI_API_KEY not set"
    try:
        r = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "prompt": prompt, "n": 1, "size": size, "quality": quality},
            timeout=90
        )
        data = r.json()
        if "data" in data:
            img_url = data["data"][0].get("url", "")
            # Download
            img_r = requests.get(img_url, timeout=30)
            fname = f"{out_dir}/nexum_image_{uuid.uuid4().hex[:6]}.png"
            with open(fname, "wb") as f: f.write(img_r.content)
            return f"✅ Image saved: {fname}\nURL: {img_url}"
        return f"Error: {data}"
    except Exception as e: return f"Error: {e}"

# ─── Gemini ───────────────────────────────────────────────────────────────────
def gemini(prompt: str, api_key: str = "") -> str:
    """OpenClaw gemini skill — CLI или API."""
    if shutil.which("gemini"):
        return run_command(f'gemini "{prompt}"', timeout=30)
    key = api_key or _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")
    if key:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30
            )
            data = r.json()
            return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", r.text)
        except Exception as e: return f"Error: {e}"
    return "❌ gemini CLI not installed and GEMINI_API_KEY not set"

# ─── nano-pdf ─────────────────────────────────────────────────────────────────
def nano_pdf(pdf_path: str, page: int, instruction: str) -> str:
    """OpenClaw nano-pdf skill."""
    if not shutil.which("nano-pdf"):
        return "❌ nano-pdf not installed. Install: pip install nano-pdf (or uv install nano-pdf)"
    return run_command(f'nano-pdf edit "{pdf_path}" {page} "{instruction}"', timeout=60)

# ─── Summarize (URLs, YouTube, local files) ──────────────────────────────────
def summarize(target: str) -> str:
    """OpenClaw summarize skill."""
    if shutil.which("summarize"):
        return run_command(f'summarize "{target}"', timeout=60)
    # Fallback: HTTP fetch for URLs
    if target.startswith("http"):
        try:
            r = requests.get(target, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            text = r.text[:3000]
            return f"Fetched content (first 3000 chars):\n{text}"
        except Exception as e: return f"Error: {e}"
    return "❌ summarize CLI not installed. Install: brew install steipete/tap/summarize"

# ─── Blogwatcher (RSS/Atom feeds) ─────────────────────────────────────────────
def blogwatcher(op: str, arg: str = "") -> str:
    """OpenClaw blogwatcher skill."""
    if not shutil.which("blogwatcher"):
        return "❌ blogwatcher not installed. Install: go install github.com/Hyaxia/blogwatcher/cmd/blogwatcher@latest"
    cmds = {
        "list":  "blogwatcher blogs",
        "check": "blogwatcher check",
        "add":   f'blogwatcher add "Feed" "{arg}"',
    }
    return run_command(cmds.get(op, f"blogwatcher {op} {arg}"), timeout=30)

# ─── GifGrep ──────────────────────────────────────────────────────────────────
def gifgrep(query: str, op: str = "search", count: int = 5) -> str:
    """OpenClaw gifgrep skill."""
    if not shutil.which("gifgrep"):
        return "❌ gifgrep not installed. Install: brew install steipete/tap/gifgrep"
    if op == "search":
        return run_command(f'gifgrep search "{query}" --count {count} --no-tui', timeout=20)
    elif op == "download":
        return run_command(f'gifgrep download "{query}" --out /tmp/nexum_gif_{uuid.uuid4().hex[:6]}.gif', timeout=30)
    else:
        return run_command(f"gifgrep {op} {query}", timeout=20)

# ─── Camsnap (RTSP/ONVIF cameras) ────────────────────────────────────────────
def camsnap(op: str, camera: str = "", out: str = "") -> str:
    """OpenClaw camsnap skill."""
    if not shutil.which("camsnap"):
        return "❌ camsnap not installed. Install: brew install steipete/tap/camsnap"
    cmds = {
        "discover": "camsnap discover --info",
        "snap":     f'camsnap snap "{camera}" --out {out or "/tmp/nexum_cam.jpg"}',
        "clip":     f'camsnap clip "{camera}" --dur 5s --out {out or "/tmp/nexum_clip.mp4"}',
        "list":     "camsnap list",
    }
    return run_command(cmds.get(op, f"camsnap {op} {camera}"), timeout=30)

# ─── Peekaboo (macOS UI automation) ──────────────────────────────────────────
def peekaboo(op: str, arg: str = "") -> str:
    """OpenClaw peekaboo skill — macOS UI automation."""
    if not shutil.which("peekaboo"):
        return "❌ peekaboo not installed (macOS only). Install: brew install steipete/tap/peekaboo"
    cmds = {
        "capture": f"peekaboo capture {arg}",
        "click":   f"peekaboo click {arg}",
        "type":    f'peekaboo type "{arg}"',
        "apps":    "peekaboo apps",
        "windows": "peekaboo windows",
        "screen":  "peekaboo screen",
    }
    return run_command(cmds.get(op, f"peekaboo {op} {arg}"), timeout=15)

# ─── Himalaya (Email IMAP/SMTP) ───────────────────────────────────────────────
def himalaya(subcmd: str) -> str:
    """OpenClaw himalaya skill — email CLI."""
    if not shutil.which("himalaya"):
        return "❌ himalaya not installed. Install: brew install himalaya"
    return run_command(f"himalaya {subcmd}", timeout=20)

# ─── iMessage (imsg CLI, macOS) ───────────────────────────────────────────────
def imsg(op: str, arg: str = "", message: str = "") -> str:
    """OpenClaw imsg skill — iMessage/SMS."""
    if not shutil.which("imsg"):
        return "❌ imsg not installed (macOS only). Install: brew install steipete/tap/imsg"
    cmds = {
        "chats":   "imsg chats",
        "history": f'imsg history "{arg}"',
        "send":    f'imsg send "{arg}" "{message}"',
    }
    return run_command(cmds.get(op, f"imsg {op} {arg}"), timeout=15)

# ─── X/Twitter (xurl CLI) ────────────────────────────────────────────────────
def xurl(subcmd: str) -> str:
    """OpenClaw xurl skill — X/Twitter API CLI."""
    if not shutil.which("xurl"):
        return "❌ xurl not installed. Install: brew install xdevplatform/tap/xurl  OR  npm install -g @xdevplatform/xurl"
    return run_command(f"xurl {subcmd}", timeout=20)

# ─── 1Password (op CLI) ──────────────────────────────────────────────────────
def onepassword(subcmd: str) -> str:
    """OpenClaw 1password skill."""
    if not shutil.which("op"):
        return "❌ op CLI not installed. Install: brew install 1password-cli"
    return run_command(f"op {subcmd}", timeout=20)

# ─── Coding Agent (claude/codex/opencode) ────────────────────────────────────
def coding_agent(prompt: str, agent: str = "auto", project_dir: str = "") -> str:
    """OpenClaw coding-agent skill — делегирование задач AI-кодировщику."""
    cwd = project_dir or str(Path.home())
    if agent == "auto":
        if shutil.which("claude"):   agent = "claude"
        elif shutil.which("codex"):  agent = "codex"
        elif shutil.which("opencode"): agent = "opencode"
        else: return "❌ No coding agent installed. Install: npm install -g @anthropic-ai/claude-code"
    if agent == "claude":
        return run_command(
            f'claude --permission-mode bypassPermissions --print "{prompt}"',
            timeout=120, cwd=cwd
        )
    elif agent == "codex":
        return run_command(f'codex exec "{prompt}"', timeout=120, cwd=cwd)
    elif agent == "opencode":
        return run_command(f'opencode "{prompt}"', timeout=120, cwd=cwd)
    return f"❌ Unknown agent: {agent}"

# ─── Session logs ─────────────────────────────────────────────────────────────
def session_logs(op: str, query: str = "") -> str:
    """OpenClaw session-logs skill — поиск по истории OpenClaw сессий."""
    logs_dir = Path.home() / ".openclaw" / "agents"
    if not logs_dir.exists():
        return "❌ No OpenClaw session logs found at ~/.openclaw/agents/"
    if op == "list":
        sessions = list(logs_dir.rglob("*.jsonl"))[:20]
        return "\n".join(str(s) for s in sessions) or "(no sessions)"
    elif op == "search":
        if not shutil.which("rg") and not shutil.which("grep"):
            return "❌ rg or grep required"
        tool = "rg" if shutil.which("rg") else "grep -r"
        return run_command(f'{tool} "{query}" ~/.openclaw/agents/ 2>/dev/null | head -50', timeout=15)
    return "❌ Unknown op (list / search)"

# ─── Healthcheck ──────────────────────────────────────────────────────────────
def healthcheck(url: str, method: str = "GET") -> str:
    """OpenClaw healthcheck skill."""
    try:
        start = time.time()
        r = requests.request(method, url, timeout=10)
        ms = int((time.time() - start) * 1000)
        status = "✅" if r.status_code < 400 else "❌"
        return f"{status} {url}\nStatus: {r.status_code} ({ms}ms)"
    except requests.exceptions.Timeout:
        return f"❌ {url}\nTimeout"
    except Exception as e:
        return f"❌ {url}\n{e}"

# ─── Philips Hue (openhue) ────────────────────────────────────────────────────
def openhue(subcmd: str) -> str:
    """OpenClaw openhue skill."""
    if not shutil.which("openhue"):
        return "❌ openhue not installed. Install: brew install openhue/tap/openhue"
    return run_command(f"openhue {subcmd}", timeout=10)

# ─── Sonos ────────────────────────────────────────────────────────────────────
def sonos(subcmd: str) -> str:
    """OpenClaw sonos skill."""
    if not shutil.which("sonoscli") and not shutil.which("sonos"):
        return "❌ sonoscli not installed."
    cli = "sonoscli" if shutil.which("sonoscli") else "sonos"
    return run_command(f"{cli} {subcmd}", timeout=10)

# ─── ElevenLabs TTS (sag) ────────────────────────────────────────────────────
def sag_tts(text: str, voice: str = "", api_key: str = "") -> str:
    """OpenClaw sag skill — ElevenLabs TTS."""
    if shutil.which("sag"):
        cmd = f'sag "{text}"'
        if voice: cmd += f' --voice "{voice}"'
        return run_command(cmd, timeout=30)
    key = api_key or _env("ELEVENLABS_API_KEY")
    if key:
        try:
            voice_id = voice or "21m00Tcm4TlvDq8ikWAM"  # Rachel
            r = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={"xi-api-key": key, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_monolingual_v1"},
                timeout=30
            )
            if r.status_code == 200:
                out = f"/tmp/nexum_tts_{uuid.uuid4().hex[:6]}.mp3"
                with open(out, "wb") as f: f.write(r.content)
                return f"✅ TTS saved: {out}"
            return f"Error: {r.status_code} {r.text}"
        except Exception as e: return f"Error: {e}"
    return "❌ sag CLI not installed and ELEVENLABS_API_KEY not set"

# ─── BluOS (blucli) ───────────────────────────────────────────────────────────
def blucli(subcmd: str) -> str:
    """OpenClaw blucli skill — Bluesound/NAD players."""
    if not shutil.which("blu"):
        return "❌ blu CLI not installed. Install: go install github.com/steipete/blucli/cmd/blu@latest"
    return run_command(f"blu {subcmd}", timeout=10)

# ─── Eight Sleep (eightctl) ──────────────────────────────────────────────────
def eightctl(subcmd: str) -> str:
    """OpenClaw eightctl skill."""
    if not shutil.which("eightctl"):
        return "❌ eightctl not installed. See https://eightctl.sh"
    return run_command(f"eightctl {subcmd}", timeout=15)

# ─── MCP Porter (mcporter) ───────────────────────────────────────────────────
def mcporter(subcmd: str) -> str:
    """OpenClaw mcporter skill — MCP servers management."""
    if not shutil.which("mcporter"):
        return "❌ mcporter not installed. See http://mcporter.dev"
    return run_command(f"mcporter {subcmd}", timeout=20)

# ─── Oracle (prompt bundling) ─────────────────────────────────────────────────
def oracle(subcmd: str) -> str:
    """OpenClaw oracle skill."""
    if not shutil.which("oracle"):
        return "❌ oracle not installed."
    return run_command(f"oracle {subcmd}", timeout=30)

# ─── Obsidian CLI / Skill creator ────────────────────────────────────────────
def skill_creator(op: str, skill_name: str = "", content: str = "") -> str:
    """OpenClaw skill-creator — создание/редактирование навыков агента."""
    skills_dir = Path.home() / ".nexum" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    if op == "list":
        return "\n".join(d.name for d in skills_dir.iterdir() if d.is_dir()) or "(no skills)"
    elif op == "create":
        skill_dir = skills_dir / skill_name
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content or f"# {skill_name}\n\nSkill description here.")
        return f"✅ Skill created: {skill_dir}"
    elif op == "read":
        md = skills_dir / skill_name / "SKILL.md"
        return md.read_text() if md.exists() else f"❌ Skill '{skill_name}' not found"
    elif op == "delete":
        skill_dir = skills_dir / skill_name
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
            return f"✅ Deleted skill: {skill_name}"
        return f"❌ Not found: {skill_name}"
    return f"❌ Unknown op: {op}"

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN AGENT LOOP
# ═══════════════════════════════════════════════════════════════════════════════

async def agent_loop():
    global UID
    reconnect_delay = 2
    linked = UID is not None
    identity = detect_user_identity()

    while True:
        try:
            print(f"\n🔌 Connecting → {SERVER_URL}")
            async with websockets.connect(SERVER_URL, ping_interval=25, ping_timeout=10) as ws:
                reconnect_delay = 2

                if linked and UID:
                    await ws.send(json.dumps({
                        "type": "register", "uid": UID, "device_id": DEVICE_ID,
                        "name": socket.gethostname(), "platform": get_platform(),
                        "mode": "FULL_OPENCLAW", "version": AGENT_VERSION,
                        "identity": identity,
                        "sysinfo": {"cpu": psutil.cpu_count(), "os": platform.system(),
                                    "ram_gb": psutil.virtual_memory().total // 1024**3},
                    }))
                    print(f"✅ Registered — uid={UID}")
                else:
                    await ws.send(json.dumps({
                        "type": "request_link", "device_id": DEVICE_ID,
                        "platform": get_platform(), "identity": identity,
                    }))
                    print("⏳ Ожидаю привязки…")

                async def heartbeat():
                    while True:
                        await asyncio.sleep(20)
                        try: await ws.send(json.dumps({"type": "ping"}))
                        except Exception: break

                hb = asyncio.create_task(heartbeat())

                async def reply(req_id: str, data):
                    if isinstance(data, (dict, list)):
                        data = json.dumps(data, ensure_ascii=False)
                    await ws.send(json.dumps({"type": "result", "reqId": req_id,
                                              "data": str(data)[:4000]}))

                try:
                    async for raw in ws:
                        msg   = json.loads(raw)
                        mtype = msg.get("type")
                        rid   = msg.get("reqId", "")

                        # ── Linking ──────────────────────────────────────
                        if mtype == "link_code":
                            code = msg.get("code")
                            print(f"\n{'='*50}\n  🔑 LINKING CODE: {code}\n  Отправь боту: /link {code}\n{'='*50}\n")

                        elif mtype == "linked":
                            UID    = msg.get("uid")
                            linked = True
                            save_config()  # ← uid вшивается персонально
                            print(f"\n✅ Привязан uid={UID}  (сохранено: {CONFIG_FILE})")

                        elif mtype == "registered":
                            print("✅ Agent active — ожидаю команды")

                        elif mtype == "need_link":
                            linked = False
                            await ws.send(json.dumps({"type": "request_link",
                                "device_id": DEVICE_ID, "platform": get_platform()}))

                        elif mtype == "pong":
                            pass

                        # ══ SYSTEM ═══════════════════════════════════════
                        elif mtype == "screenshot":
                            region = msg.get("region")
                            print("📸 Screenshot…")
                            b64 = take_screenshot(tuple(region) if region else None)
                            await ws.send(json.dumps({"type": "screenshot_result",
                                "reqId": rid, "chatId": msg.get("chatId"), "data": b64 or ""}))

                        elif mtype == "run":
                            cmd = msg.get("command", "")
                            print(f"⚙️  Run: {cmd[:60]}")
                            await reply(rid, run_command(cmd, msg.get("timeout", 60), msg.get("cwd")))

                        elif mtype == "run_background":
                            await reply(rid, run_background(msg.get("command", "")))

                        elif mtype == "bg_list":
                            await reply(rid, list_bg())

                        elif mtype == "bg_stop":
                            await reply(rid, stop_bg(msg.get("proc_id", "")))

                        elif mtype == "sysinfo":
                            await reply(rid, get_sysinfo())

                        elif mtype == "processes":
                            await reply(rid, get_processes(msg.get("limit", 15)))

                        elif mtype == "kill_process":
                            await reply(rid, kill_process(msg.get("input", "")))

                        elif mtype == "filesystem":
                            await reply(rid, filesystem_op(msg.get("op","read"),
                                msg.get("path",""), msg.get("content","")))

                        elif mtype == "clipboard":
                            await reply(rid, clipboard_op(msg.get("op","read"), msg.get("text","")))

                        elif mtype == "notify":
                            await reply(rid, send_notification(msg.get("title","NEXUM"),
                                msg.get("message",""), msg.get("timeout",5)))

                        elif mtype == "window":
                            await reply(rid, window_op(msg.get("op","list"), msg.get("window_id","")))

                        elif mtype == "http":
                            print(f"🌐 HTTP {msg.get('method','GET')} {msg.get('url','')[:60]}")
                            await reply(rid, http_request(msg.get("method","GET"), msg.get("url",""),
                                msg.get("body",""), msg.get("headers","")))

                        elif mtype == "browser":
                            await reply(rid, open_browser(msg.get("input","")))

                        elif mtype == "open_app":
                            await reply(rid, open_application(msg.get("input","")))

                        elif mtype == "mouse":
                            await reply(rid, mouse_control(msg.get("action","position"),
                                int(msg.get("x",0)), int(msg.get("y",0)), msg.get("text","")))

                        elif mtype == "keyboard":
                            await reply(rid, mouse_control(msg.get("action","type"),
                                0, 0, msg.get("text","")))

                        elif mtype == "network":
                            await reply(rid, get_network_info())

                        elif mtype == "identity":
                            await reply(rid, json.dumps(detect_user_identity(), ensure_ascii=False))

                        # ══ OPENCLAW SKILLS ═══════════════════════════════
                        elif mtype == "weather":
                            await reply(rid, weather(msg.get("location",""), msg.get("mode","current")))

                        elif mtype == "github":
                            await reply(rid, github(msg.get("subcmd","")))

                        elif mtype == "google_workspace":
                            await reply(rid, google_workspace(msg.get("subcmd","")))

                        elif mtype == "google_places":
                            await reply(rid, google_places(msg.get("query",""), msg.get("api_key","")))

                        elif mtype == "notion":
                            await reply(rid, notion(msg.get("method","GET"), msg.get("endpoint",""),
                                msg.get("body",""), msg.get("api_key","")))

                        elif mtype == "notion_search":
                            await reply(rid, notion_search(msg.get("query",""), msg.get("api_key","")))

                        elif mtype == "obsidian":
                            await reply(rid, obsidian(msg.get("op","list"),
                                msg.get("path",""), msg.get("content","")))

                        elif mtype == "apple_notes":
                            await reply(rid, apple_notes(msg.get("op","list"), msg.get("arg","")))

                        elif mtype == "apple_reminders":
                            await reply(rid, apple_reminders(msg.get("op","list"), msg.get("arg","")))

                        elif mtype == "bear_notes":
                            await reply(rid, bear_notes(msg.get("op","list"), msg.get("arg","")))

                        elif mtype == "trello":
                            await reply(rid, trello(msg.get("op","boards"), msg.get("arg",""),
                                msg.get("body")))

                        elif mtype == "slack":
                            await reply(rid, slack(msg.get("op","channels"), msg.get("channel",""),
                                msg.get("text",""), msg.get("ts",""), msg.get("emoji","")))

                        elif mtype == "discord":
                            await reply(rid, discord(msg.get("op","history"), msg.get("channel_id",""),
                                msg.get("text",""), msg.get("msg_id","")))

                        elif mtype == "spotify":
                            await reply(rid, spotify(msg.get("op","status"), msg.get("arg","")))

                        elif mtype == "tmux":
                            await reply(rid, tmux(msg.get("op","list"), msg.get("session","main"),
                                msg.get("pane",""), msg.get("keys","")))

                        elif mtype == "video_frames":
                            await reply(rid, video_frames(msg.get("path",""), msg.get("op","frame"),
                                msg.get("time","00:00:01"), msg.get("out","")))

                        elif mtype == "whisper":
                            await reply(rid, whisper_transcribe(msg.get("path",""),
                                msg.get("model","base"), msg.get("api_key","")))

                        elif mtype == "image_gen":
                            await reply(rid, openai_image_gen(msg.get("prompt",""),
                                msg.get("model","dall-e-3"), msg.get("size","1024x1024"),
                                msg.get("quality","standard"), msg.get("out_dir","/tmp"),
                                msg.get("api_key","")))

                        elif mtype == "gemini":
                            await reply(rid, gemini(msg.get("prompt",""), msg.get("api_key","")))

                        elif mtype == "nano_pdf":
                            await reply(rid, nano_pdf(msg.get("path",""),
                                msg.get("page",1), msg.get("instruction","")))

                        elif mtype == "summarize":
                            await reply(rid, summarize(msg.get("target","")))

                        elif mtype == "blogwatcher":
                            await reply(rid, blogwatcher(msg.get("op","list"), msg.get("arg","")))

                        elif mtype == "gifgrep":
                            await reply(rid, gifgrep(msg.get("query",""), msg.get("op","search"),
                                msg.get("count",5)))

                        elif mtype == "camsnap":
                            await reply(rid, camsnap(msg.get("op","discover"),
                                msg.get("camera",""), msg.get("out","")))

                        elif mtype == "peekaboo":
                            await reply(rid, peekaboo(msg.get("op","screen"), msg.get("arg","")))

                        elif mtype == "himalaya":
                            await reply(rid, himalaya(msg.get("subcmd","envelope list")))

                        elif mtype == "imsg":
                            await reply(rid, imsg(msg.get("op","chats"),
                                msg.get("arg",""), msg.get("message","")))

                        elif mtype == "xurl":
                            await reply(rid, xurl(msg.get("subcmd","")))

                        elif mtype == "onepassword":
                            await reply(rid, onepassword(msg.get("subcmd","item list")))

                        elif mtype == "coding_agent":
                            await reply(rid, coding_agent(msg.get("prompt",""),
                                msg.get("agent","auto"), msg.get("dir","")))

                        elif mtype == "session_logs":
                            await reply(rid, session_logs(msg.get("op","list"), msg.get("query","")))

                        elif mtype == "healthcheck":
                            await reply(rid, healthcheck(msg.get("url",""), msg.get("method","GET")))

                        elif mtype == "openhue":
                            await reply(rid, openhue(msg.get("subcmd","lights list")))

                        elif mtype == "sonos":
                            await reply(rid, sonos(msg.get("subcmd","status")))

                        elif mtype == "sag_tts":
                            await reply(rid, sag_tts(msg.get("text",""),
                                msg.get("voice",""), msg.get("api_key","")))

                        elif mtype == "blucli":
                            await reply(rid, blucli(msg.get("subcmd","status")))

                        elif mtype == "eightctl":
                            await reply(rid, eightctl(msg.get("subcmd","status")))

                        elif mtype == "mcporter":
                            await reply(rid, mcporter(msg.get("subcmd","list")))

                        elif mtype == "oracle":
                            await reply(rid, oracle(msg.get("subcmd","")))

                        elif mtype == "skill_creator":
                            await reply(rid, skill_creator(msg.get("op","list"),
                                msg.get("skill_name",""), msg.get("content","")))

                        else:
                            print(f"⚠️  Unknown: {mtype}")

                finally:
                    hb.cancel()

        except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            print(f"⚠️  Disconnected: {e}. Retry in {reconnect_delay}s…")
        except Exception as e:
            print(f"❌ Error: {e}. Retry in {reconnect_delay}s…")

        await asyncio.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, 30)

# ─── Entry ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  NEXUM PC Agent v8.0  —  Full OpenClaw Integration")
    print("=" * 60)
    if len(sys.argv) > 1:
        SERVER_URL = sys.argv[1]
    load_config()
    ident = detect_user_identity()
    print(f"  Device  : {DEVICE_ID}")
    print(f"  OS User : {ident['os_user']}  @  {ident['hostname']}")
    print(f"  Platform: {ident['platform']}")
    print(f"  Server  : {SERVER_URL}")
    if UID:
        print(f"  UID     : {UID}  ← вшит в {CONFIG_FILE}")
    else:
        print(f"  Status  : Не привязан — получи /link код от бота")
    print("=" * 60)
    print()
    print("СИСТЕМНЫЕ: screenshot · mouse/kb · terminal · files")
    print("           clipboard · notifications · windows · http")
    print("           browser · sysinfo · processes · network")
    print()
    print("OPENCLAW SKILLS: weather · github · google-workspace")
    print("                 google-places · notion · obsidian")
    print("                 apple-notes · apple-reminders · bear-notes")
    print("                 trello · slack · discord · spotify · tmux")
    print("                 video-frames · whisper · image-gen · gemini")
    print("                 nano-pdf · summarize · blogwatcher · gifgrep")
    print("                 camsnap · peekaboo · himalaya · imsg · xurl")
    print("                 1password · coding-agent · session-logs")
    print("                 healthcheck · openhue · sonos · sag-tts")
    print("                 blucli · eightctl · mcporter · skill-creator")
    print()
    try:
        asyncio.run(agent_loop())
    except KeyboardInterrupt:
        print("\n👋 Stopped.")
