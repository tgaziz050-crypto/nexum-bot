from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart
from core.ai_router import ai_generate

router = Router()


@router.message(CommandStart())
async def start(message: Message):

    await message.answer(
        "👁 NEXUM online.\n\n"
        "Я слушаю..."
    )


@router.message()
async def chat(message: Message):

    text = message.text

    messages = [
        {"role": "user", "content": text}
    ]

    reply = await ai_generate(messages)

    await message.answer(reply)
