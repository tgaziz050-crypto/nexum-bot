"""
NEXUM PC Agent v13.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Полностью автономный агент для управления ПК через Telegram.

Режимы безопасности:
  AUTO   — все команды выполняются автоматически
  SAFE   — опасные команды требуют подтверждения в Telegram (кнопки Да/Нет)

Установка зависимостей:
  pip install websockets pyautogui pillow psutil

Настройка:
  Задай переменные среды или отредактируй секцию CONFIG ниже.

Автозапуск Windows:
  Запусти install_windows.bat

Автозапуск Linux/Mac:
  Запусти: sudo python nexum_agent.py --install-service
"""

import asyncio
import os
import json
import base64
import io
import platform
import sys
import datetime
import subprocess
import re

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIG — задай через переменные среды или здесь напрямую
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WS_URL        = os.getenv("NEXUM_WS_URL",   "ws://localhost:18790")
OWNER_ID      = int(os.getenv("NEXUM_OWNER_ID", "0"))
AGENT_VERSION = "13.0"
# SAFE = опасные команды → подтверждение в Telegram
# AUTO = всё выполняется автоматически
MODE          = os.getenv("NEXUM_MODE", "SAFE")

LOG_FILE = os.path.join(os.path.expanduser("~"), ".nexum_audit.log")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DANGER PATTERNS — паттерны "опасных" команд (SAFE mode)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DANGER_PATTERNS = [
    r'\brm\b.*-rf?',           # rm -rf
    r'\bdel\b.*\/[sqa]',       # del /s /q /a
    r'\bformat\b',             # format disk
    r'\brmdir\b',              # rmdir
    r'\bdiskpart\b',           # diskpart
    r'\bdd\b.*of=',            # dd if/of
    r'\bsudo\b',               # sudo anything
    r'\bchmod\b.*777',         # chmod 777
    r'\bsystemctl\b.*stop',    # stop services
    r'\bpoweroff\b|\bshutdown\b|\breboot\b',  # power commands
    r'\bcurl\b.*\|\s*bash',    # curl | bash
    r'\bwget\b.*\|\s*sh',      # wget | sh
    r'\bpip\b.*install',       # pip install
    r'\bapt\b.*install',       # apt install
    r'\bchoco\b.*install',     # choco install
    r'\bwinrm\b|\bpsexec\b',   # remote execution
    r'>\s*/etc/',              # redirect to /etc
    r'>\s*C:\\Windows',        # redirect to Windows dir
    r'\bregistry\b|\bregedit\b|\breg\s+add\b|\breg\s+delete\b',  # registry
    r'\bnet\s+user\b',         # net user (account management)
    r'\bschtasks\b.*\/create', # schtasks create
    r'\bsc\b.*create\b',       # sc create service
    r'eval\s*\(',              # eval
    r'exec\s*\(',              # exec
]

