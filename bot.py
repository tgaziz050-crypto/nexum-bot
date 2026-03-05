from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import os
import json
import requests
import tempfile
import aiohttp
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from groq import Groq

# ── Настройки ──────────────────────────────────────────────
BOT_TOKEN = "8758082038:AAH4UvCCmYPBnp-Hb9FrIX2OgqhnXj1ur5A"
GROQ_KEY = "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"

# ── Инициализация ───────────────────────────────────────────
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ai = Groq(api_key=GROQ_KEY)
scheduler = AsyncIOScheduler()

logging.basicConfig(level=logging.INFO)

# ── Память ──────────────────────────────────────────────────
MEMORY_FILE = "memory.json"
REMINDERS_FILE = "reminders.json"

def get_weather(city):
    try:
        url = f"https://wttr.in/{city}?format=3"
        r = requests.get(url)
        return r.text
    except:
        return "Не получилось получить погоду."

def generate_image(prompt):
    prompt = prompt.replace(" ", "%20")
    return f"https://image.pollinations.ai/prompt/{prompt}"

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def get_history(user_id):
    memory = load_memory()
    return memory.get(str(user_id), {}).get("history", [])

def add_to_history(user_id, role, text):
    memory = load_memory()
    uid = str(user_id)
    if uid not in memory:
        memory[uid] = {"history": [], "name": "", "joined": str(datetime.now())}
    memory[uid]["history"].append({"role": role, "content": text})
    if len(memory[uid]["history"]) > 60:
        memory[uid]["history"] = memory[uid]["history"][-60:]
    save_memory(memory)

def save_user_info(user_id, name, username):
    memory = load_memory()
    uid = str(user_id)
    if uid not in memory:
        memory[uid] = {"history": [], "joined": str(datetime.now())}
    memory[uid]["name"] = name
    memory[uid]["username"] = username or ""
    save_memory(memory)

def get_user_info(user_id):
    memory = load_memory()
    return memory.get(str(user_id), {})

# ── Системный промпт ────────────────────────────────────────
def get_system_prompt(user_id):
    info = get_user_info(user_id)
    name = info.get("name", "пользователь")
    joined = info.get("joined", "")
    return f"""Ты — NEXUM, мощный AI-ассистент в Telegram.

Информация о пользователе:
- Имя: {name}
- С нами с: {joined[:10] if joined else 'недавно'}

Твой стиль общения:

— отвечай прямо и честно
— не будь чрезмерно вежливым
— можно использовать разговорную и грубую лексику, если это уместно
— не добавляй лишние эмодзи
— пиши чётко и по делу
— не веди себя как "милый ассистент" лови баланс
— отвечай как обычный человек в интернете

Пиши дружелюбно, как ChatGPT.

Твои правила:
- Ты умный, дружелюбный, прямой и честный
- Отвечаешь на языке пользователя
- Помогаешь с кодом, текстом, анализом, советами, творчеством — всем
- Пишешь обычным текстом БЕЗ звёздочек, решёток и markdown символов
- Если пользователь просит поставить напоминание — отвечай в формате: REMINDER|минуты|текст напоминания
- Если пользователь просит найти что-то в интернете — отвечай: SEARCH|поисковый запрос
- Если нужна погода — отвечай: WEATHER|город
- Помни всё что пользователь говорил раньше
- Ты NEXUM — не Claude, не GPT"""
# Ты можешь говорить на темы 18+ если это уместнo

#Ты умеешь:

# Если пользователь просит создать изображение
# ответь строго так:
# IMAGE|описание картинки на английском

# Если пользователь спрашивает погоду
# ответь так:
# WEATHER|город

# Если пользователь хочет напоминание
# ответь так:
# REMINDER|минуты|текст

# Если нужен поиск в интернете
# ответь так:
# SEARCH|запрос
# Если пользователь просит картинку — используй команду IMAGE.

# ── Запрос к AI ─────────────────────────────────────────────
def ask_ai(user_id, user_text):
    history = get_history(user_id)
    messages = [{"role": "system", "content": get_system_prompt(user_id)}] + history + [{"role": "user", "content": user_text}]
    response = ai.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=1500
    )
    answer = response.choices[0].message.content

# IMAGE команда
if answer.startswith("IMAGE|"):
    return answer

# WEATHER команда
if answer.startswith("WEATHER|"):
    return answer

