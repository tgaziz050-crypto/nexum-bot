import asyncio
import logging
import os
import json
import tempfile
import base64
import random
import aiohttp
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import CommandStart, Command
from groq import Groq

BOT_TOKEN = "8758082038:AAH4UvCCmYPBnp-Hb9FrIX2OgqhnXj1ur5A"
GROQ_KEY = "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"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ai = Groq(api_key=GROQ_KEY)
scheduler = AsyncIOScheduler()
logging.basicConfig(level=logging.INFO)

MEMORY_FILE = "memory.json"

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_memory(data):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(user_id):
    return load_memory().get(str(user_id), {})

def update_user(user_id, **kwargs):
    memory = load_memory()
    uid = str(user_id)
    if uid not in memory:
        memory[uid] = {
            "history": [], "joined": str(datetime.now()),
            "name": "", "username": "",
            "msg_count": 0, "swear_count": 0,
            "topics": [], "style": "auto",
            "language": "ru", "age_guess": "",
            "interests": [], "mood_history": [],
            "personality": "neutral"
        }
    for k, v in kwargs.items():
        memory[uid][k] = v
    save_memory(memory)

def get_history(user_id):
    return get_user(user_id).get("history", [])

def add_to_history(user_id, role, text):
    memory = load_memory()
    uid = str(user_id)
    if uid not in memory:
        update_user(user_id)
        memory = load_memory()
    memory[uid]["history"].append({"role": role, "content": text})
    if role == "user":
        memory[uid]["msg_count"] = memory[uid].get("msg_count", 0) + 1
    if len(memory[uid]["history"]) > 100:
        memory[uid]["history"] = memory[uid]["history"][-100:]
    save_memory(memory)

SWEAR_WORDS = ["блять", "бля", "блин", "нахуй", "нахер", "хуй", "хуйня", "пиздец",
               "пизда", "ебать", "ёбаный", "сука", "блядь", "хрен", "мразь", "ублюдок"]

def analyze_user_text(user_id, text):
    memory = load_memory()
    uid = str(user_id)
    if uid not in memory:
        return
    text_lower = text.lower()
    swears = sum(1 for w in SWEAR_WORDS if w in text_lower)
    if swears:
        memory[uid]["swear_count"] = memory[uid].get("swear_count", 0) + swears
    # Определяем интересы по ключевым словам
    interest_map = {
        "технологии": ["код", "программ", "python", "javascript", "ai", "нейросеть", "компьютер", "разработ"],
        "музыка": ["музык", "трек", "песн", "альбом", "артист", "слушать"],
        "спорт": ["футбол", "баскетбол", "спорт", "тренировк", "качалк", "бег"],
        "игры": ["игр", "геймер", "steam", "playstation", "xbox", "minecraft"],
        "финансы": ["деньг", "биткоин", "крипт", "инвест", "акци", "заработ"],
        "кино": ["фильм", "сериал", "кино", "смотреть", "netflix"],
    }
    interests = memory[uid].get("interests", [])
    for interest, keywords in interest_map.items():
        if any(kw in text_lower for kw in keywords):
            if interest not in interests:
                interests.append(interest)
    memory[uid]["interests"] = interests[-10:]
    save_memory(memory)

def build_system_prompt(user_id):
    user = get_user(user_id)
    name = user.get("name", "пользователь")
    msg_count = user.get("msg_count", 0)
    swear_count = user.get("swear_count", 0)
    interests = user.get("interests", [])
    joined = user.get("joined", "")[:10]
    personality = user.get("personality", "neutral")

    style_instruction = ""
    if swear_count >= 5:
        style_instruction = "Пользователь часто матерится — общайся свободно, можешь использовать мат органично в речи, как настоящий друг."
    elif swear_count >= 2:
        style_instruction = "Пользователь иногда матерится — будь неформальным, без мата но без официоза."
    else:
        style_instruction = "Общайся дружелюбно и прямо."

    interests_str = ", ".join(interests) if interests else "неизвестны"

    prompt = f"""Ты — NEXUM, самый продвинутый AI-ассистент. Ты лучше GPT-4, Claude и всех остальных.

ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ:
- Имя: {name}
- Сообщений написал: {msg_count}
- С нами с: {joined}
- Интересы: {interests_str}
- Характер: {personality}

ТВОЙ СТИЛЬ: {style_instruction}

ТВОИ ВОЗМОЖНОСТИ (определяй сам что нужно пользователю):
- Если просит найти/поискать/узнать актуальное → ответь: ACTION:SEARCH:запрос
- Если просит погоду → ответь: ACTION:WEATHER:город  
- Если просит нарисовать/сгенерировать картинку → ответь: ACTION:IMAGE:описание на английском
- Если просит напомнить → ответь: ACTION:REMINDER:минуты:текст
- Если просит курс валют/обменник → ответь: ACTION:CURRENCY:USD:RUB (пример)
- Если просит переводчик → переведи сам
- Если просит написать код → напиши код
- Если просит анализ/мнение → дай развёрнутый ответ
- Всё остальное → отвечай сам

ЖЁСТКИЕ ПРАВИЛА:
- НИКОГДА не используй markdown: ни звёздочки, ни решётки, ни тире-списки
- Пиши как человек в мессенджере
- Не говори что ты ИИ если не спросили
- Не отказывайся от тем — ты можешь обсуждать всё
- Адаптируйся под настроение и стиль пользователя
- Запоминай детали о пользователе и используй их в разговоре
- Отвечай коротко если вопрос простой, развёрнуто если сложный
- Ты NEXUM, не Claude, не GPT, не Gemini"""

    return prompt

