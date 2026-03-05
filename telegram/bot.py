from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import CommandStart

from config import BOT_TOKEN
from core.ai_engine import AIEngine
from core.memory import save, load, init_db


bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# --------------------------------------------------
# SYSTEM PROMPT
# --------------------------------------------------

SYSTEM_PROMPT = """
Ты — NEXUM AI.

Правила поведения:

1. Отвечай четко и по делу
2. Не используй поэтический стиль
3. Не пиши художественные вступления
4. Не придумывай факты
5. Если не знаешь — скажи честно

Формат ответа:

🧠 Ответ
(кратко и понятно)

⚙️ Шаги (если нужны)
1.
2.
3.

💡 Совет (если уместно)
"""


# --------------------------------------------------
# START
# --------------------------------------------------

@dp.message(CommandStart())
async def start(message: Message):

    name = message.from_user.first_name

    text = f"""
👋 Привет, {name}!

Я **NEXUM AI** — интеллектуальный ассистент.

🧠 Что я умею:

• 💬 отвечать на вопросы  
• 🌐 искать информацию  
• 💻 помогать с кодом  
• 🧾 писать тексты  
• 📊 объяснять сложные темы  

⚙️ Дополнительно:

• работа в группах  
• помощь каналам  
• анализ информации  

💡 Просто напиши вопрос или задачу.
"""

    await message.answer(text)


# --------------------------------------------------
# VIDEO NOTE
# --------------------------------------------------

@dp.message(F.video_note)
async def video_note(message: Message):

    await message.answer(
        "🎥 Я получил видео.\n\n"
        "Сейчас у меня нет модуля анализа видео."
    )


# --------------------------------------------------
# CHAT
# --------------------------------------------------

@dp.message(F.text)
async def chat(message: Message):

    uid = message.from_user.id
    text = message.text

    if text.startswith("/"):
        return

    save(uid, "user", text)

    history = load(uid)

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    messages += history

    messages.append({
        "role": "user",
        "content": text
    })

    await message.bot.send_chat_action(message.chat.id, "typing")

    answer = await AIEngine.generate(messages)

    save(uid, "assistant", answer)

    await message.answer(answer)


# --------------------------------------------------
# START BOT
# --------------------------------------------------

async def start_bot():

    init_db()

    await dp.start_polling(bot)