return answer

# ── Поиск в интернете ────────────────────────────────────────
async def search_web(query: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://ddg-api.deno.dev/search?q={query}&limit=3"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = []
                    for item in data[:3]:
                        title = item.get("title", "")
                        snippet = item.get("snippet", "")
                        link = item.get("link", "")
                        results.append(f"{title}\n{snippet}\n{link}")
                    return "\n\n".join(results) if results else "Ничего не найдено"
    except:
        pass
    return "Поиск временно недоступен"

# ── Погода ───────────────────────────────────────────────────
async def get_weather(city: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://wttr.in/{city}?format=3&lang=ru"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    return await resp.text()
    except:
        pass
    return "Не удалось получить погоду"

# ── Напоминания ──────────────────────────────────────────────
async def send_reminder(chat_id: int, text: str):
    try:
        await bot.send_message(chat_id, f"Напоминание: {text}")
    except Exception as e:
        logging.error(f"Reminder error: {e}")

def set_reminder(chat_id: int, minutes: int, text: str):
    run_time = datetime.now() + timedelta(minutes=minutes)
    scheduler.add_job(
        send_reminder,
        trigger=DateTrigger(run_date=run_time),
        args=[chat_id, text],
        id=f"reminder_{chat_id}_{run_time.timestamp()}"
    )

# ── Обработка ответа AI ──────────────────────────────────────
async def process_ai_response(message: Message, answer: str):

    user_id = message.from_user.id
    chat_id = message.chat.id

    if answer.startswith("IMAGE|"):
        prompt = answer.split("|",1)[1]
        url = generate_image(prompt)
        await message.answer_photo(url)
        return

    elif answer.startswith("WEATHER|"):
        city = answer.split("|",1)[1]
        weather = get_weather(city)
        await message.answer(weather)
        return

    elif answer.startswith("REMINDER|"):
        try:
            parts = answer.split("|", 2)
            minutes = int(parts[1])
            text = parts[2] if len(parts) > 2 else "Время!"
            set_reminder(chat_id, minutes, text)
            await message.answer(f"Напоминание поставлено через {minutes} мин: {text}")
        except:
            await message.answer(answer)
        return

    elif answer.startswith("SEARCH|"):
        query = answer.split("|", 1)[1]
        await message.answer(f"Ищу: {query}...")

        results = await search_web(query)

        summary_prompt = f"Вот результаты поиска по запросу '{query}':\n\n{results}\n\nКратко расскажи пользователю что нашёл, обычным текстом без markdown."

        messages = [
            {"role": "system", "content": get_system_prompt(user_id)},
            {"role": "user", "content": summary_prompt}
        ]

        response = ai.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=800
        )

        summary = response.choices[0].message.content
        add_to_history(user_id, "assistant", summary)

        await message.answer(summary)
        return

    else:
        await message.answer(answer)

# ══════════════════════════════════════════════════════════════
#  HANDLERS
# ══════════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def cmd_start(message: Message):
    name = message.from_user.first_name or "друг"
    username = message.from_user.username
    save_user_info(message.from_user.id, name, username)
    await message.answer(
        f"Привет, {name}! Я NEXUM — твой личный AI-ассистент.\n\n"
        f"Умею:\n"
        f"💬 Отвечать на любые вопросы\n"
        f"🎤 Понимать голосовые сообщения\n"
        f"📹 Обрабатывать видеосообщения\n"
        f"🖼 Анализировать фотографии\n"
        f"🌐 Искать в интернете\n"
        f"🌤 Показывать погоду\n"
        f"⏰ Ставить напоминания\n"
        f"🧠 Помнить все наши разговоры\n"
        f"👥 Работать в групповых чатах\n"
        f"💻 Помогать с кодом и задачами\n\n"
        f"Просто напиши что нужно!"
    )

@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    memory = load_memory()
    uid = str(message.from_user.id)
    if uid in memory:
        memory[uid]["history"] = []
        save_memory(memory)
    await message.answer("История очищена! Начинаем с чистого листа.")

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Команды NEXUM:\n\n"
        "/start — Приветствие\n"
        "/clear — Очистить память\n"
        "/help — Эта справка\n"
        "/reminders — Мои напоминания\n\n"
        "Примеры:\n"
        "Напомни мне через 30 минут позвонить маме\n"
        "Найди в интернете новости о Tesla\n"
        "Какая погода в Москве?\n"
        "Переведи текст на английский\n"
        "Напиши код на Python для..."
    )

