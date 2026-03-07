"""
╔══════════════════════════════════════════════════════╗
║  NEXUM AI — Telegram Assistant                       ║
║  Powered by Claude · Gemini · Groq                   ║
╚══════════════════════════════════════════════════════╝
"""
import asyncio, logging, os, aiohttp, json, base64, time, re, sys, io
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, BotCommand, BotCommandScopeAllPrivateChats,
    BotCommandScopeAllGroupChats,
)
from aiogram.filters import CommandStart, Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

# ── Logging ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("NEXUM")

# ── Keys ───────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8758082038:AAH4UvCCmYPBnp-Hb9FrIX2OgqhnXj1ur5A")

GEMINI_KEYS = [k for k in [
    os.getenv("G1","AIzaSyDf6nwIOu8zP_px0fol7e9tnMUVExJlVmc"),
    os.getenv("G2","AIzaSyAXyKxHHs_x-10x7AzQvkzvcf3-dUlyFRw"),
    os.getenv("G3","AIzaSyCQYq2EOS7ipG6CUyyLSoFc434lXWEAEzg"),
    os.getenv("G4","AIzaSyDrhpSExtB60gqteY94zVqVt0a8IaAU7yQ"),
    os.getenv("G5","AIzaSyClyTrxkcPcjP9JugkbwL7AqRS_kNZuHJ4"),
    os.getenv("G6","AIzaSyBovsh5hKsZM1V3E551tvTl4tVyD7yvbSo"),
] if k]

GROQ_KEYS = [k for k in [
    os.getenv("GR1","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"),
    os.getenv("GR2","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"),
    os.getenv("GR3","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"),
    os.getenv("GR4","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"),
    os.getenv("GR5","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"),
    os.getenv("GR6","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"),
] if k]

DS_KEYS = [k for k in [
    os.getenv("DS1","sk-09d35dbeb4a5430686f60bbd7411621e"),
    os.getenv("DS2","sk-ad28ca8936ca4fa6a55847b532b9d956"),
    os.getenv("DS3","sk-bae4ca5752974a5eb3edab30d0341439"),
    os.getenv("DS4","sk-1262a6b483e54810a8d02adc6f06fe48"),
    os.getenv("DS5","sk-22dad775c9f8465398a2e924ec4ae916"),
    os.getenv("DS6","sk-bf18eb9208f14617b883a0aa4d05c5b0"),
] if k]

CLAUDE_KEYS = [k for k in [
    os.getenv("CL1","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"),
] if k]

GROK_KEYS = [k for k in [
    os.getenv("GK1","sk-MXZl1hDZGmEN4slJhehF3OFWqarKHYlL4Y1MPo8rCtjlnrNf"),
    os.getenv("GK2","sk-KZ09Pva3G0Lq8hoYIIl6LP0ld5MR7wV05YQgK3RThxvGStwG"),
    os.getenv("GK3","sk-F9gQGwwdPQ3bn69ua29mCAv4B3LmUr0Bdsy4sTvwgxOwoCBY"),
] if k]

# ── Key rotation ────────────────────────────────────────────
_ki: dict = {}
def _next_key(name: str, pool: list) -> str:
    i = _ki.get(name, 0) % len(pool)
    _ki[name] = i + 1
    return pool[i]

# ── System prompt ───────────────────────────────────────────
SYSTEM = (
    "Ты NEXUM — самый умный и продвинутый AI-ассистент.\n"
    "Ты умеешь абсолютно всё: писать код, объяснять любые темы, помогать с творчеством, "
    "анализировать изображения, переводить, решать математику, помогать с бизнесом и многое другое.\n"
    "Отвечай на языке пользователя. Будь дружелюбным, точным и полезным.\n"
    f"Сегодня: {datetime.now().strftime('%d.%m.%Y')}"
)

# ── Conversation memory ─────────────────────────────────────
_history: dict[int, list] = {}
MAX_HISTORY = 20

def _get_history(uid: int) -> list:
    return _history.setdefault(uid, [])