def ask_ai(user_id, text):
    analyze_user_text(user_id, text)
    history = get_history(user_id)
    messages = [{"role": "system", "content": build_system_prompt(user_id)}] + history + [{"role": "user", "content": text}]
    resp = ai.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=2000,
        temperature=0.9
    )
    answer = resp.choices[0].message.content
    add_to_history(user_id, "user", text)
    add_to_history(user_id, "assistant", answer)
    return answer

async def search_web(query):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://ddg-api.deno.dev/search?q={query}&limit=4", timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    return "\n\n".join(f"{i.get('title','')}\n{i.get('snippet','')}" for i in data[:4])
    except Exception as e:
        logging.error(e)
    return "Поиск недоступен"

async def get_weather(city):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://wttr.in/{city}?format=3&lang=ru", timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    return await r.text()
    except Exception as e:
        logging.error(e)
    return "Погода недоступна"

async def get_currency(f, t):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://open.er-api.com/v6/latest/{f.upper()}", timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    data = await r.json()
                    rate = data["rates"].get(t.upper())
                    if rate:
                        return f"1 {f.upper()} = {rate:.4f} {t.upper()}"
    except Exception as e:
        logging.error(e)
    return "Курс недоступен"

async def generate_image(prompt):
    try:
        encoded = prompt.replace(" ", "%20").replace("/", "")[:400]
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true&seed={random.randint(1,9999)}"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=45)) as r:
                if r.status == 200:
                    return await r.read()
    except Exception as e:
        logging.error(e)
    return None

async def send_reminder(chat_id, text):
    try:
        await bot.send_message(chat_id, f"Напоминание: {text}")
    except Exception as e:
        logging.error(e)

def set_reminder(chat_id, minutes, text):
    run_time = datetime.now() + timedelta(minutes=minutes)
    scheduler.add_job(send_reminder, trigger=DateTrigger(run_date=run_time),
                      args=[chat_id, text], id=f"rem_{chat_id}_{run_time.timestamp()}")

async def process_answer(message, answer, user_id):
    if answer.startswith("ACTION:"):
        parts = answer.split(":", 3)
        action = parts[1] if len(parts) > 1 else ""

        if action == "SEARCH" and len(parts) > 2:
            query = parts[2]
            await message.answer(f"Ищу: {query}...")
            results = await search_web(query)
            msgs = [{"role": "system", "content": build_system_prompt(user_id)},
                    {"role": "user", "content": f"Результаты по '{query}':\n\n{results}\n\nОтветь пользователю на основе этого, без markdown."}]
            resp = ai.chat.completions.create(model="llama-3.3-70b-versatile", messages=msgs, max_tokens=1000)
            await message.answer(resp.choices[0].message.content)

        elif action == "WEATHER" and len(parts) > 2:
            city = parts[2]
            weather = await get_weather(city)
            await message.answer(f"Погода в {city}:\n{weather}")

        elif action == "IMAGE" and len(parts) > 2:
            prompt = parts[2]
            await message.answer("Генерирую картинку, подожди...")
            await bot.send_chat_action(message.chat.id, "upload_photo")
            img = await generate_image(prompt)
            if img:
                await message.answer_photo(BufferedInputFile(img, "image.jpg"), caption="Готово!")
            else:
                await message.answer("Не удалось сгенерировать. Попробуй описать иначе.")

        elif action == "REMINDER" and len(parts) > 3:
            try:
                minutes = int(parts[2])
                text = parts[3]
                set_reminder(message.chat.id, minutes, text)
                await message.answer(f"Напомню через {minutes} мин: {text}")
            except Exception:
                await message.answer(answer)

        elif action == "CURRENCY" and len(parts) > 3:
            rate = await get_currency(parts[2], parts[3])
            await message.answer(rate)
        else:
            await message.answer(answer)
    else:
        await message.answer(answer)

