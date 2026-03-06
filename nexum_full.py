# nexum_agent.py
import os
import json
import asyncio
import logging
import sqlite3
import tempfile
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import httpx
from dateutil import parser as dt_parser
from PIL import Image
import ffmpeg  # ffmpeg-python wrapper

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage

# Optional OpenAI fallback (install openai if you want fallback)
try:
    import openai
    HAVE_OPENAI = True
except Exception:
    HAVE_OPENAI = False

# ----------------- CONFIG -----------------
# preferred: set these as environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or "8758082038:AAHKQ-8fmD64to0GINZYLtTbVNxh8Y_NAlU"
# Ollama local server (if you run Ollama serve) default:
OLLAMA_URL = os.getenv("OLLAMA_URL") or "http://localhost:11434"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL") or "llama3:8b"  # or "llama3:70b" etc

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or None  # optional

# Basic safety / admins (comma separated telegram ids)
ADMINS = os.getenv("ADMINS", "")  # e.g. "123456789,987654321"
ADMINS = [int(x) for x in ADMINS.split(",") if x.strip().isdigit()]

DATA_DIR = os.path.join(os.path.dirname(__file__), "nexum_data")
MEDIA_DIR = os.path.join(DATA_DIR, "media")
os.makedirs(MEDIA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "nexum.db")

# ----------------- SETUP -----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexum")

from aiogram.client.default import DefaultBotProperties

bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher(storage=MemoryStorage())

