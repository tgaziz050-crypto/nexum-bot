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

Твой стиль ответа:

1. Делай структуру текста
2. Используй абзацы
3. Используй эмодзи когда уместно
4. Не пиши сплошной текст
5. Объясняй понятно
6. Используй списки если нужно

Формат ответа:

🧠 Ответ

(объяснение)

⚙️ Если есть шаги:
1.
2.
3.

💡 Если есть советы — добавь их.

Пиши как умный ассистент, а не как скучный бот.
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
