from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import CommandStart

from config import BOT_TOKEN
from core.memory import save, load
from core.ai_engine import AIEngine

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):

    await message.answer(
        "NEXUM запущен."
    )


@dp.message(F.text)
async def chat(message: Message):

    uid = message.from_user.id
    text = message.text

    save(uid, "user", text)

    history = load(uid)

    messages = [{"role": "system", "content": "Ты NEXUM AI."}]

    messages += history

    messages.append({"role": "user", "content": text})

    answer = await AIEngine.generate(messages)

    save(uid, "assistant", answer)

    await message.answer(answer)
