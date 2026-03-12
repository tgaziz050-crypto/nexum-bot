#!/usr/bin/env python3
"""
NEXUM v5 PC Agent
Secure linking via code — bot token never exposed to client

Usage:
    pip install websockets pyautogui pillow psutil
    python nexum_agent.py
"""

import asyncio
import json
import platform
import subprocess
import base64
import uuid
import sys
import os
import time
import socket
from pathlib import Path
from datetime import datetime

try:
    import websockets
    import psutil
except ImportError:
    print("Installing dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "websockets", "psutil", "pillow"], check=True)
    import websockets
    import psutil

# ─── Config ───────────────────────────────────────────────────────────────
CONFIG_FILE = Path.home() / ".nexum_agent.json"
SERVER_URL  = os.environ.get("NEXUM_SERVER", "ws://localhost:18790")
# For Railway deployment:
# SERVER_URL = "wss://your-project.up.railway.app/ws"  # if using wss

DEVICE_ID   = None
UID         = None   # set after linking

def load_config():
    global DEVICE_ID, UID, SERVER_URL
    if CONFIG_FILE.exists():
        try:
            c = json.loads(CONFIG_FILE.read_text())
            DEVICE_ID = c.get("device_id")
            UID       = c.get("uid")
            if c.get("server_url"):
                SERVER_URL = c["server_url"]
        except:
            pass
    if not DEVICE_ID:
        DEVICE_ID = str(uuid.uuid4())[:8]
        save_config()

def save_config():
    CONFIG_FILE.write_text(json.dumps({
        "device_id": DEVICE_ID,
        "uid": UID,
        "server_url": SERVER_URL,
        "updated": datetime.now().isoformat(),
    }, indent=2))

# ─── System info ──────────────────────────────────────────────────────────
def get_sysinfo() -> str:
    try:
        cpu    = psutil.cpu_percent(interval=0.5)
        ram    = psutil.virtual_memory()
        disk   = psutil.disk_usage("/")
        boot   = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M")
        return (
            f"OS: {platform.system()} {platform.release()}\n"
            f"CPU: {cpu}% ({psutil.cpu_count()} cores)\n"
            f"RAM: {ram.used // 1024**2}MB / {ram.total // 1024**2}MB ({ram.percent}%)\n"
            f"Disk: {disk.used // 1024**3}GB / {disk.total // 1024**3}GB ({disk.percent}%)\n"
            f"Boot: {boot}\n"
            f"Host: {socket.gethostname()}\n"
            f"Python: {platform.python_version()}"
        )
    except Exception as e:
        return f"Error: {e}"

def get_platform() -> str:
    return f"{platform.system()} {platform.release()} ({platform.machine()})"

# ─── Screenshot ───────────────────────────────────────────────────────────
def take_screenshot() -> str | None:
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        try:
            import subprocess
            # Linux fallback
            r = subprocess.run(["scrot", "-o", "/tmp/nexum_ss.png"], capture_output=True)
            if r.returncode == 0:
                return base64.b64encode(open("/tmp/nexum_ss.png", "rb").read()).decode()
        except:
            pass
    except Exception as e:
        print(f"Screenshot error: {e}")
    return None

# ─── Terminal command ─────────────────────────────────────────────────────
def run_command(cmd: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=str(Path.home())
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if out and err:
            return f"{out}\n\nSTDERR:\n{err}"
        return out or err or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Timeout ({timeout}s)"
    except Exception as e:
        return f"Error: {e}"

# ─── File system ──────────────────────────────────────────────────────────
def filesystem_op(op: str, path_str: str, content: str = "") -> str:
    try:
        p = Path(path_str).expanduser()
        if op == "read":
            if not p.exists():
                return f"File not found: {path_str}"
            return p.read_text(errors="replace")[:4000]
        elif op == "write":
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return f"Written: {path_str}"
        elif op == "list":
            if p.is_dir():
                items = list(p.iterdir())[:30]
                return "\n".join(str(i.name) + ("/" if i.is_dir() else "") for i in items)
            return f"Not a directory: {path_str}"
        elif op == "exists":
            return "yes" if p.exists() else "no"
        else:
            return f"Unknown op: {op}"
    except PermissionError:
        return "Permission denied"
    except Exception as e:
        return f"Error: {e}"

# ─── Browser open ─────────────────────────────────────────────────────────
def open_browser(url: str) -> str:
    try:
        import webbrowser
        webbrowser.open(url)
        return f"Opened: {url}"
    except Exception as e:
        return f"Error: {e}"


# ─── Open application ─────────────────────────────────────────────────────
def open_application(app_name: str) -> str:
    """Open an application by name"""
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.Popen(["start", app_name], shell=True)
        elif system == "Darwin":
            subprocess.Popen(["open", "-a", app_name])
        else:
            subprocess.Popen([app_name])
        return f"Opened: {app_name}"
    except Exception as e:
        # Try via xdg-open on Linux
        try:
            subprocess.Popen(["xdg-open", app_name])
            return f"Opened: {app_name}"
        except:
            return f"Error opening {app_name}: {e}"

# ─── Mouse and keyboard control ──────────────────────────────────────────
def mouse_control(action: str, x: int = 0, y: int = 0, text: str = "") -> str:
    """Control mouse and keyboard using pyautogui"""
    try:
        import pyautogui
        pyautogui.FAILSAFE = True  # Move mouse to top-left corner to abort
        
        if action == "click":
            pyautogui.click(x, y)
            return f"Clicked at ({x}, {y})"
        elif action == "move":
            pyautogui.moveTo(x, y, duration=0.3)
            return f"Moved to ({x}, {y})"
        elif action == "double_click":
            pyautogui.doubleClick(x, y)
            return f"Double-clicked at ({x}, {y})"
        elif action == "right_click":
            pyautogui.rightClick(x, y)
            return f"Right-clicked at ({x}, {y})"
        elif action == "type":
            pyautogui.typewrite(text, interval=0.05)
            return f"Typed: {text[:50]}"
        elif action == "hotkey":
            keys = text.split("+")
            pyautogui.hotkey(*keys)
            return f"Hotkey: {text}"
        elif action == "scroll":
            pyautogui.scroll(x, y)
            return f"Scrolled {x}"
        elif action == "position":
            pos = pyautogui.position()
            return f"Mouse at ({pos.x}, {pos.y})"
        else:
            return f"Unknown action: {action}"
    except ImportError:
        return "pyautogui not installed. Run: pip install pyautogui"
    except Exception as e:
        return f"Mouse/keyboard error: {e}"

# ─── Main agent loop ──────────────────────────────────────────────────────
async def agent_loop():
    global UID

    reconnect_delay = 2
    linked = UID is not None

    while True:
        try:
            print(f"\n🔌 Connecting to NEXUM server: {SERVER_URL}")
            async with websockets.connect(SERVER_URL, ping_interval=25, ping_timeout=10) as ws:
                reconnect_delay = 2  # reset on success

                if linked and UID:
                    # Already linked — register with uid
                    await ws.send(json.dumps({
                        "type":      "register",
                        "uid":       UID,
                        "device_id": DEVICE_ID,
                        "name":      socket.gethostname(),
                        "platform":  get_platform(),
                        "mode":      "SAFE",
                        "version":   "5.0.0",
                        "sysinfo":   {"cpu": psutil.cpu_count(), "os": platform.system()},
                    }))
                    print(f"✅ Registered as uid={UID}")
                else:
                    # Not linked — request linking code
                    await ws.send(json.dumps({
                        "type":      "request_link",
                        "device_id": DEVICE_ID,
                        "platform":  get_platform(),
                    }))
                    print("⏳ Requesting linking code...")

                # Heartbeat task
                async def heartbeat():
                    while True:
                        await asyncio.sleep(20)
                        try:
                            await ws.send(json.dumps({"type": "ping"}))
                        except:
                            break

                hb_task = asyncio.create_task(heartbeat())

                try:
                    async for raw in ws:
                        msg = json.loads(raw)
                        mtype = msg.get("type")

                        if mtype == "link_code":
                            code = msg.get("code")
                            print("\n" + "="*50)
                            print(f"  🔑 LINKING CODE: {code}")
                            print(f"  Send to bot: /link {code}")
                            print("="*50 + "\n")

                        elif mtype == "linked":
                            UID    = msg.get("uid")
                            linked = True
                            save_config()
                            print(f"\n✅ Linked to Telegram account uid={UID}")

                        elif mtype == "registered":
                            print("✅ Agent active and waiting for commands")

                        elif mtype == "need_link":
                            linked = False
                            await ws.send(json.dumps({
                                "type":      "request_link",
                                "device_id": DEVICE_ID,
                                "platform":  get_platform(),
                            }))

                        elif mtype == "screenshot":
                            req_id  = msg.get("reqId")
                            chat_id = msg.get("chatId")
                            print("📸 Taking screenshot...")
                            b64 = take_screenshot()
                            await ws.send(json.dumps({
                                "type":    "screenshot_result",
                                "reqId":   req_id,
                                "chatId":  chat_id,
                                "data":    b64 or "",
                            }))

                        elif mtype == "run":
                            req_id = msg.get("reqId")
                            cmd    = msg.get("command", "")
                            print(f"⚙️  Running: {cmd}")
                            result = run_command(cmd)
                            await ws.send(json.dumps({
                                "type":  "result",
                                "reqId": req_id,
                                "data":  result[:3000],
                            }))

                        elif mtype == "sysinfo":
                            req_id = msg.get("reqId")
                            info   = get_sysinfo()
                            await ws.send(json.dumps({
                                "type":  "result",
                                "reqId": req_id,
                                "data":  info,
                            }))

                        elif mtype == "filesystem":
                            req_id  = msg.get("reqId")
                            payload = msg.get("input", "")
                            # Expected: "read:/path/to/file" or "list:/path"
                            parts   = payload.split(":", 1)
                            op      = parts[0] if len(parts) > 1 else "read"
                            fpath   = parts[1] if len(parts) > 1 else payload
                            result  = filesystem_op(op, fpath)
                            await ws.send(json.dumps({
                                "type":  "result",
                                "reqId": req_id,
                                "data":  result[:3000],
                            }))

                        elif mtype == "browser":
                            req_id = msg.get("reqId")
                            url    = msg.get("input", "")
                            result = open_browser(url)
                            await ws.send(json.dumps({
                                "type":  "result",
                                "reqId": req_id,
                                "data":  result,
                            }))

                        elif mtype == "open_app":
                            req_id  = msg.get("reqId")
                            app     = msg.get("input", "")
                            print(f"🚀 Opening app: {app}")
                            result  = open_application(app)
                            await ws.send(json.dumps({
                                "type":  "result",
                                "reqId": req_id,
                                "data":  result,
                            }))

                        elif mtype == "mouse":
                            req_id = msg.get("reqId")
                            action = msg.get("action", "position")
                            x      = int(msg.get("x", 0))
                            y      = int(msg.get("y", 0))
                            text   = msg.get("text", "")
                            print(f"🖱  Mouse: {action} ({x},{y})")
                            result = mouse_control(action, x, y, text)
                            await ws.send(json.dumps({
                                "type":  "result",
                                "reqId": req_id,
                                "data":  result,
                            }))

                        elif mtype == "keyboard":
                            req_id = msg.get("reqId")
                            text   = msg.get("text", "")
                            action = msg.get("action", "type")
                            print(f"⌨️  Keyboard: {action} '{text[:20]}'")
                            result = mouse_control(action, 0, 0, text)
                            await ws.send(json.dumps({
                                "type":  "result",
                                "reqId": req_id,
                                "data":  result,
                            }))

                        elif mtype == "pong":
                            pass  # heartbeat OK

                finally:
                    hb_task.cancel()

        except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            print(f"⚠️  Disconnected: {e}. Reconnecting in {reconnect_delay}s...")
        except Exception as e:
            print(f"❌ Error: {e}. Reconnecting in {reconnect_delay}s...")

        await asyncio.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, 30)

# ─── Entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  NEXUM PC Agent v5.0")
    print("  Autonomous AI Agent for Telegram")
    print("=" * 50)

    # Allow overriding server URL
    if len(sys.argv) > 1:
        SERVER_URL = sys.argv[1]

    load_config()
    print(f"Device ID: {DEVICE_ID}")
    print(f"Server:    {SERVER_URL}")
    if UID:
        print(f"Linked UID: {UID}")
    else:
        print("Status:    Not linked (will show linking code)")
    print()

    try:
        asyncio.run(agent_loop())
    except KeyboardInterrupt:
        print("\n👋 NEXUM Agent stopped.")