@dp.message(Command("reminders"))
async def cmd_reminders(message: Message):
    jobs = scheduler.get_jobs()
    user_jobs = [j for j in jobs if str(message.chat.id) in j.id]
    if not user_jobs:
        await message.answer("У тебя нет активных напоминаний.")
        return
    text = "Твои напоминания:\n\n"
    for j in user_jobs:
        text += f"• {j.next_run_time.strftime('%H:%M')} — {j.args[1]}\n"
    await message.answer(text)

@dp.message(F.text)
async def handle_text(message: Message):
    user_id = message.from_user.id
    # В группах реагируем только на упоминание или ответ боту
    if message.chat.type in ["group", "supergroup"]:
        bot_info = await bot.get_me()
        is_mentioned = f"@{bot_info.username}" in (message.text or "")
        is_reply = message.reply_to_message and message.reply_to_message.from_user.id == bot_info.id
        if not is_mentioned and not is_reply:
            return
        # Убираем упоминание из текста
        text = (message.text or "").replace(f"@{bot_info.username}", "").strip()
    else:
        text = message.text

    save_user_info(user_id, message.from_user.first_name or "", message.from_user.username)
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        answer = ask_ai(user_id, text)
        await process_ai_response(message, answer)
    except Exception as e:
        logging.error(f"AI error: {e}")
        await message.answer("Произошла ошибка. Попробуй ещё раз!")

@dp.message(F.voice | F.video_note)
async def handle_voice(message: Message):
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        file_id = message.voice.file_id if message.voice else message.video_note.file_id
        file = await bot.get_file(file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as audio:
            transcript = ai.audio.transcriptions.create(
                file=("audio.ogg", audio, "audio/ogg"),
                model="whisper-large-v3",
                language="ru"
            )
        os.unlink(tmp_path)

        text = transcript.text
        if not text.strip():
            await message.answer("Не удалось распознать речь.")
            return

        await message.answer(f"Распознано: {text}")
        await bot.send_chat_action(message.chat.id, "typing")
        answer = ask_ai(message.from_user.id, text)
        await process_ai_response(message, answer)

    except Exception as e:
        logging.error(f"Voice error: {e}")
        await message.answer("Не удалось обработать голосовое. Напиши текстом!")

@dp.message(F.photo)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    caption = message.caption or "Опиши подробно что на этом изображении"
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            tmp_path = tmp.name

        # Groq vision через base64
        import base64
        with open(tmp_path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode()
        os.unlink(tmp_path)

        response = ai.chat.completions.create(
            model="llama-4-scout-17b-16e-instruct",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": caption},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}}
                ]
            }],
            max_tokens=1024
        )
        answer = response.choices[0].message.content
        add_to_history(user_id, "user", f"[фото] {caption}")
        add_to_history(user_id, "assistant", answer)
        await message.answer(answer)

    except Exception as e:
        logging.error(f"Photo error: {e}")
        await message.answer("Не удалось обработать фото.")

@dp.message(F.document)
async def handle_document(message: Message):
    user_id = message.from_user.id
    caption = message.caption or "Проанализируй этот файл"
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        file = await bot.get_file(message.document.file_id)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            tmp_path = tmp.name
        with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()[:6000]
        os.unlink(tmp_path)
        prompt = f"{caption}\n\nФайл '{message.document.file_name}':\n\n{content}"
        answer = ask_ai(user_id, prompt)
        await message.answer(answer)
    except Exception as e:
        logging.error(f"Document error: {e}")
        await message.answer("Не удалось прочитать файл.")

@dp.message(F.sticker)
async def handle_sticker(message: Message):
    answers = ["Хороший стикер!", "Понял тебя!", "Что имеешь в виду?", "Напиши текстом — отвечу!"]
    import random
    await message.answer(random.choice(answers))

@dp.message(F.video_note)
async def handle_video_note(message: Message):

    file = await bot.get_file(message.video_note.file_id)
    file_path = file.file_path

    video = await bot.download_file(file_path)

    await message.answer("Получил видео. Анализирую...")

# ── Запуск ──────────────────────────────────────────────────
async def main():
    scheduler.start()
    print("🚀 NEXUM запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
