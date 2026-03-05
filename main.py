import asyncio
from telegram.bot import dp, bot
from core.memory import init_db


async def main():
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
