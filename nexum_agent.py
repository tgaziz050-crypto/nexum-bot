#!/usr/bin/env python3
"""
NEXUM PC Agent — connects your computer to NEXUM bot via WebSocket.
Capabilities: screenshots, mouse/keyboard control, terminal, files, browser, notifications, HTTP.
"""
import sys, os, subprocess, platform, json, time, threading, base64, tempfile, pathlib

_PLATFORM = platform.system()  # Windows / Darwin / Linux

# ── Auto-install deps ─────────────────────────────────────────────────────────
_REQUIRED = {
    'websockets': 'websockets',
    'psutil':     'psutil',
    'requests':   'requests',
    'PIL':        'pillow',
    'pyautogui':  'pyautogui',
    'pyperclip':  'pyperclip',
}

def _ensure_deps():
    for imp, pkg in _REQUIRED.items():
        try:
            __import__(imp)
        except ImportError:
            print(f"📦 Installing {pkg}...")
            subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=True, capture_output=True)

_ensure_deps()

import asyncio, websockets, psutil, requests
from PIL import ImageGrab, Image
import pyautogui
import pyperclip

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_FILE   = pathlib.Path.home() / ".nexum_agent.json"
PLATFORM_NAME = f"{_PLATFORM} {platform.machine()}"
DEVICE_ID     = platform.node()

def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except:
            pass
    return {}

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

cfg = load_config()

# ── Get server URL ────────────────────────────────────────────────────────────
def get_server_url():
    url = cfg.get("server_url", "").strip()
    if not url:
        url = os.environ.get("NEXUM_SERVER", "").strip()
    if not url:
        print("\n🔗 Enter your NEXUM server URL")
        print("   Example: wss://nexum-bot-production-ae70.up.railway.app/ws")
        url = input("   URL: ").strip()
        if url:
            cfg["server_url"] = url
            save_config(cfg)
    return url

SERVER_URL = get_server_url()
if not SERVER_URL:
    print("❌ No server URL provided. Exiting.")
    sys.exit(1)

# ── Screenshot ────────────────────────────────────────────────────────────────
def take_screenshot(region=None) -> str:
    """Returns base64-encoded PNG screenshot."""
    try:
        if region and len(region) == 4:
            img = ImageGrab.grab(bbox=region)
        else:
            img = ImageGrab.grab()
        # Resize if too large
        w, h = img.size
        if w > 1920:
            ratio = 1920 / w
            img = img.resize((int(w*ratio), int(h*ratio)), Image.LANCZOS)
        buf = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        img.save(buf.name, 'PNG', optimize=True)
        with open(buf.name, 'rb') as f:
            data = base64.b64encode(f.read()).decode()
        os.unlink(buf.name)
        return data
    except Exception as e:
        raise RuntimeError(f"Screenshot failed: {e}")

