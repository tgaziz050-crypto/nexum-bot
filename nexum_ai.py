import asyncio
import logging
import sqlite3
import datetime
import os
import tempfile
import requests
import httpx
import whisper

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

# ==============================
# 🔐 ВСТАВЬ СЮДА ТОКЕН
# ==============================
TELEGRAM_TOKEN = "8758082038:AAHKQ-8fmD64to0GINZYLtTbVNxh8Y_NAlU"

# ==============================
# МОДЕЛИ
# ==============================
TEXT_MODEL = "phi3"
VISION_MODEL = "llava"

OLLAMA_URL = "http://localhost:11434/api/generate"

# ==============================
# НАСТРОЙКА
# ==============================
logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher(storage=MemoryStorage())

whisper_model = whisper.load_model("base")

# ==============================
# БАЗА ДАННЫХ
# ==============================
conn = sqlite3.connect("nexum.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS memory (
    user_id INTEGER,
    role TEXT,
    content TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    text TEXT,
    remind_at TEXT,
    sent INTEGER DEFAULT 0
)
""")

conn.commit()

# ==============================
# СИСТЕМНЫЙ ПРОМПТ
# ==============================
SYSTEM_PROMPT = """
Ты NEXUM — персональный AI помощник.

Правила:
- отвечай кратко
- структурируй
- не говори что ты языковая модель
- если не знаешь — скажи честно
- не выдумывай факты
- ориентируйся на предпринимателей и людей дела
"""

# ==============================
# LLM ВЫЗОВ
# ==============================
async def call_model(model, prompt):
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False
            }
        )
    return response.json().get("response", "")

async def generate_text(user_id, user_text):
    cursor.execute(
        "SELECT role, content FROM memory WHERE user_id=? ORDER BY rowid DESC LIMIT 8",
        (user_id,)
    )
    history = cursor.fetchall()

    history_text = "\n".join(
        [f"{r}: {c}" for r, c in reversed(history)]
    )

    prompt = f"""
{SYSTEM_PROMPT}

История диалога:
{history_text}

Пользователь:
{user_text}

Ответ:
"""

    response = await call_model(TEXT_MODEL, prompt)

    cursor.execute("INSERT INTO memory VALUES (?,?,?)",
                   (user_id, "user", user_text))
    cursor.execute("INSERT INTO memory VALUES (?,?,?)",
                   (user_id, "assistant", response))
    conn.commit()

    return response

# ==============================
# НАПОМИНАНИЯ
# ==============================
async def reminder_loop():
    while True:
        now = datetime.datetime.utcnow().isoformat()

        cursor.execute(
            "SELECT id, user_id, text FROM reminders WHERE remind_at<=? AND sent=0",
            (now,)
        )
        rows = cursor.fetchall()

        for rid, uid, text in rows:
            await bot.send_message(uid, f"⏰ Напоминание:\n{text}")
            cursor.execute("UPDATE reminders SET sent=1 WHERE id=?", (rid,))
            conn.commit()

        await asyncio.sleep(15)

@dp.message(Command("remind"))
async def set_reminder(message: Message):
    try:
        parts = message.text.split(" ", 2)
        minutes = int(parts[1])
        text = parts[2]

        remind_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes)

        cursor.execute(
            "INSERT INTO reminders (user_id,text,remind_at) VALUES (?,?,?)",
            (message.from_user.id, text, remind_time.isoformat())
        )
        conn.commit()

        await message.answer("Напоминание поставлено.")
    except:
        await message.answer("Формат: /remind 10 текст")

# ==============================
# ОБРАБОТКА ВСЕГО
# ==============================
@dp.message()
async def handle_all(message: Message):

    # -------- Фото --------
    if message.photo:
        await message.answer("📷 Анализирую фото...")

        file = await bot.get_file(message.photo[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"

        result = await call_model(
            VISION_MODEL,
            f"Опиши изображение: {file_url}"
        )

        await message.answer(result)
        return

    # -------- Голос --------
    if message.voice:
        await message.answer("🎤 Распознаю голос...")

        file = await bot.get_file(message.voice.file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"

        r = requests.get(file_url)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            tmp.write(r.content)
            tmp_path = tmp.name

        result = whisper_model.transcribe(tmp_path)
        text = result["text"]

        os.remove(tmp_path)

        response = await generate_text(message.from_user.id, text)
        await message.answer(response)
        return

    # -------- Группы --------
    if message.chat.type != "private":
        me = await bot.get_me()
        if not message.text or f"@{me.username}" not in message.text:
            return

    if not message.text:
        return

    await message.answer("💭")

    response = await generate_text(message.from_user.id, message.text)
    await message.answer(response)

# ==============================
# START
# ==============================
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "NEXUM.\n"
        "Персональный AI помощник.\n"
        "Сформулируй задачу."
    )

# ==============================
# MAIN
# ==============================
async def main():
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())