def _add_message(uid: int, role: str, content):
    h = _get_history(uid)
    h.append({"role": role, "content": content})
    if len(h) > MAX_HISTORY:
        _history[uid] = h[-MAX_HISTORY:]

def _clear_history(uid: int):
    _history[uid] = []

# ── Claude API ──────────────────────────────────────────────
async def _claude(messages: list, image_b64: str = None, image_mime: str = "image/jpeg") -> Optional[str]:
    if not CLAUDE_KEYS:
        return None
    key = _next_key("cl", CLAUDE_KEYS)

    claude_msgs = []
    for m in messages:
        if isinstance(m["content"], str):
            claude_msgs.append({"role": m["role"], "content": m["content"]})

    if image_b64 and claude_msgs:
        last = claude_msgs[-1]
        if last["role"] == "user":
            text = last["content"] if isinstance(last["content"], str) else ""
            claude_msgs[-1] = {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": image_mime, "data": image_b64}},
                    {"type": "text", "text": text or "Что на этом изображении?"}
                ]
            }

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-opus-4-6",
                    "max_tokens": 4096,
                    "temperature": 0.8,
                    "system": SYSTEM,
                    "messages": claude_msgs,
                },
                timeout=aiohttp.ClientTimeout(total=60),
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    return data["content"][0]["text"]
                log.warning(f"Claude {r.status}: {(await r.text())[:200]}")
    except Exception as e:
        log.warning(f"Claude error: {e}")
    return None

# ── Gemini API ──────────────────────────────────────────────
async def _gemini(messages: list, image_b64: str = None, image_mime: str = "image/jpeg") -> Optional[str]:
    if not GEMINI_KEYS:
        return None
    key = _next_key("g", GEMINI_KEYS)

    parts_list = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        if isinstance(m["content"], str):
            parts_list.append({"role": role, "parts": [{"text": m["content"]}]})

    if image_b64 and parts_list and parts_list[-1]["role"] == "user":
        parts_list[-1]["parts"].append(
            {"inline_data": {"mime_type": image_mime, "data": image_b64}}
        )

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={key}",
                json={
                    "contents": parts_list,
                    "systemInstruction": {"parts": [{"text": SYSTEM}]},
                    "generationConfig": {"maxOutputTokens": 4096, "temperature": 0.8},
                },
                timeout=aiohttp.ClientTimeout(total=60),
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                log.warning(f"Gemini {r.status}: {(await r.text())[:200]}")
    except Exception as e:
        log.warning(f"Gemini error: {e}")
    return None

# ── Groq API ────────────────────────────────────────────────
async def _groq(messages: list) -> Optional[str]:
    if not GROQ_KEYS:
        return None
    key = _next_key("gr", GROQ_KEYS)

    msgs = [{"role": "system", "content": SYSTEM}]
    for m in messages:
        if isinstance(m["content"], str):
            msgs.append({"role": m["role"], "content": m["content"]})

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": msgs, "max_tokens": 4096, "temperature": 0.8},
                timeout=aiohttp.ClientTimeout(total=45),
            ) as r:
                if r.status == 200:
                    return (await r.json())["choices"][0]["message"]["content"]
                log.warning(f"Groq {r.status}: {(await r.text())[:200]}")
    except Exception as e:
        log.warning(f"Groq error: {e}")
    return None

# ── Main AI dispatcher ──────────────────────────────────────
async def ask_ai(uid: int, text: str, image_b64: str = None, image_mime: str = "image/jpeg") -> str:
    _add_message(uid, "user", text)
    history = _get_history(uid)

    result = None
    if CLAUDE_KEYS:
        result = await _claude(history, image_b64, image_mime)
    if not result and GEMINI_KEYS:
        result = await _gemini(history, image_b64, image_mime)
    if not result and GROQ_KEYS:
        result = await _groq(history)
    if not result:
        result = (
            "⚠️ Нет AI-ключей. Добавь в Railway переменные:\n"
            "• `CL1` — Claude (console.anthropic.com)\n"
            "• `G1` — Gemini (aistudio.google.com) — бесплатно\n"
            "• `GR1` — Groq (console.groq.com) — бесплатно"
        )

    _add_message(uid, "assistant", result)
    return result

