import asyncio
import aiohttp
import sqlite3
import os
import logging
import whisper
from datetime import datetime

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ================== CONFIG ==================

TELEGRAM_TOKEN = "8758082038:AAHKQ-8fmD64to0GINZYLtTbVNxh8Y_NAlU"
MODEL_TEXT = "phi3:latest"
MODEL_VISION = "llava:latest"
OLLAMA_URL = "http://localhost:11434/api/generate"

DATA_DIR = "nexum_data"
DB_PATH = os.path.join(DATA_DIR, "nexum.db")

os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)

# ================== BOT INIT ==================

bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

# ================== DATABASE ==================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            remind_at TEXT,
            sent INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ================== MEMORY ==================

def save_memory(user_id, role, content):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory (user_id, role, content) VALUES (?, ?, ?)",
        (user_id, role, content)
    )
    conn.commit()
    conn.close()

def get_memory(user_id, limit=10):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content FROM memory WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit)
    )
    rows = cur.fetchall()
    conn.close()
    rows.reverse()
    return rows

def clear_memory(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM memory WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

# ================== OLLAMA ==================

async def generate(prompt, model):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OLLAMA_URL,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_thread": 8,
                        "temperature": 0.7,
                        "num_predict": 512
                    }
                }
            ) as resp:

                if resp.status != 200:
                    return "Ошибка модели."

                data = await resp.json()
                result = data.get("response", "").strip()

                if not result:
                    return "Модель не вернула ответ."

                return result

    except Exception as e:
        logging.error(f"OLLAMA ERROR: {e}")
        return "Ошибка генерации."

# ================== PROMPT ==================

def build_prompt(user_id, text):
    memory = get_memory(user_id)
    context = ""

    for role, content in memory:
        context += f"{role.upper()}: {content}\n"

    context += f"USER: {text}\nASSISTANT:"
    return context

# ================== REMINDERS ==================

async def reminder_loop():
    while True:
        await asyncio.sleep(10)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT id, user_id, text FROM reminders WHERE remind_at <= ? AND sent=0",
            (now,)
        )
        rows = cur.fetchall()

        for r_id, user_id, text in rows:
            try:
                await bot.send_message(user_id, f"⏰ Напоминание:\n{text}")
                cur.execute("UPDATE reminders SET sent=1 WHERE id=?", (r_id,))
                conn.commit()
            except:
                pass

        conn.close()

# ================== COMMANDS ==================

@router.message(CommandStart())
async def start_handler(message: Message):
    await message.answer("🚀 NEXUM 4.0 активен.")

@router.message(Command("clear"))
async def clear_handler(message: Message):
    clear_memory(message.from_user.id)
    await message.answer("Память очищена.")

@router.message(Command("stats"))
async def stats_handler(message: Message):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM memory WHERE user_id=?",
        (message.from_user.id,)
    )
    count = cur.fetchone()[0]
    conn.close()
    await message.answer(f"Сообщений в памяти: {count}")

# ================== MAIN HANDLER ==================

@router.message()
async def main_handler(message: Message):

    user_id = message.from_user.id

    # --- VOICE ---
    if message.voice:
        await message.answer("🎤 Распознаю голос...")

        file = await bot.get_file(message.voice.file_id)
        audio_path = os.path.join(DATA_DIR, "voice.ogg")
        await bot.download_file(file.file_path, audio_path)

        model = whisper.load_model("base")
        result = model.transcribe(audio_path)
        text = result["text"].strip()

        if not text:
            await message.answer("Не удалось распознать.")
            return

        save_memory(user_id, "user", text)
        prompt = build_prompt(user_id, text)
        answer = await generate(prompt, MODEL_TEXT)
        save_memory(user_id, "assistant", answer)

        await message.answer(answer[:4000])
        return

    # --- PHOTO ---
    if message.photo:
        await message.answer("🖼 Анализирую фото...")
        caption = message.caption or "Опиши изображение"
        answer = await generate(caption, MODEL_VISION)
        await message.answer(answer[:4000])
        return

    # --- TEXT ---
    if not message.text:
        return

    text = message.text.strip()

    # --- REMIND ---
    if text.startswith("/remind"):
        try:
            _, time_str, reminder_text = text.split(" ", 2)
            remind_time = datetime.strptime(time_str, "%Y-%m-%d_%H:%M")

            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO reminders (user_id, text, remind_at) VALUES (?, ?, ?)",
                (
                    user_id,
                    reminder_text,
                    remind_time.strftime("%Y-%m-%d %H:%M:%S")
                )
            )
            conn.commit()
            conn.close()

            await message.answer("Напоминание сохранено.")
        except:
            await message.answer("Формат: /remind 2026-03-05_18:30 Текст")
        return

    save_memory(user_id, "user", text)
    prompt = build_prompt(user_id, text)
    answer = await generate(prompt, MODEL_TEXT)

    save_memory(user_id, "assistant", answer)
    await message.answer(answer[:4000])

# ================== RUN ==================

async def main():
    asyncio.create_task(reminder_loop())

    while True:
        try:
            await dp.start_polling(
                bot,
                timeout=60,
                allowed_updates=dp.resolve_used_update_types()
            )
        except Exception as e:
            logging.error(f"Polling error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())