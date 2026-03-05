from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import CommandStart

from config import BOT_TOKEN
from core.ai_engine import AIEngine
from core.memory import save, load, init_db

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):

    name = message.from_user.first_name

    text = f"""
👋 Привет, {name}!

Я **NEXUM AI** — умный ассистент.

🧠 Что я умею:

• 💬 отвечать на вопросы  
• 🌐 искать информацию  
• 💻 помогать с кодом  
• 🧾 писать тексты  
• 📊 объяснять сложные темы  

⚙️ Дополнительно:

• работа в **группах**
• помощь в **каналах**
• **напоминания**
• **анализ информации**

💡 Просто напиши вопрос или задачу.

Например:

• "Объясни чёрные дыры просто"  
• "Напиши код Python для бота"  
• "Дай идеи для стартапа"
"""

    await message.answer(text)
    await message.answer(text)
    await message.answer(
        "NEXUM V4 активирован."
    )


@dp.message(F.text)
async def chat(message: Message):

    uid = message.from_user.id
    text = message.text

    save(uid, "user", text)

    history = load(uid)

messages = [
{
"role": "system",
"content": """
Ты — NEXUM AI.

Правила:

1. Отвечай понятно.
2. Не пиши поэтические тексты.
3. Не придумывай факты.
4. Если у тебя нет данных — скажи об этом.
5. Не говори что видишь изображение или видео, если анализ не был выполнен.

Формат ответа:

🧠 Ответ

(краткое объяснение)

⚙️ Шаги (если нужны)

1.
2.
3.

💡 Совет (если уместно)
"""
}
]
    messages += history

    messages.append({"role": "user", "content": text})

    answer = await AIEngine.generate(messages)

    save(uid, "assistant", answer)

    await message.answer(answer)


async def start_bot():

    init_db()

    await dp.start_polling(bot)

@dp.message(F.video_note)
async def video_note(message: Message):

    await message.answer(
        "🎥 Я получил видео.\n\n"
        "Сейчас у меня нет модуля анализа видео.\n"
        "Но я могу добавить его позже."
    )