def is_dangerous(cmd: str) -> bool:
    cmd_lower = cmd.lower()
    return any(re.search(p, cmd_lower) for p in DANGER_PATTERNS)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AUDIT LOG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def audit(action: str, detail: str, status: str):
    ts   = datetime.datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] [{status}] {action}: {detail[:300]}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    print(f"  AUDIT {status}: {action}: {detail[:80]}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SCREENSHOT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def take_screenshot() -> str:
    try:
        import pyautogui
        from PIL import Image
        img = pyautogui.screenshot()
        img = img.resize((1280, 720), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"  Screenshot error: {e}")
        return ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SYSTEM INFO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_sysinfo() -> dict:
    info = {
        "platform": f"{platform.system()} {platform.release()}",
        "hostname": platform.node(),
        "cpu_count": os.cpu_count(),
    }
    try:
        import psutil
        info["cpu_percent"] = psutil.cpu_percent(interval=0.5)
        info["ram_used_gb"] = round(psutil.virtual_memory().used / 1e9, 1)
        info["ram_total_gb"] = round(psutil.virtual_memory().total / 1e9, 1)
        info["ram_percent"] = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/")
        info["disk_free_gb"] = round(disk.free / 1e9, 1)
        info["disk_total_gb"] = round(disk.total / 1e9, 1)
    except Exception:
        pass
    return info

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND EXECUTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def exec_cmd(cmd: str, timeout: int = 30) -> str:
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return f"❌ Timeout ({timeout}s): команда убита"

        out = stdout.decode(errors="replace").strip()
        err = stderr.decode(errors="replace").strip()
        result = out
        if err:
            result += f"\n[stderr] {err}"
        return result.strip()[:4000] or "(нет вывода)"
    except Exception as e:
        return f"❌ Ошибка: {e}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PENDING CONFIRMATIONS (taskId → callback)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
pending_confirms: dict[str, asyncio.Future] = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN AGENT LOOP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def main():
    if not OWNER_ID:
        print("❌ Задай NEXUM_OWNER_ID!")
        sys.exit(1)

    name = platform.node() or "PC"
    plat = f"{platform.system()} {platform.release()}"

    print("=" * 55)
    print(f"  NEXUM PC Agent v{AGENT_VERSION}")
    print(f"  Device  : {name} ({plat})")
    print(f"  Owner   : {OWNER_ID}")
    print(f"  Server  : {WS_URL}")
    print(f"  Mode    : {MODE}")
    print(f"  Audit   : {LOG_FILE}")
    print("=" * 55)

    try:
        import websockets
    except ImportError:
        print("❌ pip install websockets pyautogui pillow psutil")
        sys.exit(1)

    reconnect_delay = 5
    ws_ref = None  # держим ссылку на ws для отправки уведомлений

    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=30) as ws:
                ws_ref = ws

                await ws.send(json.dumps({
                    "type": "register",
                    "uid": OWNER_ID,
                    "name": name,
                    "platform": plat,
                    "version": AGENT_VERSION,
                    "mode": MODE,
                    "sysinfo": get_sysinfo(),
                }))
                print(f"✅ Подключён к NEXUM gateway")
                reconnect_delay = 5

                # Heartbeat
                async def heartbeat():
                    while True:
                        await asyncio.sleep(30)
                        try:
                            await ws.send(json.dumps({
                                "type": "heartbeat",
                                "uid": OWNER_ID,
                                "sysinfo": get_sysinfo(),
                            }))
                        except Exception:
                            break

                hb = asyncio.create_task(heartbeat())

                async for raw in ws:
                    try:
                        msg   = json.loads(raw)
                        mtype = msg.get("type")

                        # ── Registered ─────────────────────────────────
                        if mtype == "registered":
                            print("✅ Агент зарегистрирован — Telegram уведомлён")

                        # ── Heartbeat OK ────────────────────────────────
                        elif mtype == "heartbeat_ok":
                            pass

                        # ── Execute command ─────────────────────────────
                        elif mtype == "exec":
                            cmd    = msg.get("cmd", "").strip()
                            taskId = msg.get("taskId", "")
                            if not cmd:
                                continue

                            danger = is_dangerous(cmd)

                            # SAFE mode + опасная команда → запрос в Telegram
                            if MODE == "SAFE" and danger:
                                print(f"  ⚠️  Опасная команда, запрос подтверждения: {cmd[:60]}")
                                audit("exec_request", cmd, "PENDING")

                                # Отправляем запрос на подтверждение в бот
                                await ws.send(json.dumps({
                                    "type":   "confirm_request",
                                    "uid":    OWNER_ID,
                                    "taskId": taskId,
                                    "cmd":    cmd,
                                }))

                                # Ждём ответ (таймаут 60 сек)
                                loop = asyncio.get_event_loop()
                                fut  = loop.create_future()
                                pending_confirms[taskId] = fut

                                try:
                                    approved = await asyncio.wait_for(fut, timeout=60)
                                except asyncio.TimeoutError:
                                    approved = False
                                    pending_confirms.pop(taskId, None)

                                audit("exec", cmd, "APPROVED" if approved else "REJECTED")

                                if approved:
                                    print(f"  ✅ Подтверждено, выполняю: {cmd[:60]}")
                                    result = await exec_cmd(cmd)
                                else:
                                    result = "❌ Отклонено пользователем в Telegram"
                                    print(f"  🚫 Отклонено")

                            else:
                                # AUTO mode или безопасная команда
                                audit("exec", cmd, "AUTO")
                                print(f"  ▶ {cmd[:80]}")
                                result = await exec_cmd(cmd)
                                print(f"  ✓ done: {result[:60]}")

                            await ws.send(json.dumps({
                                "type":   "result",
                                "taskId": taskId,
                                "result": result,
                            }))

                        # ── Confirm response (от бота) ──────────────────
                        elif mtype == "confirm_response":
                            taskId  = msg.get("taskId", "")
                            approved = msg.get("approved", False)
                            if taskId in pending_confirms:
                                fut = pending_confirms.pop(taskId)
                                if not fut.done():
                                    fut.set_result(approved)

                        # ── Screenshot ──────────────────────────────────
                        elif mtype == "screenshot":
                            chat_id = msg.get("chatId")
                            audit("screenshot", f"chatId={chat_id}", "AUTO")
                            print(f"  📸 Скриншот...")
                            data = await take_screenshot()
                            if data:
                                await ws.send(json.dumps({
                                    "type":   "screenshot",
                                    "chatId": chat_id,
                                    "data":   data,
                                }))
                                print("  ✅ Скриншот отправлен")
                            else:
                                print("  ❌ Ошибка скриншота")

                        # ── Sysinfo request ─────────────────────────────
                        elif mtype == "sysinfo":
                            await ws.send(json.dumps({
                                "type":    "sysinfo_response",
                                "uid":     OWNER_ID,
                                "taskId":  msg.get("taskId", ""),
                                "sysinfo": get_sysinfo(),
                            }))

                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        print(f"  Ошибка обработки сообщения: {e}")

                hb.cancel()

        except Exception as e:
            print(f"❌ Соединение потеряно: {e}")
            print(f"  Переподключение через {reconnect_delay}с...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INSTALL SERVICE (Linux/Mac)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def install_systemd_service():
    python  = sys.executable
    script  = os.path.abspath(__file__)
    service = f"""[Unit]
Description=NEXUM PC Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={os.getenv("USER", "user")}
Environment=NEXUM_WS_URL={WS_URL}
Environment=NEXUM_OWNER_ID={OWNER_ID}
Environment=NEXUM_MODE={MODE}
ExecStart={python} {script}
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    path = "/etc/systemd/system/nexum-agent.service"
    try:
        with open(path, "w") as f:
            f.write(service)
        os.system("systemctl daemon-reload")
        os.system("systemctl enable nexum-agent")
        os.system("systemctl start nexum-agent")
        print(f"✅ Systemd сервис установлен и запущен")
        print(f"   Управление: systemctl status nexum-agent")
    except PermissionError:
        print("❌ Запусти с sudo: sudo python nexum_agent.py --install-service")


if __name__ == "__main__":
    if "--install-service" in sys.argv:
        install_systemd_service()
        sys.exit(0)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 NEXUM Agent остановлен.")