# ── Groq Whisper ────────────────────────────────────────────
async def transcribe(audio_bytes: bytes, filename: str = "audio.ogg") -> Optional[str]:
    if not GROQ_KEYS:
        return None
    key = _next_key("gr", GROQ_KEYS)
    try:
        data = aiohttp.FormData()
        data.add_field("file", audio_bytes, filename=filename, content_type="audio/ogg")
        data.add_field("model", "whisper-large-v3")
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                data=data,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                if r.status == 200:
                    return (await r.json()).get("text", "").strip()
    except Exception as e:
        log.warning(f"Whisper: {e}")
    return None

# ── Bot ─────────────────────────────────────────────────────
bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

async def _reply(msg: Message, text: str):
    """Send reply, splitting at 4000 chars, with Markdown fallback."""
    text = text.strip()
    if not text:
        return
    for i, chunk in enumerate([text[j:j+4000] for j in range(0, len(text), 4000)]):
        fn = msg.reply if i == 0 else msg.answer
        try:
            await fn(chunk, parse_mode="Markdown")
        except TelegramBadRequest:
            await fn(chunk)

# ── Commands ────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(msg: Message):
    _clear_history(msg.from_user.id)
    name = msg.from_user.first_name or "друг"
    active = []
    if CLAUDE_KEYS:  active.append("Claude ✅")
    if GEMINI_KEYS:  active.append("Gemini ✅")
    if GROQ_KEYS:    active.append("Groq ✅")
    engines = " · ".join(active) if active else "❌ нет ключей"
    await msg.answer(
        f"👋 Привет, *{name}*!\n\n"
        f"Я *NEXUM AI* — умный ассистент нового поколения.\n\n"
        f"🧠 *AI движки:* {engines}\n\n"
        f"Пиши мне что угодно — отвечу, помогу, объясню!\n\n"
        f"• Текст, вопросы, задачи — просто пиши\n"
        f"• Фото — анализирую изображения\n"
        f"• Голосовые — транскрибирую и отвечаю\n"
        f"• Файлы — читаю и анализирую\n\n"
        f"/clear — новый диалог  |  /help — помощь",
        parse_mode="Markdown"
    )

@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "🤖 *NEXUM AI — справка*\n\n"
        "*Возможности:*\n"
        "— Отвечаю на любые вопросы\n"
        "— Пишу и объясняю код\n"
        "— Анализирую фото и изображения\n"
        "— Распознаю голосовые сообщения\n"
        "— Перевожу тексты\n"
        "— Решаю математику\n"
        "— Помогаю с текстами и творчеством\n\n"
        "*Команды:*\n"
        "/start — начать заново\n"
        "/clear — очистить историю\n"
        "/status — статус AI движков\n"
        "/help — эта справка",
        parse_mode="Markdown"
    )

@dp.message(Command("clear"))
async def cmd_clear(msg: Message):
    _clear_history(msg.from_user.id)
    await msg.answer("🧹 История очищена. Начнём с чистого листа!")

@dp.message(Command("status"))
async def cmd_status(msg: Message):
    lines = ["⚙️ *Статус NEXUM AI*\n"]
    lines.append(f"{'✅' if CLAUDE_KEYS else '❌'} Claude: {len(CLAUDE_KEYS)} ключ(ей)")
    lines.append(f"{'✅' if GEMINI_KEYS else '❌'} Gemini: {len(GEMINI_KEYS)} ключ(ей)")
    lines.append(f"{'✅' if GROQ_KEYS else '❌'} Groq: {len(GROQ_KEYS)} ключ(ей)")
    primary = ("Claude" if CLAUDE_KEYS else "Gemini" if GEMINI_KEYS else "Groq" if GROQ_KEYS else "нет")
    lines.append(f"\n🟢 *Основной AI:* {primary}")
    await msg.answer("\n".join(lines), parse_mode="Markdown")

# ── Text ────────────────────────────────────────────────────
@dp.message(F.text & ~F.text.startswith("/"))
async def handle_text(msg: Message):
    await bot.send_chat_action(msg.chat.id, "typing")
    reply = await ask_ai(msg.from_user.id, msg.text)
    await _reply(msg, reply)

