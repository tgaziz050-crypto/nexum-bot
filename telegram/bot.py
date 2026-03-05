import asyncio, logging, base64, tempfile, os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import CommandStart, Command
from config import BOT_TOKEN, ADMIN_USER_ID
from core.memory import init_db, save_message, get_history, add_memory
from core.ai_engine import generate
from core.tools import Tools
from core.self_improve import create_patch_suggestion

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("telegram_bot")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.reply("Привет — я NEXUM. Скажи, чем помочь?")

@dp.message(Command("post"))
async def cmd_post(message: Message):
    """Команда для постинга в канал: /post <@channel_or_channel_id> | текст"""
    if message.from_user.id != ADMIN_USER_ID:
        await message.reply("Только админ может использовать эту команду.")
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.reply("Использование: /post @channel текст")
        return
    channel = parts[1]
    text = parts[2]
    try:
        await bot.send_message(chat_id=channel, text=text)
        await message.reply("Опубликовано.")
    except Exception as e:
        await message.reply(f"Ошибка при посте: {e}")

@dp.message(F.text)
async def on_text(message: Message):
    uid = message.from_user.id
    text = message.text
    save_message(uid, "user", text)
    history = get_history(uid, limit=20)
    messages = [{"role":"system","content":"Ты NEXUM, отвечай кратко."}]
    for h in history:
        messages.append({"role":h["role"], "content": h["content"]})
    messages.append({"role":"user","content": text})
    # indicators
    await bot.send_chat_action(message.chat.id, "typing")
    resp = await generate(messages)
    save_message(uid, "assistant", resp)
    # if user asked to remember
    if text.lower().startswith("запомни:") or "запомни" in text.lower():
        add_memory(uid, "user_note", text)
    await message.answer(resp)

@dp.message(F.photo)
async def on_photo(message: Message):
    await bot.send_chat_action(message.chat.id, "upload_photo")
    file = await bot.get_file(message.photo[-1].file_id)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        await bot.download_file(file.file_path, tmp.name)
        data = open(tmp.name, "rb").read()
    analysis = await Tools.gen_image_pollinations("Опиши изображение")  # simplified: real flow should upload and call Vision
    await message.answer("Принял фото — описываю...")
    await message.answer("Анализ: (временно) Я получил картинку. Для детального анализа включи Gemini Vision ключи.")
    os.unlink(tmp.name)

@dp.message(F.voice)
async def on_voice(message: Message):
    await bot.send_chat_action(message.chat.id, "typing")
    file = await bot.get_file(message.voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        await bot.download_file(file.file_path, tmp.name)
        path = tmp.name
    # можно транскрибировать через Groq Whisper если ключи есть — здесь placeholder
    await message.answer("Голос получен. Транскрипция доступна при наличии STT ключей.")

# Self improve: user can ask NEXUM "проанализируй core/ai_engine.py и предложи улучшения"
@dp.message(Command("suggest_patch"))
async def cmd_suggest(message: Message):
    if message.from_user.id != ADMIN_USER_ID:
        await message.reply("Только админ.")
        return
    # пример: /suggest_patch core/ai_engine.py
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Использование: /suggest_patch path/to/file.py")
        return
    target = parts[1].strip()
    # read file and ask AI for improvement suggestion
    try:
        with open(target, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        await message.reply(f"Не удалось прочитать файл: {e}")
        return
    prompt = f"Проанализируй код, предложи улучшения и дай готовый вариант файла. Объясни изменения кратко."
    messages = [{"role":"user","content": prompt + "\n\n" + content}]
    await bot.send_chat_action(message.chat.id, "typing")
    suggestion = await generate(messages)
    # save as patch suggestion
    patch_file = await create_patch_suggestion(target, suggestion, "AI suggestion from /suggest_patch")
    await message.reply(f"Предложение сохранено: {patch_file}\nОткрой, проверь и создай PR вручную.")

# Запуск
async def start_polling():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(start_polling())