# ── Run command ───────────────────────────────────────────────────────────────
def run_command(cmd: str, timeout=30) -> str:
    """Execute shell command and return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout,
            encoding='utf-8', errors='replace'
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if out and err:
            return f"{out}\n\nSTDERR:\n{err}"
        return out or err or "(no output)"
    except subprocess.TimeoutExpired:
        return f"⏱ Command timed out after {timeout}s"
    except Exception as e:
        return f"❌ Error: {e}"

# Background processes
_bg_procs: dict = {}
_bg_id = 0

def run_background(cmd: str) -> str:
    global _bg_id
    _bg_id += 1
    proc_id = f"bg_{_bg_id}"
    proc = subprocess.Popen(cmd, shell=True)
    _bg_procs[proc_id] = {'proc': proc, 'cmd': cmd, 'started': time.time()}
    return f"🔄 Started background process `{proc_id}`\nPID: {proc.pid}\nCommand: {cmd}"

def list_bg() -> str:
    if not _bg_procs:
        return "No background processes"
    lines = []
    for pid, info in _bg_procs.items():
        status = "running" if info['proc'].poll() is None else f"exited({info['proc'].returncode})"
        lines.append(f"• `{pid}` [{status}] {info['cmd'][:60]}")
    return "\n".join(lines)

def stop_bg(proc_id: str) -> str:
    if proc_id not in _bg_procs:
        return f"❌ Process `{proc_id}` not found"
    _bg_procs[proc_id]['proc'].terminate()
    del _bg_procs[proc_id]
    return f"✅ Stopped `{proc_id}`"

# ── System info ───────────────────────────────────────────────────────────────
def get_sysinfo() -> str:
    cpu    = psutil.cpu_percent(interval=1)
    mem    = psutil.virtual_memory()
    disk   = psutil.disk_usage('/')
    net    = psutil.net_io_counters()
    boot   = time.time() - psutil.boot_time()
    uptime = f"{int(boot//3600)}h {int((boot%3600)//60)}m"

    gb = 1024**3
    return (
        f"💻 **System Info**\n\n"
        f"🖥 OS: {_PLATFORM} {platform.version()[:40]}\n"
        f"📱 Device: {DEVICE_ID}\n"
        f"⚙️ CPU: {cpu}% ({psutil.cpu_count()} cores)\n"
        f"🧠 RAM: {mem.used/gb:.1f}/{mem.total/gb:.1f} GB ({mem.percent}%)\n"
        f"💾 Disk: {disk.used/gb:.1f}/{disk.total/gb:.1f} GB ({disk.percent}%)\n"
        f"🌐 Net: ↑{net.bytes_sent/1024/1024:.1f}MB ↓{net.bytes_recv/1024/1024:.1f}MB\n"
        f"⏱ Uptime: {uptime}"
    )

def get_processes(limit=15) -> str:
    procs = sorted(psutil.process_iter(['pid','name','cpu_percent','memory_percent','status']),
                   key=lambda p: p.info.get('cpu_percent',0) or 0, reverse=True)[:limit]
    lines = [f"{'PID':<8} {'CPU%':<7} {'MEM%':<7} {'NAME'}"]
    lines.append("─" * 40)
    for p in procs:
        i = p.info
        lines.append(f"{i['pid']:<8} {(i['cpu_percent'] or 0):<7.1f} {(i['memory_percent'] or 0):<7.1f} {(i['name'] or '?')[:30]}")
    return "```\n" + "\n".join(lines) + "\n```"

def kill_process(target: str) -> str:
    killed = []
    for p in psutil.process_iter(['pid', 'name']):
        try:
            if str(p.pid) == target or target.lower() in (p.info['name'] or '').lower():
                p.terminate()
                killed.append(f"{p.info['name']} (PID {p.pid})")
        except:
            pass
    return f"✅ Killed: {', '.join(killed)}" if killed else f"❌ Process not found: {target}"

# ── Filesystem ────────────────────────────────────────────────────────────────
def filesystem_op(op: str, path: str = "~", content: str = "") -> str:
    path = os.path.expanduser(path)
    try:
        if op == "list":
            entries = sorted(os.listdir(path))
            dirs  = [f"📁 {e}" for e in entries if os.path.isdir(os.path.join(path, e))]
            files = [f"📄 {e}" for e in entries if os.path.isfile(os.path.join(path, e))]
            return f"📂 {path}\n\n" + "\n".join(dirs + files) or "(empty)"
        elif op == "read":
            with open(path, encoding='utf-8', errors='replace') as f:
                data = f.read(8000)
            return f"📄 `{path}`:\n```\n{data}\n```"
        elif op == "write":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"✅ Written to {path}"
        elif op == "delete":
            if os.path.isfile(path):
                os.remove(path)
            else:
                import shutil
                shutil.rmtree(path)
            return f"🗑 Deleted: {path}"
        elif op == "exists":
            return f"{'✅ Exists' if os.path.exists(path) else '❌ Not found'}: {path}"
        elif op == "mkdir":
            os.makedirs(path, exist_ok=True)
            return f"✅ Created directory: {path}"
        else:
            return f"❌ Unknown op: {op}"
    except Exception as e:
        return f"❌ Error: {e}"

# ── Mouse & Keyboard ──────────────────────────────────────────────────────────
def mouse_action(action: str, x=0, y=0, text="") -> str:
    try:
        pyautogui.FAILSAFE = False
        if action == "move":
            pyautogui.moveTo(x, y, duration=0.3)
            return f"✅ Mouse moved to ({x}, {y})"
        elif action == "click":
            pyautogui.click(x, y)
            return f"✅ Clicked at ({x}, {y})"
        elif action == "double":
            pyautogui.doubleClick(x, y)
            return f"✅ Double-clicked at ({x}, {y})"
        elif action == "right":
            pyautogui.rightClick(x, y)
            return f"✅ Right-clicked at ({x}, {y})"
        elif action == "scroll":
            pyautogui.scroll(int(text) if text else 3, x=x, y=y)
            return f"✅ Scrolled"
        elif action == "drag":
            parts = text.split(',') if text else []
            if len(parts) >= 2:
                pyautogui.dragTo(int(parts[0]), int(parts[1]), duration=0.5)
                return f"✅ Dragged to ({parts[0]}, {parts[1]})"
        elif action == "position":
            pos = pyautogui.position()
            return f"🖱 Mouse position: ({pos.x}, {pos.y})"
        return f"❌ Unknown action: {action}"
    except Exception as e:
        return f"❌ Mouse error: {e}"

def keyboard_action(action: str, text="") -> str:
    try:
        if action == "type":
            pyautogui.write(text, interval=0.02)
            return f"✅ Typed: {text[:50]}"
        elif action == "hotkey":
            keys = [k.strip() for k in text.split('+')]
            pyautogui.hotkey(*keys)
            return f"✅ Pressed: {text}"
        elif action == "press":
            pyautogui.press(text)
            return f"✅ Pressed key: {text}"
        elif action == "typewrite":
            pyautogui.typewrite(text)
            return f"✅ Typewritten: {text[:50]}"
        return f"❌ Unknown action: {action}"
    except Exception as e:
        return f"❌ Keyboard error: {e}"

# ── Clipboard ─────────────────────────────────────────────────────────────────
def clipboard_op(op: str, text="") -> str:
    try:
        if op == "read":
            content = pyperclip.paste()
            return f"📋 Clipboard:\n```\n{content[:2000]}\n```" if content else "📋 Clipboard is empty"
        elif op == "write":
            pyperclip.copy(text)
            return f"✅ Copied to clipboard: {text[:100]}"
        return f"❌ Unknown op: {op}"
    except Exception as e:
        return f"❌ Clipboard error: {e}"

# ── Notifications ─────────────────────────────────────────────────────────────
def send_notification(title: str, message: str) -> str:
    try:
        if _PLATFORM == "Windows":
            subprocess.Popen(['powershell', '-Command',
                f'Add-Type -AssemblyName System.Windows.Forms; '
                f'$n = New-Object System.Windows.Forms.NotifyIcon; '
                f'$n.Icon = [System.Drawing.SystemIcons]::Information; '
                f'$n.Visible = $True; '
                f'$n.ShowBalloonTip(5000, "{title}", "{message}", [System.Windows.Forms.ToolTipIcon]::Info)'
            ])
        elif _PLATFORM == "Darwin":
            subprocess.run(['osascript', '-e', f'display notification "{message}" with title "{title}"'])
        else:
            subprocess.run(['notify-send', title, message])
        return f"✅ Notification sent: {title}"
    except Exception as e:
        return f"❌ Notification error: {e}"

# ── Network info ──────────────────────────────────────────────────────────────
def get_network() -> str:
    try:
        interfaces = psutil.net_if_addrs()
        lines = ["🌐 **Network**\n"]
        for iface, addrs in list(interfaces.items())[:6]:
            for addr in addrs:
                if addr.family.name in ('AF_INET', '2'):
                    lines.append(f"• {iface}: {addr.address}")
        # External IP
        try:
            ext = requests.get("https://api.ipify.org", timeout=3).text
            lines.append(f"\n🌍 External IP: {ext}")
        except:
            pass
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Network error: {e}"

# ── Window management ─────────────────────────────────────────────────────────
def window_op(op: str, window_id="") -> str:
    try:
        if _PLATFORM == "Windows":
            if op == "list":
                result = subprocess.run(['powershell', '-Command',
                    'Get-Process | Where-Object {$_.MainWindowTitle -ne ""} | Select-Object Id,ProcessName,MainWindowTitle | Format-Table -AutoSize'],
                    capture_output=True, text=True, timeout=10)
                return f"🪟 Windows:\n```\n{result.stdout[:2000]}\n```"
            elif op == "focus" and window_id:
                subprocess.run(['powershell', '-Command', f'(Get-Process | Where-Object {{$_.MainWindowTitle -like "*{window_id}*"}} | Select-Object -First 1).MainWindowHandle | ForEach-Object {{[Microsoft.VisualBasic.Interaction]::AppActivate($_)}}'])
                return f"✅ Focused window: {window_id}"
        elif _PLATFORM == "Darwin":
            if op == "list":
                result = subprocess.run(['osascript', '-e', 'tell app "System Events" to get name of every window of every process whose visible is true'], capture_output=True, text=True)
                return f"🪟 Windows:\n{result.stdout[:2000]}"
        return f"Window operation '{op}' completed"
    except Exception as e:
        return f"❌ Window error: {e}"

# ── Browser ───────────────────────────────────────────────────────────────────
def browser_open(url: str) -> str:
    try:
        import webbrowser
        webbrowser.open(url)
        return f"✅ Opened in browser: {url}"
    except Exception as e:
        return f"❌ Browser error: {e}"

# ── HTTP request ──────────────────────────────────────────────────────────────
def http_request(method: str, url: str, body="") -> str:
    try:
        method = method.upper()
        headers = {'Content-Type': 'application/json', 'User-Agent': 'NEXUM-Agent/12.0'}
        if method == 'GET':
            r = requests.get(url, headers=headers, timeout=15)
        elif method == 'POST':
            r = requests.post(url, data=body, headers=headers, timeout=15)
        elif method == 'PUT':
            r = requests.put(url, data=body, headers=headers, timeout=15)
        elif method == 'DELETE':
            r = requests.delete(url, headers=headers, timeout=15)
        else:
            return f"❌ Unsupported method: {method}"
        try:
            content = r.json()
            text = json.dumps(content, indent=2, ensure_ascii=False)[:3000]
        except:
            text = r.text[:3000]
        return f"**{method} {url}**\nStatus: {r.status_code}\n```\n{text}\n```"
    except Exception as e:
        return f"❌ HTTP error: {e}"

# ── Open app ──────────────────────────────────────────────────────────────────
def open_app(name: str) -> str:
    try:
        if _PLATFORM == "Windows":
            subprocess.Popen(['start', name], shell=True)
        elif _PLATFORM == "Darwin":
            subprocess.Popen(['open', '-a', name])
        else:
            subprocess.Popen([name])
        return f"✅ Launched: {name}"
    except Exception as e:
        return f"❌ Launch error: {e}"

# ── Message handler ───────────────────────────────────────────────────────────
async def handle_message(msg: dict) -> dict:
    t      = msg.get("type", "")
    req_id = msg.get("reqId", "")

    try:
        if t == "screenshot":
            data = take_screenshot(msg.get("region"))
            return {"type": "screenshot_result", "reqId": req_id, "data": data}

        elif t == "run":
            out = run_command(msg.get("command", "echo ok"))
            return {"type": "result", "reqId": req_id, "data": out}

        elif t == "run_background":
            out = run_background(msg.get("command", ""))
            return {"type": "result", "reqId": req_id, "data": out}

        elif t == "bg_list":
            return {"type": "result", "reqId": req_id, "data": list_bg()}

        elif t == "bg_stop":
            return {"type": "result", "reqId": req_id, "data": stop_bg(msg.get("proc_id", ""))}

        elif t == "sysinfo":
            return {"type": "result", "reqId": req_id, "data": get_sysinfo()}

        elif t == "processes":
            return {"type": "result", "reqId": req_id, "data": get_processes(msg.get("limit", 15))}

        elif t == "kill_process":
            return {"type": "result", "reqId": req_id, "data": kill_process(msg.get("input", ""))}

        elif t == "network":
            return {"type": "result", "reqId": req_id, "data": get_network()}

        elif t == "filesystem":
            return {"type": "result", "reqId": req_id, "data": filesystem_op(
                msg.get("op", "list"), msg.get("path", "~"), msg.get("content", "")
            )}

        elif t == "clipboard":
            return {"type": "result", "reqId": req_id, "data": clipboard_op(
                msg.get("op", "read"), msg.get("text", "")
            )}

        elif t == "notify":
            return {"type": "result", "reqId": req_id, "data": send_notification(
                msg.get("title", "NEXUM"), msg.get("message", "")
            )}

        elif t == "mouse":
            return {"type": "result", "reqId": req_id, "data": mouse_action(
                msg.get("action", "position"), msg.get("x", 0), msg.get("y", 0), msg.get("text", "")
            )}

        elif t == "keyboard":
            return {"type": "result", "reqId": req_id, "data": keyboard_action(
                msg.get("action", "type"), msg.get("text", "")
            )}

        elif t == "window":
            return {"type": "result", "reqId": req_id, "data": window_op(
                msg.get("op", "list"), msg.get("window_id", "")
            )}

        elif t == "browser":
            return {"type": "result", "reqId": req_id, "data": browser_open(msg.get("input", ""))}

        elif t == "open_app":
            return {"type": "result", "reqId": req_id, "data": open_app(msg.get("input", ""))}

        elif t == "http":
            return {"type": "result", "reqId": req_id, "data": http_request(
                msg.get("method", "GET"), msg.get("url", ""), msg.get("body", "")
            )}

        else:
            return {"type": "result", "reqId": req_id, "data": f"❓ Unknown command type: {t}"}

    except Exception as e:
        return {"type": "result", "reqId": req_id, "data": f"❌ Error handling {t}: {e}"}

# ── WebSocket client ──────────────────────────────────────────────────────────
async def run_agent():
    uid = cfg.get("uid")
    device_id = DEVICE_ID

    while True:
        try:
            print(f"\n🔌 Connecting to {SERVER_URL}...")
            async with websockets.connect(SERVER_URL, ping_interval=20, ping_timeout=30) as ws:
                print("✅ Connected!")

                if uid:
                    # Re-register with saved UID
                    await ws.send(json.dumps({"type": "register", "uid": uid, "device_id": device_id, "platform": PLATFORM_NAME}))
                    print(f"📱 Re-registered as UID {uid}")
                else:
                    # Request link code
                    await ws.send(json.dumps({"type": "request_link", "device_id": device_id, "platform": PLATFORM_NAME}))

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        mtype = msg.get("type")

                        if mtype == "link_code":
                            code = msg.get("code", "")
                            print(f"\n{'='*50}")
                            print(f"🔑 LINK CODE: {code}")
                            print(f"   Send to bot: /link {code}")
                            print(f"{'='*50}\n")

                        elif mtype == "linked":
                            uid = msg.get("uid")
                            cfg["uid"] = uid
                            save_config(cfg)
                            print(f"✅ Linked to Telegram UID: {uid}")
                            # Register now
                            await ws.send(json.dumps({"type": "register", "uid": uid, "device_id": device_id, "platform": PLATFORM_NAME}))

                        elif mtype == "registered":
                            print(f"✅ Agent registered and ready!")
                            print(f"   Commands available in Telegram: /screenshot /run /sysinfo etc.")

                        elif mtype == "pong":
                            pass  # keepalive

                        elif msg.get("reqId"):
                            # Handle command
                            response = await handle_message(msg)
                            await ws.send(json.dumps(response))

                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        print(f"❌ Message error: {e}")

        except websockets.exceptions.ConnectionClosed:
            print("⚠️ Connection closed, reconnecting in 5s...")
        except OSError as e:
            print(f"❌ Connection error: {e}")
            print("   Retrying in 10s...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"❌ Unexpected error: {e}")

        await asyncio.sleep(5)

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  NEXUM PC Agent")
    print(f"  Platform: {PLATFORM_NAME}")
    print(f"  Device:   {DEVICE_ID}")
    print("=" * 50)

    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        print("\n👋 Agent stopped.")