# ── Photo ────────────────────────────────────────────────────
@dp.message(F.photo)
async def handle_photo(msg: Message):
    await bot.send_chat_action(msg.chat.id, "typing")
    caption = msg.caption or "Что на этом изображении? Опиши подробно."
    photo = msg.photo[-1]
    file  = await bot.get_file(photo.file_id)
    url   = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
    img_b64 = None
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                img_b64 = base64.b64encode(await r.read()).decode()
    except Exception as e:
        log.warning(f"Photo download: {e}")
    reply = await ask_ai(msg.from_user.id, caption, img_b64)
    await _reply(msg, reply)

# ── Voice ────────────────────────────────────────────────────
@dp.message(F.voice | F.audio)
async def handle_voice(msg: Message):
    await bot.send_chat_action(msg.chat.id, "typing")
    voice = msg.voice or msg.audio
    file  = await bot.get_file(voice.file_id)
    url   = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
                audio_bytes = await r.read()
        text = await transcribe(audio_bytes)
        if not text:
            await msg.reply("Не могу распознать голосовое. Нужен GR1 (Groq) ключ.")
            return
        await msg.reply(f"🎤 *Распознано:* {text}", parse_mode="Markdown")
        reply = await ask_ai(msg.from_user.id, text)
        await _reply(msg, reply)
    except Exception as e:
        log.error(f"Voice: {e}")
        await msg.reply("Ошибка обработки голосового.")

# ── Document ────────────────────────────────────────────────
@dp.message(F.document)
async def handle_doc(msg: Message):
    await bot.send_chat_action(msg.chat.id, "typing")
    doc = msg.document
    caption = msg.caption or "Проанализируй этот файл."
    text_types = ["text/", "application/json", "application/xml", "application/javascript"]
    is_text = any(doc.mime_type and doc.mime_type.startswith(t) for t in text_types)
    if not is_text or (doc.file_size and doc.file_size > 500_000):
        reply = await ask_ai(msg.from_user.id, f"Файл: {doc.file_name} ({doc.mime_type}). {caption}")
        await _reply(msg, reply)
        return
    file = await bot.get_file(doc.file_id)
    url  = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                content = (await r.text(errors="replace"))[:8000]
        reply = await ask_ai(msg.from_user.id, f"Файл `{doc.file_name}`:\n```\n{content}\n```\n{caption}")
        await _reply(msg, reply)
    except Exception as e:
        log.error(f"Document: {e}")
        await msg.reply("Не удалось прочитать файл.")

# ── Sticker ──────────────────────────────────────────────────
@dp.message(F.sticker)
async def handle_sticker(msg: Message):
    reply = await ask_ai(msg.from_user.id, "Пользователь прислал стикер. Ответь коротко и весело.")
    await _reply(msg, reply)

# ── Startup ──────────────────────────────────────────────────
async def on_startup():
    providers = []
    if CLAUDE_KEYS:  providers.append(f"Claude({len(CLAUDE_KEYS)})")
    if GEMINI_KEYS:  providers.append(f"Gemini({len(GEMINI_KEYS)})")
    if GROQ_KEYS:    providers.append(f"Groq({len(GROQ_KEYS)})")
    log.info("AI: " + (", ".join(providers) if providers else "NO KEYS!"))

    await bot.set_my_commands([
        BotCommand(command="start",  description="Начать / перезапустить"),
        BotCommand(command="clear",  description="Очистить историю"),
        BotCommand(command="status", description="Статус AI"),
        BotCommand(command="help",   description="Помощь"),
    ], scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать"),
        BotCommand(command="clear", description="Очистить историю"),
        BotCommand(command="help",  description="Помощь"),
    ], scope=BotCommandScopeAllGroupChats())
    log.info("NEXUM AI ready.")

async def main():
    if not BOT_TOKEN:
        log.critical("BOT_TOKEN not set!")
        sys.exit(1)
    dp.startup.register(on_startup)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
