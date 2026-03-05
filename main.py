import asyncio
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from telegram.handlers import router

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

dp.include_router(router)


async def main():

    print("NEXUM v3 STARTED")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
