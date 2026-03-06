import asyncio
import logging
import os
import sqlite3
import datetime
import httpx

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

# =========================
# 🔥 ВСТАВЬ СЮДА ТОКЕН
# =========================

TELEGRAM_TOKEN = "8758082038:AAHKQ-8fmD64to0GINZYLtTbVNxh8Y_NAlU"

# =========================
# OLLAMA НАСТРОЙКИ
# =========================

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3:8b"

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher(storage=MemoryStorage())

# =========================
# БАЗА ДАННЫХ
# =========================

conn = sqlite3.connect("nexum.db")
cursor = conn.cursor()

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

# =========================
# LLM
# =========================

async def generate_text(prompt: str):
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False
                }
            )
        data = response.json()
        return data.get("response", "Нет ответа.")
    except Exception as e:
        return f"Ошибка LLM: {e}"

# =========================
# НАПОМИНАНИЯ
# =========================

async def reminder_loop():
    while True:
        now = datetime.datetime.utcnow().isoformat()
        cursor.execute("SELECT id, user_id, text FROM reminders WHERE remind_at <= ? AND sent=0", (now,))
        rows = cursor.fetchall()

        for rid, user_id, text in rows:
            try:
                await bot.send_message(user_id, f"⏰ Напоминание:\n{text}")
                cursor.execute("UPDATE reminders SET sent=1 WHERE id=?", (rid,))
                conn.commit()
            except:
                pass

        await asyncio.sleep(10)

# =========================
# /start
# =========================

@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer("👋 Привет. Я NEXUM PRO.\nНапиши задачу.")

# =========================
# /remind
# =========================

@dp.message(Command("remind"))
async def remind_handler(message: Message):
    try:
        parts = message.text.split(" ", 2)
        minutes = int(parts[1])
        text = parts[2]

        remind_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes)

        cursor.execute(
            "INSERT INTO reminders (user_id, text, remind_at) VALUES (?, ?, ?)",
            (message.from_user.id, text, remind_time.isoformat())
        )
        conn.commit()

        await message.answer(f"⏳ Напомню через {minutes} минут.")

    except:
        await message.answer("Используй: /remind 10 Текст напоминания")

# =========================
# ВСЕ СООБЩЕНИЯ
# =========================

@dp.message()
async def chat_handler(message: Message):

    # Группы — отвечаем если упомянули
    if message.chat.type != "private":
        me = await bot.get_me()
        if not message.text or f"@{me.username}" not in message.text:
            return

    if message.photo:
        await message.answer("📷 Фото получено (анализ добавим позже).")
        return

    if message.voice:
        await message.answer("🎤 Голос получен (распознавание добавим позже).")
        return

    if message.video:
        await message.answer("🎥 Видео получено.")
        return

    if not message.text:
        return

    await message.answer("💭 Думаю...")

    response = await generate_text(message.text)
    await message.answer(response)

# =========================
# MAIN
# =========================

async def main():
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())