if HAVE_OPENAI and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# ----------------- DB -----------------
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS memory (
    user_id INTEGER,
    key TEXT,
    value TEXT,
    PRIMARY KEY(user_id, key)
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    remind_at TEXT,
    text TEXT,
    sent INTEGER DEFAULT 0
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_id INTEGER,
    chat_id INTEGER,
    action_json TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# ----------------- UTIL -----------------
def save_file_bytes(prefix: str, data: bytes, suffix: str):
    fname = f"{prefix}_{int(datetime.utcnow().timestamp())}{suffix}"
    path = os.path.join(MEDIA_DIR, fname)
    with open(path, "wb") as f:
        f.write(data)
    return path

async def convert_to_wav(input_path: str) -> Optional[str]:
    try:
        out_path = input_path + ".wav"
        (
            ffmpeg
            .input(input_path)
            .output(out_path, format="wav", acodec="pcm_s16le", ac=1, ar="16000")
            .overwrite_output()
            .run(quiet=True)
        )
        return out_path
    except Exception as e:
        logger.exception("ffmpeg convert failed: %s", e)
        return None

def parse_relative_time(text: str) -> Optional[datetime]:
    text = text.strip().lower()
    if text.startswith("in "):
        body = text[3:].strip()
        try:
            if body.endswith("m"):
                return datetime.utcnow() + timedelta(minutes=int(body[:-1]))
            if body.endswith("h"):
                return datetime.utcnow() + timedelta(hours=int(body[:-1]))
            if body.endswith("d"):
                return datetime.utcnow() + timedelta(days=int(body[:-1]))
        except Exception:
            return None
    try:
        return dt_parser.parse(text)
    except Exception:
        return None

def get_memory_all(user_id: int) -> Dict[str, str]:
    cursor.execute("SELECT key, value FROM memory WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()
    return {k: v for k, v in rows}

def set_memory(user_id: int, key: str, value: str):
    cursor.execute("REPLACE INTO memory (user_id, key, value) VALUES (?, ?, ?)", (user_id, key, value))
    conn.commit()

# ----------------- LLM ABSTRACTION -----------------
async def call_ollama_generate(prompt: str, model: str = OLLAMA_MODEL, timeout: int = 60) -> Optional[str]:
    """
    Calls local Ollama server at /api/generate (simplified).
    Adjust body if your Ollama version expects different payload.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            payload = {
                "model": model,
                "prompt": prompt,
                "max_tokens": 1024,
                "temperature": 0.7,
                "stream": False
            }
            url = OLLAMA_URL.rstrip("/") + "/api/generate"
            r = await client.post(url, json=payload)
            if r.status_code != 200:
                logger.warning("Ollama returned %s: %s", r.status_code, r.text)
                return None
            data = r.json()
            # different Ollama versions may have different shape — try to find text
            if isinstance(data, dict):
                # try keys
                if "response" in data:
                    return data["response"]
                if "text" in data:
                    return data["text"]
                # attempt known shape:
                # for some Ollama: { "choices": [ {"message": {"content": "..."}} ]}
                choices = data.get("choices") or []
                if choices:
                    first = choices[0]
                    if isinstance(first, dict):
                        msg = first.get("message") or {}
                        return msg.get("content") or first.get("text") or None
            return None
    except Exception as e:
        logger.exception("Ollama call failed: %s", e)
        return None

async def call_openai_chat(prompt: str, timeout: int = 60) -> Optional[str]:
    if not HAVE_OPENAI or not openai.api_key:
        return None
    try:
        # Use blocking call in thread because openai lib may be sync
        def blocking():
            return openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are NEXUM, an assistant that must reply in plain text or JSON when instructed."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1024,
                temperature=0.7
            )
        resp = await asyncio.to_thread(blocking)
        return resp["choices"][0]["message"]["content"]
    except Exception as e:
        logger.exception("OpenAI call failed: %s", e)
        return None

async def llm_generate(prompt: str) -> str:
    """
    Try Ollama -> OpenAI -> fallback echo.
    """
    # try Ollama
    out = await call_ollama_generate(prompt)
    if out:
        return out
    # try OpenAI fallback
    out = await call_openai_chat(prompt)
    if out:
        return out
    # fallback
    return "(no LLM available) " + prompt[:400]

# ----------------- AGENT BRAIN -----------------
async def agent_brain(user_text: str, user_id: int, chat_id: int) -> str:
    """
    Agent prompt asks model to return JSON decision if it wants to call a tool.
    Otherwise respond with plain text.
    """
    memory = get_memory_all(user_id)
    memory_text = "\n".join([f"{k}: {v}" for k, v in memory.items()]) or "(no memory)"

    system = (
        "You are NEXUM, an autonomous assistant. "
        "When the user message requires calling a tool, respond ONLY with a JSON object (no extra text) "
        "with the shape {\"action\":\"tool_name\", \"parameters\":{...}}. "
        "If you just want to reply to the user, respond with JSON: {\"action\":\"respond\",\"text\":\"...\"}.\n\n"
        "Available tools:\n"
        " - send_message: send a message to the chat. parameters: chat_id (int), text (string)\n"
        " - save_memory: save key/value. parameters: key, value\n"
        " - create_reminder: schedule reminder. parameters: in_time (e.g. 'in 10m' or ISO), text\n"
        " - generate_code: ask to produce code snippet. parameters: prompt (string)\n\n"
        "Security: Do NOT request tools other than listed. If unsure, answer textually.\n"
    )

    prompt = f"{system}\nUSER: {user_text}\n\nMemory:\n{memory_text}\n\nRespond JSON only."

    resp = await llm_generate(prompt)

    # try parse JSON
    try:
        decision = json.loads(resp.strip())
    except Exception:
        # Not JSON — treat whole resp as textual reply
        return resp

    action = decision.get("action")
    if not action:
        return "Непонятное действие от агента."

    # ACTION: respond
    if action == "respond":
        return decision.get("text", "(no text)")

    # ACTION: save_memory
    if action == "save_memory":
        params = decision.get("parameters", {})
        key = params.get("key")
        value = params.get("value")
        if key and value is not None:
            set_memory(user_id, key, value)
            return f"Запомнил `{key}`."
        return "Некорректные параметры для save_memory."

    # ACTION: create_reminder
    if action == "create_reminder":
        params = decision.get("parameters", {})
        in_time = params.get("in_time")
        text = params.get("text", "")
        dt = parse_relative_time(in_time) if in_time else None
        if not dt:
            return "Не понял время. Используй формат `in 10m` или ISO."
        cursor.execute("INSERT INTO reminders (user_id, remind_at, text) VALUES (?, ?, ?)",
                       (user_id, dt.isoformat(), text))
        conn.commit()
        return f"Напоминание создано на {dt.isoformat()} (UTC)."

    # ACTION: send_message (only allowed from agent decisions for safety)
    if action == "send_message":
        params = decision.get("parameters", {})
        target_chat = params.get("chat_id")
        text = params.get("text", "")
        try:
            await bot.send_message(target_chat or chat_id, text)
            return "Сообщение отправлено."
        except Exception as e:
            logger.exception("send_message failed: %s", e)
            return "Не удалось отправить сообщение."

    # ACTION: generate_code
    if action == "generate_code":
        params = decision.get("parameters", {})
        prompt_code = params.get("prompt", "")
        # We ask the LLM to generate code — call LLM as usual
        code = await llm_generate("Write only the code (no extra commentary):\n\n" + prompt_code)
        return f"```python\n{code}\n```"

    return "Действие не поддерживается."

# ----------------- HANDLERS -----------------
from aiogram.filters import Command
from aiogram.types import Message

@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "👋 Привет.\n"
        "Я NEXUM — твой AI помощник.\n\n"
        "Просто напиши задачу."
    )


@dp.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "/start — перезапуск\n"
        "Просто напиши текст — я отвечу\n"
    )


@dp.message()
async def chat_handler(message: Message):
    if not message.text:
        return

    response = await generate_text(message.text)
    await message.answer(response)

# ----------------- MAIN -----------------
async def main():
    logger.info("Starting bot...")
    # start background tasks
    asyncio.create_task(reminders_loop())
    asyncio.create_task(tasks_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")