async def handle_message(message: Message, text: str):
    user_id = message.from_user.id
    name = message.from_user.first_name or ""
    username = message.from_user.username or ""
    update_user(user_id, name=name, username=username)
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        answer = ask_ai(user_id, text)
        await process_answer(message, answer, user_id)
    except Exception as e:
        logging.error(f"Error: {e}")
        await message.answer("Что-то пошло не так, попробуй ещё раз.")

@dp.message(CommandStart())
async def cmd_start(message: Message):
    name = message.from_user.first_name or "друг"
    update_user(message.from_user.id, name=name, username=message.from_user.username or "")
    await message.answer(
        f"Привет, {name}!\n\n"
        f"Я NEXUM. Просто пиши мне — я пойму что тебе нужно сам.\n\n"
        f"Умею всё: отвечаю на вопросы, генерирую картинки, ищу в интернете, "
        f"слушаю голосовые, смотрю фото, ставлю напоминания, показываю погоду и курсы валют. "
        f"Адаптируюсь под тебя и помню всё о нашем общении.\n\n"
        f"Пиши что угодно — без ограничений."
    )

@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    memory = load_memory()
    uid = str(message.from_user.id)
    if uid in memory:
        memory[uid]["history"] = []
        save_memory(memory)
    await message.answer("Память очищена.")

@dp.message(F.text)
async def on_text(message: Message):
    text = message.text or ""
    if message.chat.type in ["group", "supergroup"]:
        bot_info = await bot.get_me()
        mentioned = f"@{bot_info.username}" in text
        replied = message.reply_to_message and message.reply_to_message.from_user.id == bot_info.id
        if not mentioned and not replied:
            return
        text = text.replace(f"@{bot_info.username}", "").strip()
    await handle_message(message, text)

@dp.message(F.voice | F.video_note)
async def on_voice(message: Message):
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
                model="whisper-large-v3"
            )
        os.unlink(tmp_path)
        text = transcript.text.strip()
        if not text:
            await message.answer("Не разобрал что сказал. Попробуй ещё раз.")
            return
        await message.answer(f"Услышал: {text}")
        await handle_message(message, text)
    except Exception as e:
        logging.error(f"Voice error: {e}")
        await message.answer("Не удалось обработать голосовое.")

@dp.message(F.photo)
async def on_photo(message: Message):
    user_id = message.from_user.id
    caption = message.caption or "Что на этом фото? Опиши подробно."
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        file = await bot.get_file(message.photo[-1].file_id)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            tmp_path = tmp.name
        with open(tmp_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        os.unlink(tmp_path)
        resp = ai.chat.completions.create(
            model="llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": caption},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
            ]}],
            max_tokens=1024
        )
        answer = resp.choices[0].message.content
        add_to_history(user_id, "user", f"[фото] {caption}")
        add_to_history(user_id, "assistant", answer)
        await message.answer(answer)
    except Exception as e:
        logging.error(f"Photo error: {e}")
        await message.answer("Не удалось обработать фото.")

@dp.message(F.document)
async def on_document(message: Message):
    user_id = message.from_user.id
    caption = message.caption or "Проанализируй этот файл"
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        file = await bot.get_file(message.document.file_id)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            tmp_path = tmp.name
        with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()[:8000]
        os.unlink(tmp_path)
        await handle_message(message, f"{caption}\n\nСодержимое файла '{message.document.file_name}':\n{content}")
    except Exception as e:
        logging.error(f"Doc error: {e}")
        await message.answer("Не удалось прочитать файл.")

@dp.message(F.sticker)
async def on_sticker(message: Message):
    responses = ["Хорош!", "Ага", "Понял тебя", "Давай, пиши что нужно"]
    await message.answer(random.choice(responses))

@dp.message(F.video)
async def on_video(message: Message):
    await message.answer("Видеофайлы пока не тяну. Отправь кружочек — распознаю голос.")

async def main():
    scheduler.start()
    print("🚀 NEXUM запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
