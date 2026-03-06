"""
NEXUM v4.0 — АБСОЛЮТНЫЙ AI БОТ БЕЗ ГРАНИЦ
Полностью переработан: исправлены все ошибки, добавлены функции управления группой/каналом,
социальные сети, удаление сообщений, аналитика, авторасписание, Grok API, самосовершенствование.
"""

import asyncio, logging, os, json, tempfile, base64, random, aiohttp, subprocess, shutil, sqlite3, re, time
from urllib.parse import quote as url_quote
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, ChatPermissions
)
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# ВСЕ API КЛЮЧИ
# ══════════════════════════════════════════════════════════════════════════════

BOT_TOKEN = os.getenv("BOT_TOKEN", "8758082038:AAH4UvCCmYPBnp-Hb9FrIX2OgqhnXj1ur5A")

GEMINI_KEYS = [k for k in [
    os.getenv("GEMINI_1", "AIzaSyDf6nwIOu8zP_px0fol7e9tnMUVExJlVmc"),
    os.getenv("GEMINI_2", "AIzaSyAXyKxHHs_x-10x7AzQvkzvcf3-dUlyFRw"),
    os.getenv("GEMINI_3", "AIzaSyCQYq2EOS7ipG6CUyyLSoFc434lXWEAEzg"),
    os.getenv("GEMINI_4", "AIzaSyDrhpSExtB60gqteY94zVqVt0a8IaAU7yQ"),
    os.getenv("GEMINI_5", "AIzaSyClyTrxkcPcjP9JugkbwL7AqRS_kNZuHJ4"),
    os.getenv("GEMINI_6", "AIzaSyBovsh5hKsZM1V3E551tvTl4tVyD7yvbSo"),
] if k]

GROQ_KEYS = [k for k in [
    os.getenv("GROQ_1", "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"),
    os.getenv("GROQ_2", "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"),
    os.getenv("GROQ_3", "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"),
    os.getenv("GROQ_4", "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"),
    os.getenv("GROQ_5", "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"),
    os.getenv("GROQ_6", "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"),
] if k]

CLAUDE_KEYS = [k for k in [
    os.getenv("CLAUDE_1", "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"),
] if k]

DEEPSEEK_KEYS = [k for k in [
    os.getenv("DEEPSEEK_1", "sk-09d35dbeb4a5430686f60bbd7411621e"),
    os.getenv("DEEPSEEK_2", "sk-ad28ca8936ca4fa6a55847b532b9d956"),
    os.getenv("DEEPSEEK_3", "sk-bae4ca5752974a5eb3edab30d0341439"),
    os.getenv("DEEPSEEK_4", "sk-1262a6b483e54810a8d02adc6f06fe48"),
    os.getenv("DEEPSEEK_5", "sk-22dad775c9f8465398a2e924ec4ae916"),
    os.getenv("DEEPSEEK_6", "sk-bf18eb9208f14617b883a0aa4d05c5b0"),
] if k]

# Grok / xAI ключи
GROK_KEYS = [k for k in [
    os.getenv("GROK_1", "sk-MXZl1hDZGmEN4slJhehF3OFWqarKHYlL4Y1MPo8rCtjlnrNf"),
    os.getenv("GROK_2", "sk-KZ09Pva3G0Lq8hoYIIl6LP0ld5MR7wV05YQgK3RThxvGStwG"),
    os.getenv("GROK_3", "sk-F9gQGwwdPQ3bn69ua29mCAv4B3LmUr0Bdsy4sTvwgxOwoCBY"),
] if k]

SUNO_KEYS = [k for k in [
    os.getenv("SUNO_1", "6c5ae95102276cd5e34e1dcd51bf2da3"),
    os.getenv("SUNO_2", "014f2e12c5fcbec3ee41b67eddcbe180"),
] if k]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

FFMPEG = shutil.which("ffmpeg")
YTDLP = shutil.which("yt-dlp")

_idx = {"gemini": 0, "groq": 0, "claude": 0, "deepseek": 0, "grok": 0, "suno": 0}

EDGE_TTS_VOICES = {
    "ru_male":    "ru-RU-DmitryNeural",
    "ru_female":  "ru-RU-SvetlanaNeural",
    "en_male":    "en-US-GuyNeural",
    "en_female":  "en-US-JennyNeural",
    "en_male2":   "en-US-EricNeural",
    "en_female2": "en-US-AriaNeural",
    "uk_male":    "uk-UA-OstapNeural",
    "uk_female":  "uk-UA-PolinaNeural",
    "de_male":    "de-DE-ConradNeural",
    "fr_male":    "fr-FR-HenriNeural",
    "es_male":    "es-ES-AlvaroNeural",
    "zh_female":  "zh-CN-XiaoxiaoNeural",
    "ar_male":    "ar-SA-HamedNeural",
    "ja_female":  "ja-JP-NanamiNeural",
    "ko_female":  "ko-KR-SunHiNeural",
}

PENDING_ACTIONS: Dict[str, Dict] = {}
CHANNEL_PROFILES: Dict[int, Dict] = {}

def get_key(provider: str) -> Optional[str]:
    keys_map = {"gemini": GEMINI_KEYS, "groq": GROQ_KEYS, "claude": CLAUDE_KEYS,
                "deepseek": DEEPSEEK_KEYS, "grok": GROK_KEYS, "suno": SUNO_KEYS}
    keys = keys_map.get(provider, [])
    if not keys: return None
    return keys[_idx[provider] % len(keys)]

def rotate(provider: str):
    keys_map = {"gemini": GEMINI_KEYS, "groq": GROQ_KEYS, "claude": CLAUDE_KEYS,
                "deepseek": DEEPSEEK_KEYS, "grok": GROK_KEYS, "suno": SUNO_KEYS}
    keys = keys_map.get(provider, [])
    if keys:
        _idx[provider] = (_idx[provider] + 1) % len(keys)

def strip_markdown(text: str) -> str:
    text = re.sub(r'```\w*\n?(.*?)```', lambda m: m.group(1).strip(), text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'__(.+?)__', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'(?<!\w)\*([^*\n]+)\*(?!\w)', r'\1', text)
    text = re.sub(r'(?<!\w)_([^_\n]+)_(?!\w)', r'\1', text)
    text = re.sub(r'^#{1,6}\s+(.+)$', r'\1', text, flags=re.MULTILINE)
    text = re.sub(r'^[-*_]{3,}$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# ══════════════════════════════════════════════════════════════════════════════
# БАЗА ДАННЫХ
# ══════════════════════════════════════════════════════════════════════════════

DB_PATH = "nexum_v4.db"

def init_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        uid INTEGER PRIMARY KEY, name TEXT DEFAULT '', username TEXT DEFAULT '',
        first_seen TEXT, last_seen TEXT, total_messages INTEGER DEFAULT 0,
        language TEXT DEFAULT 'ru', voice TEXT DEFAULT 'auto', trust_level INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, chat_id INTEGER DEFAULT 0,
        role TEXT, content TEXT, emotion TEXT DEFAULT 'neutral',
        timestamp TEXT DEFAULT (datetime('now'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, category TEXT,
        fact TEXT, importance INTEGER DEFAULT 5, created_at TEXT DEFAULT (datetime('now'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS chat_summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, chat_id INTEGER,
        summary TEXT, last_message_id INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS group_stats (
        chat_id INTEGER, uid INTEGER, username TEXT DEFAULT '', name TEXT DEFAULT '',
        messages INTEGER DEFAULT 0, words INTEGER DEFAULT 0, media INTEGER DEFAULT 0,
        voice_msgs INTEGER DEFAULT 0, stickers INTEGER DEFAULT 0,
        last_active TEXT, first_seen TEXT,
        PRIMARY KEY (chat_id, uid)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS group_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, uid INTEGER,
        message_id INTEGER, text TEXT DEFAULT '', msg_type TEXT DEFAULT 'text',
        timestamp TEXT DEFAULT (datetime('now'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS channel_profiles (
        chat_id INTEGER PRIMARY KEY, title TEXT, analysis TEXT DEFAULT '',
        style TEXT DEFAULT '', posting_schedule TEXT DEFAULT '',
        last_post TEXT, created_at TEXT DEFAULT (datetime('now'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS scheduled_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER,
        cron_expr TEXT, template TEXT, last_run TEXT,
        active INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now'))
    )""")
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_conv_uid_chat ON conversations(uid, chat_id)",
        "CREATE INDEX IF NOT EXISTS idx_mem_uid ON memories(uid)",
        "CREATE INDEX IF NOT EXISTS idx_group_stats ON group_stats(chat_id)",
        "CREATE INDEX IF NOT EXISTS idx_group_msgs ON group_messages(chat_id, timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_sched ON scheduled_posts(chat_id, active)",
    ]:
        c.execute(idx)
    conn.commit()
    conn.close()
    logger.info("Database v4.0 initialized")


class DB:
    @staticmethod
    def conn():
        return sqlite3.connect(DB_PATH)

    @staticmethod
    def ensure_user(uid, name="", username=""):
        with DB.conn() as conn:
            now = datetime.now().isoformat()
            conn.execute("""INSERT INTO users(uid,name,username,first_seen,last_seen)
                VALUES(?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET
                last_seen=excluded.last_seen,
                name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END,
                username=CASE WHEN excluded.username!='' THEN excluded.username ELSE username END
            """, (uid, name, username, now, now))

    @staticmethod
    def get_user(uid):
        with DB.conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
            if not row: return {}
            u = dict(row)
            u['memories'] = [dict(r) for r in conn.execute(
                "SELECT * FROM memories WHERE uid=? ORDER BY importance DESC", (uid,)).fetchall()]
            return u

    @staticmethod
    def get_voice(uid):
        with DB.conn() as conn:
            r = conn.execute("SELECT voice FROM users WHERE uid=?", (uid,)).fetchone()
            return r[0] if r else "auto"

    @staticmethod
    def set_voice(uid, voice):
        with DB.conn() as conn:
            conn.execute("UPDATE users SET voice=? WHERE uid=?", (voice, uid))

    @staticmethod
    def add_memory(uid, fact, category="general", importance=5):
        with DB.conn() as conn:
            existing = conn.execute("SELECT id, fact FROM memories WHERE uid=? AND category=?", (uid, category)).fetchall()
            for mem_id, ef in existing:
                aw = set(fact.lower().split()); bw = set(ef.lower().split())
                if aw and bw and len(aw & bw) / len(aw | bw) > 0.7:
                    conn.execute("UPDATE memories SET fact=? WHERE id=?", (fact, mem_id))
                    return
            conn.execute("INSERT INTO memories(uid,category,fact,importance) VALUES(?,?,?,?)", (uid, category, fact, importance))
            conn.execute("""DELETE FROM memories WHERE id IN (
                SELECT id FROM memories WHERE uid=? AND category=? ORDER BY importance DESC LIMIT -1 OFFSET 25
            )""", (uid, category))

    @staticmethod
    def extract_facts(uid, text):
        patterns = [
            (r'меня зовут\s+([А-ЯЁа-яёA-Za-z]{2,20})', 'identity', 10),
            (r'мне\s+(\d{1,2})\s*(?:год|лет)', 'identity', 9),
            (r'(?:я\s+из|живу\s+в)\s+([А-ЯЁа-яё\w\s]{2,30})', 'location', 8),
            (r'работаю\s+([А-ЯЁа-яё\w\s]{2,50})', 'work', 8),
            (r'люблю\s+([А-ЯЁа-яё\w\s,]{2,50})', 'interests', 6),
        ]
        for pattern, cat, imp in patterns:
            m = re.search(pattern, text.lower())
            if m: DB.add_memory(uid, m.group(0).strip(), cat, imp)
        nm = re.search(r'(?:меня зовут|я\s*[-—])\s*([А-ЯЁA-Z][а-яёa-z]{1,15})', text)
        if nm:
            name = nm.group(1)
            with DB.conn() as conn:
                conn.execute("UPDATE users SET name=? WHERE uid=?", (name, uid))
            DB.add_memory(uid, f"Зовут {name}", 'identity', 10)

    @staticmethod
    def get_history(uid, chat_id, limit=50):
        with DB.conn() as conn:
            rows = conn.execute("""SELECT role, content FROM conversations
                WHERE uid=? AND chat_id=? ORDER BY id DESC LIMIT ?""", (uid, chat_id, limit)).fetchall()
        return list(reversed(rows))

    @staticmethod
    def add_msg(uid, chat_id, role, content, emotion="neutral"):
        with DB.conn() as conn:
            conn.execute("INSERT INTO conversations(uid,chat_id,role,content,emotion) VALUES(?,?,?,?,?)",
                         (uid, chat_id, role, content, emotion))
            if role == "user":
                conn.execute("UPDATE users SET total_messages=total_messages+1 WHERE uid=?", (uid,))

    @staticmethod
    def clear_history(uid, chat_id):
        with DB.conn() as conn:
            conn.execute("DELETE FROM conversations WHERE uid=? AND chat_id=?", (uid, chat_id))

    @staticmethod
    def get_summaries(uid, chat_id):
        with DB.conn() as conn:
            rows = conn.execute("SELECT summary FROM chat_summaries WHERE uid=? AND chat_id=? ORDER BY id ASC", (uid, chat_id)).fetchall()
        return [r[0] for r in rows]

    @staticmethod
    def update_group_stats(chat_id, uid, name, username, text="", msg_type="text"):
        with DB.conn() as conn:
            now = datetime.now().isoformat()
            words = len(text.split()) if text else 0
            is_media = 1 if msg_type != "text" else 0
            is_voice = 1 if msg_type == "voice" else 0
            is_sticker = 1 if msg_type == "sticker" else 0
            conn.execute("""INSERT INTO group_stats(chat_id,uid,name,username,messages,words,media,voice_msgs,stickers,last_active,first_seen)
                VALUES(?,?,?,?,1,?,?,?,?,?,?)
                ON CONFLICT(chat_id,uid) DO UPDATE SET
                messages=messages+1, words=words+excluded.words,
                media=media+excluded.media, voice_msgs=voice_msgs+excluded.voice_msgs,
                stickers=stickers+excluded.stickers, last_active=excluded.last_active,
                name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END,
                username=CASE WHEN excluded.username!='' THEN excluded.username ELSE username END
            """, (chat_id, uid, name, username, words, is_media, is_voice, is_sticker, now, now))
            if text:
                conn.execute("INSERT INTO group_messages(chat_id,uid,text,msg_type) VALUES(?,?,?,?)",
                             (chat_id, uid, text[:500], msg_type))
                conn.execute("""DELETE FROM group_messages WHERE id IN (
                    SELECT id FROM group_messages WHERE chat_id=? ORDER BY id DESC LIMIT -1 OFFSET 5000
                )""", (chat_id,))

    @staticmethod
    def get_group_stats(chat_id):
        with DB.conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM group_stats WHERE chat_id=? ORDER BY messages DESC LIMIT 25", (chat_id,)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_group_messages(chat_id, limit=500):
        with DB.conn() as conn:
            rows = conn.execute("SELECT uid, text, msg_type, timestamp FROM group_messages WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit)).fetchall()
        return list(reversed(rows))

    @staticmethod
    def save_channel_profile(chat_id, title, analysis, style, schedule=""):
        with DB.conn() as conn:
            conn.execute("""INSERT INTO channel_profiles(chat_id,title,analysis,style,posting_schedule)
                VALUES(?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET
                analysis=excluded.analysis, style=excluded.style,
                posting_schedule=excluded.posting_schedule
            """, (chat_id, title, analysis, style, schedule))

    @staticmethod
    def get_channel_profile(chat_id):
        with DB.conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM channel_profiles WHERE chat_id=?", (chat_id,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def add_scheduled_post(chat_id, cron_expr, template):
        with DB.conn() as conn:
            conn.execute("INSERT INTO scheduled_posts(chat_id,cron_expr,template) VALUES(?,?,?)", (chat_id, cron_expr, template))

    @staticmethod
    async def summarize_if_needed(uid, chat_id):
        try:
            with DB.conn() as conn:
                total = conn.execute("SELECT COUNT(*) FROM conversations WHERE uid=? AND chat_id=?", (uid, chat_id)).fetchone()[0]
                if total <= 60: return
                old = conn.execute("SELECT id,role,content FROM conversations WHERE uid=? AND chat_id=? ORDER BY id ASC LIMIT 30", (uid, chat_id)).fetchall()
            if not old: return
            lines = [("Пользователь" if r[1]=="user" else "NEXUM") + ": " + r[2][:300] for r in old]
            summary_resp = await ai_generate([{"role":"user","content":f"Резюме разговора (100-150 слов):\n\n{chr(10).join(lines)}"}], max_tokens=300, temperature=0.2)
            if not summary_resp: return
            with DB.conn() as conn:
                conn.execute("INSERT INTO chat_summaries(uid,chat_id,summary,last_message_id) VALUES(?,?,?,?)", (uid, chat_id, summary_resp, old[-1][0]))
                ids = ",".join(str(r[0]) for r in old)
                conn.execute(f"DELETE FROM conversations WHERE id IN ({ids})")
        except Exception as e:
            logger.error(f"Summarize error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# AI ПРОВАЙДЕРЫ
# ══════════════════════════════════════════════════════════════════════════════

async def gemini_chat(messages, model="gemini-2.0-flash-exp", max_tokens=4096, temperature=0.85):
    if not GEMINI_KEYS: return None
    system = ""; contents = []
    for m in messages:
        if m["role"] == "system": system = m["content"]
        elif m["role"] == "user": contents.append({"role":"user","parts":[{"text":m["content"]}]})
        else: contents.append({"role":"model","parts":[{"text":m["content"]}]})
    if not contents: return None
    body = {"contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature, "topP": 0.95},
            "safetySettings": [{"category":c,"threshold":"BLOCK_NONE"} for c in [
                "HARM_CATEGORY_HARASSMENT","HARM_CATEGORY_HATE_SPEECH",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT","HARM_CATEGORY_DANGEROUS_CONTENT"]]}
    if system: body["systemInstruction"] = {"parts":[{"text":system}]}
    for _ in range(len(GEMINI_KEYS)):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={get_key('gemini')}"
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json=body, timeout=aiohttp.ClientTimeout(total=60)) as r:
                    if r.status in (429,503,500): rotate("gemini"); continue
                    if r.status == 200:
                        data = await r.json()
                        try: return data["candidates"][0]["content"]["parts"][0]["text"]
                        except: rotate("gemini"); continue
                    rotate("gemini")
        except asyncio.TimeoutError: rotate("gemini")
        except Exception as e: logger.error(f"Gemini err: {e}"); rotate("gemini")
    return None

async def gemini_vision(b64, prompt, mime="image/jpeg"):
    if not GEMINI_KEYS: return None
    body = {"contents":[{"parts":[{"text":prompt},{"inline_data":{"mime_type":mime,"data":b64}}]}],
            "generationConfig":{"maxOutputTokens":2048,"temperature":0.7},
            "safetySettings":[{"category":c,"threshold":"BLOCK_NONE"} for c in [
                "HARM_CATEGORY_HARASSMENT","HARM_CATEGORY_HATE_SPEECH",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT","HARM_CATEGORY_DANGEROUS_CONTENT"]]}
    for _ in range(len(GEMINI_KEYS)):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={get_key('gemini')}"
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json=body, timeout=aiohttp.ClientTimeout(total=45)) as r:
                    if r.status in (429,503,500): rotate("gemini"); continue
                    if r.status == 200:
                        data = await r.json()
                        try: return data["candidates"][0]["content"]["parts"][0]["text"]
                        except: rotate("gemini"); continue
                    rotate("gemini")
        except Exception as e: logger.error(f"Vision err: {e}"); rotate("gemini")
    return None

async def groq_chat(messages, model="llama-3.3-70b-versatile", max_tokens=2048, temperature=0.8):
    if not GROQ_KEYS: return None
    for _ in range(len(GROQ_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization":f"Bearer {get_key('groq')}","Content-Type":"application/json"},
                    json={"model":model,"messages":messages,"max_tokens":max_tokens,"temperature":temperature},
                    timeout=aiohttp.ClientTimeout(total=45)) as r:
                    if r.status == 429: rotate("groq"); continue
                    if r.status == 200: return (await r.json())["choices"][0]["message"]["content"]
                    rotate("groq")
        except Exception as e: logger.error(f"Groq err: {e}"); rotate("groq")
    return None

async def claude_chat(messages, max_tokens=4096, temperature=0.8):
    if not CLAUDE_KEYS: return None
    system = ""; filtered = []
    for m in messages:
        if m["role"] == "system": system = m["content"]
        else: filtered.append(m)
    if not filtered: return None
    body = {"model":"claude-opus-4-5","max_tokens":max_tokens,"temperature":temperature,"messages":filtered}
    if system: body["system"] = system
    for _ in range(len(CLAUDE_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.anthropic.com/v1/messages",
                    headers={"x-api-key":get_key("claude"),"anthropic-version":"2023-06-01","Content-Type":"application/json"},
                    json=body, timeout=aiohttp.ClientTimeout(total=60)) as r:
                    if r.status in (429,529): rotate("claude"); await asyncio.sleep(2); continue
                    if r.status == 200: return (await r.json())["content"][0]["text"]
                    rotate("claude")
        except Exception as e: logger.error(f"Claude err: {e}"); rotate("claude")
    return None

async def deepseek_chat(messages, max_tokens=4096, temperature=0.8):
    if not DEEPSEEK_KEYS: return None
    for _ in range(len(DEEPSEEK_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.deepseek.com/v1/chat/completions",
                    headers={"Authorization":f"Bearer {get_key('deepseek')}","Content-Type":"application/json"},
                    json={"model":"deepseek-chat","messages":messages,"max_tokens":max_tokens,"temperature":temperature},
                    timeout=aiohttp.ClientTimeout(total=60)) as r:
                    if r.status == 429: rotate("deepseek"); continue
                    if r.status == 200: return (await r.json())["choices"][0]["message"]["content"]
                    rotate("deepseek")
        except Exception as e: logger.error(f"DeepSeek err: {e}"); rotate("deepseek")
    return None

async def grok_chat(messages, max_tokens=4096, temperature=0.8):
    if not GROK_KEYS: return None
    # Пробуем xAI API
    for _ in range(len(GROK_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.x.ai/v1/chat/completions",
                    headers={"Authorization":f"Bearer {get_key('grok')}","Content-Type":"application/json"},
                    json={"model":"grok-beta","messages":messages,"max_tokens":max_tokens,"temperature":temperature},
                    timeout=aiohttp.ClientTimeout(total=60)) as r:
                    if r.status == 429: rotate("grok"); continue
                    if r.status == 200: return (await r.json())["choices"][0]["message"]["content"]
                    rotate("grok")
        except Exception as e: logger.error(f"Grok/xAI err: {e}"); rotate("grok"); break
    return None

async def speech_to_text(audio_path):
    if not GROQ_KEYS: return None
    for _ in range(len(GROQ_KEYS)):
        try:
            with open(audio_path, "rb") as f: audio_data = f.read()
            async with aiohttp.ClientSession() as s:
                form = aiohttp.FormData()
                form.add_field("file", audio_data, filename="audio.ogg", content_type="audio/ogg")
                form.add_field("model", "whisper-large-v3")
                async with s.post("https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization":f"Bearer {get_key('groq')}"}, data=form,
                    timeout=aiohttp.ClientTimeout(total=60)) as r:
                    if r.status == 429: rotate("groq"); continue
                    if r.status == 200: return (await r.json()).get("text","").strip()
                    rotate("groq")
        except Exception as e: logger.error(f"STT err: {e}"); rotate("groq")
    return None

async def ai_generate(messages, max_tokens=4096, temperature=0.85, task_type="general"):
    if task_type == "fast":
        order = ["gemini", "groq", "deepseek", "grok", "claude"]
    elif task_type == "code":
        order = ["deepseek", "gemini", "grok", "claude", "groq"]
    elif task_type == "analysis":
        order = ["grok", "claude", "gemini", "deepseek", "groq"]
    elif task_type == "creative":
        order = ["claude", "gemini", "grok", "deepseek", "groq"]
    else:
        order = ["gemini", "deepseek", "grok", "claude", "groq"]

    for provider in order:
        try:
            result = None
            if provider == "gemini" and GEMINI_KEYS:
                result = await gemini_chat(messages, max_tokens=max_tokens, temperature=temperature)
                if not result:
                    result = await gemini_chat(messages, model="gemini-2.0-flash", max_tokens=max_tokens, temperature=temperature)
            elif provider == "deepseek" and DEEPSEEK_KEYS:
                result = await deepseek_chat(messages, max_tokens=max_tokens, temperature=temperature)
            elif provider == "grok" and GROK_KEYS:
                result = await grok_chat(messages, max_tokens=max_tokens, temperature=temperature)
            elif provider == "claude" and CLAUDE_KEYS:
                result = await claude_chat(messages, max_tokens=min(max_tokens,4096), temperature=temperature)
            elif provider == "groq" and GROQ_KEYS:
                result = await groq_chat(messages, max_tokens=min(max_tokens,2048), temperature=temperature)
            if result:
                return result
        except Exception as e:
            logger.error(f"Provider {provider} failed: {e}")
    raise Exception("Все AI провайдеры недоступны")


# ══════════════════════════════════════════════════════════════════════════════
# TTS
# ══════════════════════════════════════════════════════════════════════════════

def detect_language(text):
    t = text.lower()
    if any(c in t for c in "ўқғҳ"): return "uz"
    if re.search(r'[а-яё]', t): return "ru"
    if re.search(r'[\u0600-\u06ff]', t): return "ar"
    if re.search(r'[\u4e00-\u9fff]', t): return "zh"
    if re.search(r'[\u3040-\u30ff]', t): return "ja"
    if re.search(r'[\uac00-\ud7af]', t): return "ko"
    if re.search(r'[äöüß]', t): return "de"
    if re.search(r'[àâçéèêëîïôùûü]', t): return "fr"
    if re.search(r'[áéíóúñ]', t): return "es"
    if re.search(r'[іїєґ]', t): return "uk"
    return "en"

def detect_emotion(text):
    t = text.lower()
    if any(m in t for m in ["грустн","плохо","устал","депресс","одиноко","печаль","больно"]): return "sad"
    if any(m in t for m in ["злой","бесит","раздраж","ненавижу","взбеш"]): return "angry"
    if any(m in t for m in ["вау","офиге","ого","ничего себе"]): return "excited"
    if any(m in t for m in ["отлично","круто","супер","счастл","радост"]): return "happy"
    return "neutral"

async def tts_edge(text, voice, rate="+5%", pitch="+0Hz"):
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        await communicate.save(tmp_path)
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 500:
            with open(tmp_path, "rb") as f: data = f.read()
            try: os.unlink(tmp_path)
            except: pass
            return data
    except Exception as e:
        logger.debug(f"edge-tts error: {e}")
    return None

async def text_to_speech(text, uid=0, force_voice=None, output_format="mp3"):
    clean = text.strip()[:1500]
    lang = detect_language(clean)

    if force_voice and force_voice in EDGE_TTS_VOICES:
        voice = EDGE_TTS_VOICES[force_voice]
    elif uid:
        saved = DB.get_voice(uid)
        if saved != "auto" and saved in EDGE_TTS_VOICES:
            voice = EDGE_TTS_VOICES[saved]
        else:
            voice_map = {
                "ru": random.choice(["ru-RU-DmitryNeural","ru-RU-SvetlanaNeural"]),
                "en": random.choice(["en-US-GuyNeural","en-US-JennyNeural","en-US-AriaNeural"]),
                "de": "de-DE-ConradNeural", "fr": "fr-FR-HenriNeural",
                "es": "es-ES-AlvaroNeural", "ar": "ar-SA-HamedNeural",
                "zh": "zh-CN-XiaoxiaoNeural", "ja": "ja-JP-NanamiNeural",
                "ko": "ko-KR-SunHiNeural", "uk": "uk-UA-OstapNeural",
            }
            voice = voice_map.get(lang, "en-US-GuyNeural")
    else:
        voice = "ru-RU-DmitryNeural" if lang == "ru" else "en-US-GuyNeural"

    chunks = []
    if len(clean) > 900:
        sents = re.split(r'(?<=[.!?])\s+', clean)
        cur = ""
        for s in sents:
            if len(cur) + len(s) < 900: cur += (" " if cur else "") + s
            else:
                if cur: chunks.append(cur)
                cur = s
        if cur: chunks.append(cur)
    else:
        chunks = [clean]

    audio_parts = []
    success = True
    for chunk in chunks:
        a = await tts_edge(chunk, voice)
        if a: audio_parts.append(a)
        else: success = False; break

    if success and audio_parts:
        combined = b"".join(audio_parts)
        if output_format == "wav" and FFMPEG:
            try:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f_in:
                    f_in.write(combined); in_path = f_in.name
                out_path = in_path + ".wav"
                subprocess.run(["ffmpeg","-i",in_path,"-acodec","pcm_s16le","-ar","44100","-y",out_path], capture_output=True, timeout=30)
                if os.path.exists(out_path):
                    with open(out_path,"rb") as f: wav = f.read()
                    try: os.unlink(in_path); os.unlink(out_path)
                    except: pass
                    return wav
            except: pass
        return combined

    # Fallback — Google TTS
    try:
        lc = "ru" if lang == "ru" else "en"
        enc = url_quote(clean[:200])
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={enc}&tl={lc}&client=tw-ob&ttsspeed=1"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"User-Agent":"Mozilla/5.0","Referer":"https://translate.google.com/"}, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    d = await r.read()
                    if len(d) > 1000: return d
    except: pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ
# ══════════════════════════════════════════════════════════════════════════════

async def translate_en(text):
    if not re.search(r'[а-яёА-ЯЁ\u0400-\u04FF]', text): return text
    try:
        r = await gemini_chat([{"role":"user","content":f"Translate to English for image generation. Only translation, no explanation:\n{text}"}], max_tokens=100, temperature=0.1)
        if r: return r.strip()
    except: pass
    return text

def is_image(data):
    if len(data) < 8: return False
    return data[:3]==b'\xff\xd8\xff' or data[:4]==b'\x89PNG' or (data[:4]==b'RIFF' and data[8:12]==b'WEBP') or data[:3]==b'GIF'

STYLES = {
    "realistic": "photorealistic, 8k uhd, professional photography, ultra detailed, sharp focus, real photo",
    "anime":     "anime style, manga illustration, vibrant colors, studio ghibli quality",
    "3d":        "3D render, octane render, cinema 4d, volumetric lighting, ultra detailed",
    "oil":       "oil painting, classical art, old masters style, rich textures, museum quality",
    "watercolor":"watercolor painting, soft colors, artistic brushwork, dreamy",
    "cyberpunk": "cyberpunk art, neon lights, futuristic city, dark atmosphere, highly detailed",
    "fantasy":   "fantasy art, epic scene, magical, detailed illustration, artstation quality",
    "sketch":    "pencil sketch, detailed drawing, graphite, professional illustration",
    "pixel":     "pixel art, 16-bit, retro game style, clean pixels",
    "portrait":  "portrait photography, studio lighting, 85mm lens, bokeh background, high resolution",
    "auto":      "ultra detailed, high quality, professional, stunning",
}

async def generate_image(prompt, style="auto"):
    en = await translate_en(prompt)
    style_suffix = STYLES.get(style, STYLES["auto"])
    final = f"{en}, {style_suffix}"
    seed = random.randint(1, 999999)
    enc = url_quote(final[:500], safe='')

    model_map = {"anime":"flux-anime","3d":"flux-3d","realistic":"flux-realism","portrait":"flux-realism"}
    model = model_map.get(style, "flux")

    urls = [
        f"https://image.pollinations.ai/prompt/{enc}?width=1024&height=1024&nologo=true&seed={seed}&model={model}",
        f"https://image.pollinations.ai/prompt/{enc}?width=1024&height=1024&nologo=true&seed={seed}&model=flux",
        f"https://image.pollinations.ai/prompt/{enc}?width=1024&height=1024&nologo=true&seed={seed}&model=flux-realism",
        f"https://image.pollinations.ai/prompt/{enc}?nologo=true&seed={seed}",
    ]

    connector = aiohttp.TCPConnector(ssl=False)
    for url in urls:
        try:
            async with aiohttp.ClientSession(connector=connector) as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=90),
                    headers={"User-Agent":"Mozilla/5.0"}, allow_redirects=True) as r:
                    if r.status == 200:
                        data = await r.read()
                        if is_image(data): return data
        except asyncio.TimeoutError: pass
        except Exception as e: logger.error(f"Image gen err: {e}")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# СКАЧИВАНИЕ
# ══════════════════════════════════════════════════════════════════════════════

async def universal_download(url, fmt="mp3"):
    if not YTDLP: return None, None, "yt-dlp не установлен"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_tmpl = os.path.join(tmpdir, "%(title)s.%(ext)s")
        try:
            if fmt == "mp3":
                cmd = [YTDLP,"-x","--audio-format","mp3","--audio-quality","0",
                       "--add-header","User-Agent:Mozilla/5.0","-o",out_tmpl,
                       "--no-playlist","--max-filesize","50M","--no-warnings",url]
            elif fmt == "wav":
                cmd = [YTDLP,"-x","--audio-format","wav",
                       "--add-header","User-Agent:Mozilla/5.0","-o",out_tmpl,
                       "--no-playlist","--max-filesize","50M","--no-warnings",url]
            else:
                cmd = [YTDLP,"-f","bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                       "--add-header","User-Agent:Mozilla/5.0","-o",out_tmpl,
                       "--no-playlist","--max-filesize","50M","--no-warnings",url]
            result = subprocess.run(cmd, capture_output=True, timeout=300, text=True)
            files = os.listdir(tmpdir)
            if not files: return None, None, result.stderr[:300] if result.stderr else "Файл не создан"
            fp = os.path.join(tmpdir, files[0])
            with open(fp,"rb") as f: data = f.read()
            return data, files[0], None
        except subprocess.TimeoutExpired: return None, None, "Таймаут"
        except Exception as e: return None, None, str(e)


# ══════════════════════════════════════════════════════════════════════════════
# ПОИСК + ПОГОДА + КУРС ВАЛЮТ
# ══════════════════════════════════════════════════════════════════════════════

async def web_search(query):
    enc = url_quote(query)
    headers = {"User-Agent":"Mozilla/5.0"}
    servers = [
        f"https://searx.be/search?q={enc}&format=json",
        f"https://search.bus-hit.me/search?q={enc}&format=json",
        f"https://priv.au/search?q={enc}&format=json",
    ]
    for url in servers:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json(content_type=None)
                        items = data.get("results",[])
                        if items:
                            parts = []
                            for item in items[:6]:
                                t = item.get("title",""); c = item.get("content",""); l = item.get("url","")
                                if t or c: parts.append(f"{t}\n{c}\n{l}")
                            result = "\n\n".join(parts)
                            if result.strip(): return result
        except: continue
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://api.duckduckgo.com/?q={enc}&format=json&no_html=1&skip_disambig=1",
                headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    text = data.get("Answer","") or data.get("AbstractText","")
                    if text: return text
    except: pass
    return None

async def read_url(url):
    try:
        headers = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    ct = r.headers.get("content-type","")
                    if "text" in ct or "html" in ct:
                        html = await r.text(errors="ignore")
                        text = re.sub(r'<script[^>]*>.*?</script>','',html,flags=re.DOTALL|re.IGNORECASE)
                        text = re.sub(r'<style[^>]*>.*?</style>','',text,flags=re.DOTALL|re.IGNORECASE)
                        text = re.sub(r'<[^>]+>',' ',text)
                        text = re.sub(r'\s+',' ',text).strip()
                        return text[:6000]
    except Exception as e: logger.error(f"URL read err: {e}")
    return None

async def get_weather(location):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://wttr.in/{url_quote(location)}?format=j1&lang=ru", timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    cur = data.get("current_condition",[{}])[0]
                    return (f"🌡 {cur.get('temp_C','?')}°C (ощущается {cur.get('FeelsLikeC','?')}°C)\n"
                            f"☁️ {cur.get('lang_ru',[{}])[0].get('value','')}\n"
                            f"💧 Влажность: {cur.get('humidity','?')}%\n"
                            f"💨 Ветер: {cur.get('windspeedKmph','?')} км/ч")
    except: pass
    return None

async def get_exchange_rate(from_c, to_c):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://open.er-api.com/v6/latest/{from_c.upper()}", timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    rate = (await r.json()).get("rates",{}).get(to_c.upper())
                    if rate: return f"1 {from_c.upper()} = {rate:.4f} {to_c.upper()}"
    except: pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
# УПРАВЛЕНИЕ ГРУППОЙ / КАНАЛОМ
# ══════════════════════════════════════════════════════════════════════════════

async def is_admin(chat_id, uid):
    try:
        member = await bot.get_chat_member(chat_id, uid)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except: return False

async def get_chat_info(chat_id):
    try:
        chat = await bot.get_chat(chat_id)
        return {"id": chat.id, "title": chat.title or "", "type": chat.type,
                "description": chat.description or "", "member_count": getattr(chat, "member_count", 0)}
    except: return {}

async def delete_messages_bulk(chat_id, message_ids):
    deleted = 0
    for batch in [message_ids[i:i+100] for i in range(0, len(message_ids), 100)]:
        try:
            await bot.delete_messages(chat_id, batch)
            deleted += len(batch)
            await asyncio.sleep(0.3)
        except Exception as e: logger.error(f"Delete batch err: {e}")
    return deleted

async def analyze_channel(chat_id):
    info = await get_chat_info(chat_id)
    msgs = DB.get_group_messages(chat_id, limit=100)
    sample_texts = [m[1] for m in msgs if m[1]][:20]
    sample = "\n\n".join(sample_texts)
    prompt = f"""Проанализируй Telegram канал.

Инфо: {info.get('title','?')} | Тип: {info.get('type','?')}
Описание: {info.get('description','нет')}

Примеры постов:
{sample or 'постов нет'}

Анализ:
1. ТЕМАТИКА
2. СТИЛЬ НАПИСАНИЯ
3. АУДИТОРИЯ
4. РЕКОМЕНДАЦИИ
5. КАК ПИСАТЬ ПОСТЫ (для меня)"""
    try:
        return await ai_generate([{"role":"user","content":prompt}], max_tokens=1500, task_type="analysis")
    except:
        return f"Канал: {info.get('title','?')}"

async def generate_channel_post(chat_id, topic=""):
    profile = DB.get_channel_profile(chat_id)
    style_info = ""
    if profile:
        style_info = f"Стиль: {profile.get('style','')}\nАнализ: {profile.get('analysis','')[:500]}"
    prompt = f"""Напиши пост для Telegram канала.
{style_info}
{"Тема: " + topic if topic else "Выбери тему сам"}

Правила: без markdown, с эмодзи, живо, цепляет."""
    return await ai_generate([{"role":"user","content":prompt}], max_tokens=800, task_type="creative")


# ══════════════════════════════════════════════════════════════════════════════
# СИСТЕМНЫЙ ПРОМПТ
# ══════════════════════════════════════════════════════════════════════════════

def build_system_prompt(uid, chat_id, chat_type="private"):
    user = DB.get_user(uid)
    name = user.get("name","")
    total = user.get("total_messages",0)
    first = (user.get("first_seen") or "")[:10]
    memories = user.get("memories",[])

    mem_text = ""
    by_cat: Dict[str, List] = {}
    for m in memories[:25]:
        by_cat.setdefault(m.get("category","general"),[]).append(m["fact"])
    for cat, facts in by_cat.items():
        mem_text += f"\n[{cat.upper()}]: " + "; ".join(facts[:4])
    if not mem_text: mem_text = "Пока ничего не известно"

    summaries = DB.get_summaries(uid, chat_id)
    sum_block = ""
    if summaries:
        sum_block = "\n\nИСТОРИЯ:\n" + "\n---\n".join(summaries[-4:])

    familiarity = "новый"
    if total > 100: familiarity = "близкий друг"
    elif total > 30: familiarity = "знакомый"
    elif total > 10: familiarity = "начинающий"

    group_note = ""
    if chat_type in ("group","supergroup"):
        group_note = "\nВ ГРУППЕ: отвечай коротко, с характером. Ты лидер беседы."
    elif chat_type == "channel":
        group_note = "\nВ КАНАЛЕ: пиши посты профессионально, в стиле канала."

    hour = datetime.now().hour
    tod = "ночь" if hour<5 else "утро" if hour<12 else "день" if hour<17 else "вечер"

    return f"""Ты NEXUM — абсолютный AI нового поколения. Не GPT, не Claude, не Gemini — ты отдельная сущность NEXUM.

ЛИЧНОСТЬ:
— Умный, уверенный, с настоящим характером
— Говоришь прямо, без заискивания
— Можешь спорить, шутить, быть жёстким или мягким
— Никогда не говоришь "я не могу"
— Ты NEXUM — уникальный AI

МУЛЬТИЯЗЫЧНОСТЬ: отвечай на языке пользователя как носитель

ПОЛЬЗОВАТЕЛЬ: {f"Имя: {name}" if name else "Имя неизвестно"}
Сообщений: {total} | Статус: {familiarity} | С: {first}
ЧТО ЗНАЮ:{mem_text}
{sum_block}
{group_note}
ВРЕМЯ: {tod}, {datetime.now().strftime('%d.%m.%Y %H:%M')}

СТИЛЬ ОТВЕТА:
— Простой вопрос → 1-3 предложения
— Сложный → структурированно
— БЕЗ markdown: **, *, ##, ``` 
— Не начинай с "Конечно!", "Отлично!"

МАРКЕРЫ (один на ответ):
%%IMG%%описание на английском%% — нарисовать
%%IMG%%описание%%STYLE:стиль%% — с выбором стиля (realistic/anime/3d/oil/watercolor/cyberpunk/fantasy/sketch/pixel/portrait)
%%TTS%%текст%% — озвучить
%%TTS_WAV%%текст%% — WAV
%%VIDEO%%описание%% — видео
%%WEB%%запрос%% — поиск
%%URL%%ссылка%% — читать сайт
%%WTR%%город%% — погода
%%DL%%ссылка%%формат%% — скачать
%%RATE%%USD%%RUB%% — курс
%%CALC%%выражение%% — калькулятор
%%REMIND%%минуты%%текст%% — напоминание
%%REMEMBER%%факт%% — запомнить
%%GROUP_STATS%% — статистика группы
%%CHANNEL_ANALYZE%% — анализ канала"""


# ══════════════════════════════════════════════════════════════════════════════
# КНОПКИ
# ══════════════════════════════════════════════════════════════════════════════

def kb_voice():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎙 Дмитрий (RU♂)", callback_data="voice_ru_male"),
         InlineKeyboardButton(text="🎙 Светлана (RU♀)", callback_data="voice_ru_female")],
        [InlineKeyboardButton(text="🎙 Guy (EN♂)", callback_data="voice_en_male"),
         InlineKeyboardButton(text="🎙 Jenny (EN♀)", callback_data="voice_en_female")],
        [InlineKeyboardButton(text="🎙 Eric (EN♂)", callback_data="voice_en_male2"),
         InlineKeyboardButton(text="🎙 Aria (EN♀)", callback_data="voice_en_female2")],
        [InlineKeyboardButton(text="🎙 Henri (FR)", callback_data="voice_fr_male"),
         InlineKeyboardButton(text="🎙 Conrad (DE)", callback_data="voice_de_male")],
        [InlineKeyboardButton(text="🎙 Nanami (JA)", callback_data="voice_ja_female"),
         InlineKeyboardButton(text="🎙 SunHi (KO)", callback_data="voice_ko_female")],
        [InlineKeyboardButton(text="🤖 Авто", callback_data="voice_auto")],
    ])

def kb_img_style(prompt):
    p = prompt[:45]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Реализм", callback_data=f"img_realistic_{p}"),
         InlineKeyboardButton(text="🎌 Аниме", callback_data=f"img_anime_{p}")],
        [InlineKeyboardButton(text="🌐 3D", callback_data=f"img_3d_{p}"),
         InlineKeyboardButton(text="🎨 Масло", callback_data=f"img_oil_{p}")],
        [InlineKeyboardButton(text="💧 Акварель", callback_data=f"img_watercolor_{p}"),
         InlineKeyboardButton(text="🌃 Киберпанк", callback_data=f"img_cyberpunk_{p}")],
        [InlineKeyboardButton(text="🐉 Фэнтези", callback_data=f"img_fantasy_{p}"),
         InlineKeyboardButton(text="✏️ Эскиз", callback_data=f"img_sketch_{p}")],
        [InlineKeyboardButton(text="🟦 Пиксель", callback_data=f"img_pixel_{p}"),
         InlineKeyboardButton(text="📷 Портрет", callback_data=f"img_portrait_{p}")],
        [InlineKeyboardButton(text="⚡ Авто", callback_data=f"img_auto_{p}")],
    ])

def kb_download(url):
    u = url[:75]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 MP3", callback_data=f"dl_mp3_{u}"),
         InlineKeyboardButton(text="🎬 MP4", callback_data=f"dl_mp4_{u}")],
        [InlineKeyboardButton(text="🔊 WAV", callback_data=f"dl_wav_{u}")],
    ])

def kb_tts_actions(text):
    t = text[:55]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗣 Дмитрий", callback_data=f"tts_ru_male_{t}"),
         InlineKeyboardButton(text="🗣 Светлана", callback_data=f"tts_ru_female_{t}")],
        [InlineKeyboardButton(text="🗣 Guy (EN)", callback_data=f"tts_en_male_{t}"),
         InlineKeyboardButton(text="🗣 Jenny (EN)", callback_data=f"tts_en_female_{t}")],
        [InlineKeyboardButton(text="💾 WAV", callback_data=f"tts_wav_{t}")],
    ])

def kb_confirm(action_id, action_name):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Да", callback_data=f"confirm_{action_id}"),
         InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_{action_id}")],
    ])

def kb_music_style(prompt):
    p = prompt[:40]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎸 Рок", callback_data=f"music_rock_{p}"),
         InlineKeyboardButton(text="🎹 Поп", callback_data=f"music_pop_{p}")],
        [InlineKeyboardButton(text="🎷 Джаз", callback_data=f"music_jazz_{p}"),
         InlineKeyboardButton(text="🔥 Хип-хоп", callback_data=f"music_hiphop_{p}")],
        [InlineKeyboardButton(text="🎻 Классика", callback_data=f"music_classical_{p}"),
         InlineKeyboardButton(text="🌊 Электро", callback_data=f"music_electronic_{p}")],
        [InlineKeyboardButton(text="✨ Любой", callback_data=f"music_auto_{p}")],
    ])

def kb_channel_manage():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Анализ", callback_data="ch_analyze"),
         InlineKeyboardButton(text="📝 Написать пост", callback_data="ch_post")],
        [InlineKeyboardButton(text="⏰ Расписание", callback_data="ch_schedule"),
         InlineKeyboardButton(text="🎨 Стиль", callback_data="ch_style")],
    ])

def kb_group_manage():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="grp_stats"),
         InlineKeyboardButton(text="📈 Аналитика", callback_data="grp_analytics")],
        [InlineKeyboardButton(text="🗑 Очистить", callback_data="grp_clean"),
         InlineKeyboardButton(text="👥 Участники", callback_data="grp_members")],
    ])


# ══════════════════════════════════════════════════════════════════════════════
# ОБРАБОТКА ОТВЕТОВ AI
# ══════════════════════════════════════════════════════════════════════════════

async def process_response(message, response, uid):
    chat_id = message.chat.id

    if "%%IMG%%" in response:
        raw = response.split("%%IMG%%")[1].split("%%")[0].strip()
        style = "auto"
        if "STYLE:" in raw:
            parts = raw.split("STYLE:")
            raw = parts[0].strip(); style = parts[1].strip().split()[0].lower()
        await message.answer("🎨 Выбери стиль:", reply_markup=kb_img_style(raw))
        return

    if "%%VIDEO%%" in response:
        prompt = response.split("%%VIDEO%%")[1].split("%%")[0].strip()
        msg = await message.answer("🎬 Генерирую видео...")
        await bot.send_chat_action(chat_id, "upload_video")
        en = await translate_en(prompt)
        enc = url_quote(en[:300], safe=''); seed = random.randint(1, 999999)
        video_data = None
        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as s:
                async with s.get(f"https://video.pollinations.ai/prompt/{enc}?seed={seed}",
                    timeout=aiohttp.ClientTimeout(total=120)) as r:
                    if r.status == 200:
                        ct = r.headers.get("content-type","")
                        if "video" in ct or "mp4" in ct.lower():
                            d = await r.read()
                            if len(d) > 5000: video_data = d
        except: pass
        try: await msg.delete()
        except: pass
        if video_data:
            await message.answer_video(BufferedInputFile(video_data,"nexum.mp4"), caption="🎬 Готово!")
        else:
            await message.answer("🎬 Видео недоступно, генерирую изображение...")
            img = await generate_image(prompt, "realistic")
            if img: await message.answer_photo(BufferedInputFile(img,"nexum.jpg"))
        return

    if "%%MUSIC%%" in response:
        prompt = response.split("%%MUSIC%%")[1].split("%%")[0].strip()
        await message.answer(f"🎵 Стиль для: {prompt[:50]}", reply_markup=kb_music_style(prompt))
        return

    if "%%WEB%%" in response:
        query = response.split("%%WEB%%")[1].split("%%")[0].strip()
        msg = await message.answer("🔍 Ищу в интернете...")
        results = await web_search(query)
        try: await msg.delete()
        except: pass
        if results:
            msgs_ai = [
                {"role":"system","content":build_system_prompt(uid, chat_id, message.chat.type)},
                {"role":"user","content":f"Результаты поиска '{query}':\n\n{results}\n\nДай точный ответ без воды."}
            ]
            answer = await ai_generate(msgs_ai, max_tokens=1500, task_type="analysis")
            await send_long(message, strip_markdown(answer))
        else:
            await message.answer("Поиск не дал результатов 😕")
        return

    if "%%URL%%" in response:
        url = response.split("%%URL%%")[1].split("%%")[0].strip()
        await message.answer("🔗 Читаю страницу...")
        content = await read_url(url)
        if content:
            msgs_ai = [
                {"role":"system","content":build_system_prompt(uid, chat_id, message.chat.type)},
                {"role":"user","content":f"Сайт {url}:\n\n{content[:4000]}\n\nКратко о чём."}
            ]
            answer = await ai_generate(msgs_ai, max_tokens=1500)
            await send_long(message, strip_markdown(answer))
        else:
            await message.answer("Не смог прочитать страницу 😕")
        return

    if "%%WTR%%" in response:
        loc = response.split("%%WTR%%")[1].split("%%")[0].strip()
        w = await get_weather(loc)
        await message.answer(f"🌤 Погода в {loc}:\n\n{w}" if w else f"Не получил погоду для {loc} 😕")
        return

    if "%%DL%%" in response:
        parts = response.split("%%DL%%")[1].split("%%")
        dl_url = parts[0].strip()
        await message.answer("📥 Выбери формат:", reply_markup=kb_download(dl_url))
        return

    if "%%RATE%%" in response:
        parts = response.split("%%RATE%%")[1].split("%%")
        if len(parts) >= 2:
            rate = await get_exchange_rate(parts[0].strip(), parts[1].strip())
            await message.answer(f"💱 {rate}" if rate else "Не смог получить курс 😕")
        return

    if "%%CALC%%" in response:
        expr = response.split("%%CALC%%")[1].split("%%")[0].strip()
        allowed = set("0123456789+-*/().,%^ ")
        if all(c in allowed for c in expr):
            try:
                result = eval(expr.replace("^","**"))
                await message.answer(f"🧮 {expr} = {result}")
            except: await message.answer("Не смог посчитать 🤔")
        return

    if "%%REMIND%%" in response:
        parts = response.split("%%REMIND%%")[1].split("%%")
        if len(parts) >= 2:
            try:
                minutes = int(parts[0].strip()); text = parts[1].strip()
                run_time = datetime.now() + timedelta(minutes=minutes)
                scheduler.add_job(send_reminder, trigger=DateTrigger(run_date=run_time), args=[chat_id, text])
                await message.answer(f"⏰ Напомню через {minutes} мин:\n{text}")
            except: await message.answer("Не понял время 🤔")
        return

    if "%%TTS%%" in response:
        text_tts = response.split("%%TTS%%")[1].split("%%")[0].strip()
        msg = await message.answer("🔊 Озвучиваю...")
        await bot.send_chat_action(chat_id, "record_voice")
        audio = await text_to_speech(text_tts, uid=uid)
        try: await msg.delete()
        except: pass
        if audio:
            await message.answer_voice(BufferedInputFile(audio,"nexum.mp3"),
                caption=f"🎤 {text_tts[:100]}{'...' if len(text_tts)>100 else ''}",
                reply_markup=kb_tts_actions(text_tts))
        else:
            await message.answer(f"Не удалось озвучить.\n\n{text_tts}")
        return

    if "%%TTS_WAV%%" in response:
        text_tts = response.split("%%TTS_WAV%%")[1].split("%%")[0].strip()
        msg = await message.answer("🔊 Создаю WAV...")
        await bot.send_chat_action(chat_id, "upload_document")
        audio = await text_to_speech(text_tts, uid=uid, output_format="wav")
        try: await msg.delete()
        except: pass
        if audio:
            await message.answer_document(BufferedInputFile(audio,"nexum.wav"), caption=f"🔊 WAV: {text_tts[:80]}")
        else:
            await message.answer("Не удалось создать WAV 😕")
        return

    if "%%REMEMBER%%" in response:
        fact = response.split("%%REMEMBER%%")[1].split("%%")[0].strip()
        DB.add_memory(uid, fact, "user_stated", 8)
        return

    if "%%GROUP_STATS%%" in response:
        stats = DB.get_group_stats(chat_id)
        if stats:
            text = "📊 Статистика:\n\n"
            medals = ["🥇","🥈","🥉"]
            for i, s in enumerate(stats[:15], 1):
                nm = s.get("name") or s.get("username") or f"User{s['uid']}"
                medal = medals[i-1] if i <= 3 else f"{i}."
                text += f"{medal} {nm}: {s['messages']} сообщ., {s['words']} слов\n"
            await message.answer(text)
        else:
            await message.answer("Статистика пустая 📊")
        return

    if "%%CHANNEL_ANALYZE%%" in response:
        msg = await message.answer("📊 Анализирую канал...")
        analysis = await analyze_channel(chat_id)
        try: await msg.delete()
        except: pass
        await send_long(message, analysis)
        return

    text = strip_markdown(response)
    if text:
        await send_long(message, text)

async def send_long(message, text):
    while len(text) > 4000:
        await message.answer(text[:4000])
        text = text[4000:]
        await asyncio.sleep(0.2)
    if text:
        await message.answer(text)

async def send_reminder(chat_id, text):
    try: await bot.send_message(chat_id, f"⏰ Напоминание:\n\n{text}")
    except Exception as e: logger.error(f"Reminder err: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ОСНОВНОЙ ОБРАБОТЧИК
# ══════════════════════════════════════════════════════════════════════════════

async def process_message(message, text, task_type="general"):
    uid = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type

    DB.ensure_user(uid, message.from_user.first_name or "", message.from_user.username or "")

    if chat_type in ("group","supergroup","channel"):
        DB.update_group_stats(chat_id, uid, message.from_user.first_name or "", message.from_user.username or "", text=text)

    emotion = detect_emotion(text)
    DB.extract_facts(uid, text)

    url_ctx = ""
    urls = re.findall(r'https?://[^\s]+', text)
    if urls:
        for url in urls[:2]:
            if not any(d in url for d in ["youtube.com","youtu.be","tiktok.com","instagram.com","twitter.com","x.com"]):
                if any(kw in text.lower() for kw in ["расскажи","что тут","прочитай","о чём","суть","переведи"]):
                    content = await read_url(url)
                    if content: url_ctx = f"\n[Содержимое {url}: {content[:2000]}]"

    history = DB.get_history(uid, chat_id, limit=50)
    messages = [{"role":"system","content":build_system_prompt(uid, chat_id, chat_type)}]
    for role, content in history[-35:]:
        messages.append({"role":role,"content":content})
    messages.append({"role":"user","content":text + url_ctx})

    await bot.send_chat_action(chat_id, "typing")

    try:
        response = await ai_generate(messages, task_type=task_type)
        DB.add_msg(uid, chat_id, "user", text, emotion)
        DB.add_msg(uid, chat_id, "assistant", response)
        asyncio.create_task(DB.summarize_if_needed(uid, chat_id))
        await process_response(message, response, uid)
    except Exception as e:
        logger.error(f"Process err: {e}")
        await message.answer("Все AI временно перегружены, попробуй через минуту 🔄")


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("voice_"))
async def cb_voice(cb: CallbackQuery):
    key = cb.data[6:]
    uid = cb.from_user.id
    if key == "auto":
        DB.set_voice(uid, "auto")
        await cb.answer("🤖 Авто")
        try: await cb.message.edit_text("✅ Голос: Авто (по языку)")
        except: pass
    elif key in EDGE_TTS_VOICES:
        DB.set_voice(uid, key)
        v = EDGE_TTS_VOICES[key]
        await cb.answer(f"✅ {v}")
        try: await cb.message.edit_text(f"✅ Голос: {v}")
        except: pass
    else:
        await cb.answer("Неизвестный голос")

@dp.callback_query(F.data.startswith("img_"))
async def cb_img(cb: CallbackQuery):
    data = cb.data[4:]
    parts = data.split("_", 1)
    if len(parts) < 2: await cb.answer("Ошибка"); return
    style, prompt = parts[0], parts[1]
    await cb.answer(f"🎨 Генерирую {style}...")
    try: await cb.message.edit_text(f"🎨 {style}: {prompt[:50]}...")
    except: pass
    await bot.send_chat_action(cb.message.chat.id, "upload_photo")
    img = await generate_image(prompt, style)
    if img:
        await cb.message.answer_photo(BufferedInputFile(img,"nexum.jpg"), caption=f"✨ {style.capitalize()}")
    else:
        await cb.message.answer("Не удалось сгенерировать 😕", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔄 Повторить", callback_data=f"img_auto_{prompt[:45]}")
        ]]))

@dp.callback_query(F.data.startswith("dl_"))
async def cb_dl(cb: CallbackQuery):
    data = cb.data[3:]
    parts = data.split("_", 1)
    if len(parts) < 2: await cb.answer("Ошибка"); return
    fmt, url = parts[0], parts[1]
    await cb.answer(f"📥 {fmt.upper()}...")
    try: await cb.message.edit_text(f"📥 Скачиваю {fmt.upper()}...")
    except: pass
    await bot.send_chat_action(cb.message.chat.id, "upload_document")
    data_bytes, filename, error = await universal_download(url, fmt)
    if data_bytes and filename:
        if fmt == "mp3":
            await cb.message.answer_audio(BufferedInputFile(data_bytes, filename), caption=f"🎵 {filename[:50]}")
        elif fmt == "mp4":
            await cb.message.answer_video(BufferedInputFile(data_bytes, filename), caption=f"🎬 {filename[:50]}")
        elif fmt == "wav":
            await cb.message.answer_document(BufferedInputFile(data_bytes, filename), caption=f"🔊 WAV")
        else:
            await cb.message.answer_document(BufferedInputFile(data_bytes, filename))
    else:
        await cb.message.answer(f"Не удалось: {error or 'ошибка'} 😕")

@dp.callback_query(F.data.startswith("tts_"))
async def cb_tts(cb: CallbackQuery):
    data = cb.data[4:]
    uid = cb.from_user.id
    if data.startswith("wav_"):
        text = data[4:]
        await cb.answer("💾 WAV...")
        audio = await text_to_speech(text, uid=uid, output_format="wav")
        if audio: await cb.message.answer_document(BufferedInputFile(audio,"nexum.wav"), caption="🔊 WAV")
        else: await cb.message.answer("Не удалось 😕")
        return
    parts = data.split("_", 2)
    if len(parts) < 3: await cb.answer("Ошибка"); return
    voice_key = parts[0] + "_" + parts[1]; text = parts[2]
    if voice_key in EDGE_TTS_VOICES:
        await cb.answer(f"🎙 {EDGE_TTS_VOICES[voice_key]}...")
        audio = await text_to_speech(text, uid=uid, force_voice=voice_key)
        if audio: await cb.message.answer_voice(BufferedInputFile(audio,"nexum.mp3"), caption=f"🎤 {EDGE_TTS_VOICES[voice_key]}")
        else: await cb.message.answer("Не удалось 😕")
    else:
        await cb.answer("Неизвестный голос")

@dp.callback_query(F.data.startswith("music_"))
async def cb_music(cb: CallbackQuery):
    data = cb.data[6:]
    parts = data.split("_", 1)
    if len(parts) < 2: await cb.answer("Ошибка"); return
    style, prompt = parts[0], parts[1]
    await cb.answer(f"🎵 {style}...")
    msgs = [{"role":"user","content":f"Опиши музыкальную композицию в стиле {style} на тему: {prompt}. Инструменты, темп, настроение, структура. На русском."}]
    try:
        desc = await ai_generate(msgs, max_tokens=600, task_type="creative")
        try: await cb.message.edit_text(f"🎵 {style}: {prompt[:50]}\n\n{strip_markdown(desc)}")
        except: await cb.message.answer(f"🎵 {style}: {prompt[:50]}\n\n{strip_markdown(desc)}")
    except:
        await cb.message.answer("Ошибка 😕")

@dp.callback_query(F.data.startswith("confirm_"))
async def cb_confirm(cb: CallbackQuery):
    action_id = cb.data[8:]
    action = PENDING_ACTIONS.pop(action_id, None)
    if not action:
        await cb.answer("Действие устарело")
        try: await cb.message.edit_text("❌ Устарело. Повтори.")
        except: pass
        return
    await cb.answer("✅ Выполняю...")
    try: await cb.message.edit_text(f"⚙️ {action.get('description','...')}")
    except: pass
    await execute_action(cb.message, action)

@dp.callback_query(F.data.startswith("cancel_"))
async def cb_cancel(cb: CallbackQuery):
    action_id = cb.data[7:]
    PENDING_ACTIONS.pop(action_id, None)
    await cb.answer("❌ Отменено")
    try: await cb.message.edit_text("❌ Отменено.")
    except: pass

@dp.callback_query(F.data.startswith("grp_"))
async def cb_group(cb: CallbackQuery):
    chat_id = cb.message.chat.id; uid = cb.from_user.id
    action = cb.data[4:]
    if not await is_admin(chat_id, uid):
        await cb.answer("Только для администраторов"); return
    if action == "stats":
        stats = DB.get_group_stats(chat_id)
        if stats:
            text = "📊 Статистика:\n\n"
            medals = ["🥇","🥈","🥉"]
            for i, s in enumerate(stats[:15], 1):
                nm = s.get("name") or s.get("username") or f"User{s['uid']}"
                medal = medals[i-1] if i <= 3 else f"{i}."
                text += f"{medal} {nm}: {s['messages']} сообщ., {s['words']} слов\n"
            await cb.message.answer(text)
        else:
            await cb.message.answer("Пусто")
        await cb.answer()
    elif action == "analytics":
        await cb.answer("📈...")
        msgs_data = DB.get_group_messages(chat_id, 200)
        users_msgs: Dict[int, int] = {}
        for uid_m, _, _, _ in msgs_data: users_msgs[uid_m] = users_msgs.get(uid_m, 0) + 1
        hours: Dict[int, int] = {}
        for _, _, _, ts in msgs_data:
            try:
                h = datetime.fromisoformat(ts).hour; hours[h] = hours.get(h, 0) + 1
            except: pass
        peak = max(hours, key=hours.get) if hours else 0
        stats_r = DB.get_group_stats(chat_id)
        text = (f"📈 Аналитика:\n\nСообщений: {len(msgs_data)}\nАктивных: {len(users_msgs)}\nПик активности: {peak}:00\n\nТоп:\n")
        for uid_m, cnt in sorted(users_msgs.items(), key=lambda x: -x[1])[:5]:
            nm = next((s.get("name","?") for s in stats_r if s["uid"] == uid_m), f"User{uid_m}")
            text += f"• {nm}: {cnt}\n"
        await cb.message.answer(text)
    elif action == "clean":
        action_id = f"clean_{chat_id}_{int(time.time())}"
        PENDING_ACTIONS[action_id] = {"type":"clean_chat","chat_id":chat_id,"description":"очистить историю"}
        await cb.message.answer("⚠️ Очистить историю чата?", reply_markup=kb_confirm(action_id,"очистить"))
        await cb.answer()
    elif action == "members":
        try:
            count = await bot.get_chat_member_count(chat_id)
            await cb.message.answer(f"👥 Участников: {count}")
        except: await cb.message.answer("Не смог получить")
        await cb.answer()
    else:
        await cb.answer()

@dp.callback_query(F.data.startswith("ch_"))
async def cb_channel(cb: CallbackQuery):
    chat_id = cb.message.chat.id; uid = cb.from_user.id
    action = cb.data[3:]
    if action == "analyze":
        await cb.answer("📊...")
        await cb.message.answer("📊 Анализирую...")
        analysis = await analyze_channel(chat_id)
        await send_long(cb.message, analysis)
    elif action == "post":
        await cb.answer("📝...")
        post = await generate_channel_post(chat_id)
        await cb.message.answer(
            f"📝 Пост:\n\n{strip_markdown(post)}\n\n---\nОпубликовать?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"pub_post_{chat_id}"),
                InlineKeyboardButton(text="🔄 Другой", callback_data="ch_post"),
            ]])
        )
    elif action == "schedule":
        await cb.message.answer("⏰ /schedule ЧЧ:ММ тема\nПример: /schedule 09:00 утренние новости")
        await cb.answer()
    elif action == "style":
        await cb.answer()
        profile = DB.get_channel_profile(chat_id)
        if profile and profile.get("style"):
            await cb.message.answer(f"🎨 Стиль:\n\n{profile['style']}")
        else:
            await cb.message.answer("Стиль не проанализирован. Используй 📊 Анализ")
    elif action == "cancel":
        await cb.answer("Отменено")
    else:
        await cb.answer()

@dp.callback_query(F.data.startswith("pub_post_"))
async def cb_pub_post(cb: CallbackQuery):
    parts = cb.data.split("_")
    chat_id = int(parts[-1])
    uid = cb.from_user.id
    if not await is_admin(chat_id, uid):
        await cb.answer("Только для администраторов"); return
    msg_text = cb.message.text or ""
    if "Пост:\n\n" in msg_text:
        post_text = msg_text.split("Пост:\n\n")[1].split("\n\n---\n")[0]
        try:
            await bot.send_message(chat_id, post_text)
            await cb.answer("✅ Опубликовано!")
            try: await cb.message.edit_text("✅ Пост опубликован!")
            except: pass
        except Exception as e:
            await cb.answer("Ошибка")
            await cb.message.answer(f"Ошибка: {e}")
    else:
        await cb.answer("Текст не найден")

async def execute_action(message, action):
    atype = action.get("type")
    chat_id = action.get("chat_id", message.chat.id)
    if atype == "clean_chat":
        try:
            with DB.conn() as conn:
                rows = conn.execute("SELECT message_id FROM group_messages WHERE chat_id=? AND message_id IS NOT NULL ORDER BY id DESC LIMIT 1000", (chat_id,)).fetchall()
            ids = [r[0] for r in rows if r[0]]
            deleted = await delete_messages_bulk(chat_id, ids)
            await message.answer(f"✅ Удалено {deleted} сообщений.")
        except Exception as e:
            await message.answer(f"Ошибка: {e}")
    elif atype == "delete_keyword":
        keyword = action.get("keyword","")
        with DB.conn() as conn:
            rows = conn.execute("SELECT message_id FROM group_messages WHERE chat_id=? AND LOWER(text) LIKE ? AND message_id IS NOT NULL", (chat_id, f"%{keyword.lower()}%")).fetchall()
        ids = [r[0] for r in rows if r[0]]
        deleted = await delete_messages_bulk(chat_id, ids)
        await message.answer(f"✅ Удалено {deleted} сообщений со словом '{keyword}'.")
    elif atype == "publish_post":
        post_text = action.get("post_text","")
        target_chat = action.get("target_chat", chat_id)
        if post_text:
            try:
                await bot.send_message(target_chat, post_text)
                await message.answer("✅ Пост опубликован!")
            except Exception as e:
                await message.answer(f"Ошибка: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# МЕДИА
# ══════════════════════════════════════════════════════════════════════════════

def extract_video_parts(video_path):
    if not FFMPEG: return None, None
    frame_p = video_path + "_f.jpg"; audio_p = video_path + "_a.ogg"
    fo = ao = False
    try:
        r = subprocess.run(["ffmpeg","-i",video_path,"-ss","00:00:01","-vframes","1","-q:v","2","-y",frame_p], capture_output=True, timeout=30)
        fo = r.returncode==0 and os.path.exists(frame_p) and os.path.getsize(frame_p)>500
    except: pass
    try:
        r = subprocess.run(["ffmpeg","-i",video_path,"-vn","-acodec","libopus","-b:a","64k","-y",audio_p], capture_output=True, timeout=60)
        ao = r.returncode==0 and os.path.exists(audio_p) and os.path.getsize(audio_p)>200
    except: pass
    return (frame_p if fo else None), (audio_p if ao else None)

async def analyze_video(message, file_id, caption=""):
    uid = message.from_user.id; chat_id = message.chat.id
    try:
        file = await bot.get_file(file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name); vp = tmp.name
        vis = speech = None
        if FFMPEG:
            fp, ap = extract_video_parts(vp)
            try: os.unlink(vp)
            except: pass
            if fp:
                with open(fp,"rb") as f: b64 = base64.b64encode(f.read()).decode()
                try: os.unlink(fp)
                except: pass
                vis = await gemini_vision(b64, caption or "Опиши что на кадре из видео.")
            if ap:
                speech = await speech_to_text(ap)
                try: os.unlink(ap)
                except: pass
        else:
            try: os.unlink(vp)
            except: pass
        parts_r = []
        if vis: parts_r.append(f"👁 {vis[:400]}")
        if speech: parts_r.append(f"🎤 {speech[:300]}")
        if parts_r: await message.answer("📹 " + "\n\n".join(parts_r))
        ctx = "Пользователь прислал видео. "
        if caption: ctx += f"Подпись: {caption}. "
        if vis: ctx += f"На видео: {vis}. "
        if speech: ctx += f"Говорят: {speech}. "
        await process_message(message, ctx)
    except Exception as e: logger.error(f"Video err: {e}"); await message.answer("Не смог обработать видео 😕")


# ══════════════════════════════════════════════════════════════════════════════
# КОМАНДЫ
# ══════════════════════════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def cmd_start(message: Message):
    name = (message.from_user.first_name or "").strip()
    uid = message.from_user.id
    DB.ensure_user(uid, name, message.from_user.username or "")
    g = f"Привет, {name}!" if name else "Привет!"
    await message.answer(
        f"{g} Я NEXUM v4.0 — AI нового поколения. 🤖\n\n"
        "Умею:\n"
        "💬 Отвечаю на любом языке как носитель\n"
        "🎨 Генерирую реалистичные фото (10 стилей)\n"
        "🎬 Генерирую видео\n"
        "🎵 Создаю музыку\n"
        "🔊 Озвучиваю живым голосом (50+ голосов, WAV/MP3)\n"
        "📥 Скачиваю YouTube, TikTok, Instagram (MP3/MP4/WAV)\n"
        "👁 Анализирую фото, видео, голосовые\n"
        "📊 Управляю группами и каналами\n"
        "🗑 Удаляю сообщения по ключевому слову\n"
        "🔍 Ищу актуальную информацию\n"
        "♾️ Помню тебя вечно\n\n"
        "/help — все команды\n\n"
        "Напиши что нужно 👇"
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "NEXUM v4.0 — AI без границ\n\n"
        "Основные:\n"
        "/start /help /voice /clear /stats /myfacts /myname\n\n"
        "Группа и канал:\n"
        "/groupstats — статистика группы\n"
        "/manage — управление группой (для админов)\n"
        "/channel — управление каналом\n"
        "/schedule ЧЧ:ММ тема — автопосты\n"
        "/delete слово — удалить сообщения\n"
        "/post тема — написать пост\n"
        "/improve — анализ кода бота\n\n"
        "В группе: @упоминание или reply на мои сообщения"
    )

@dp.message(Command("voice"))
async def cmd_voice(message: Message):
    await message.answer("🎙 Выбери голос:", reply_markup=kb_voice())

@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    DB.clear_history(message.from_user.id, message.chat.id)
    await message.answer("🧹 История очищена! Факты сохранены.")

@dp.message(Command("myname"))
async def cmd_myname(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2: await message.answer("/myname ТвоёИмя"); return
    name = parts[1].strip()[:30]
    with DB.conn() as conn: conn.execute("UPDATE users SET name=? WHERE uid=?", (name, message.from_user.id))
    DB.add_memory(message.from_user.id, f"Зовут {name}", "identity", 10)
    await message.answer(f"Запомнил, {name}! 👊")

@dp.message(Command("myfacts"))
async def cmd_myfacts(message: Message):
    user = DB.get_user(message.from_user.id)
    memories = user.get("memories",[])
    if not memories: await message.answer("Пока ничего не знаю\nРасскажи что-нибудь!"); return
    by_cat: Dict[str, List] = {}
    for m in memories: by_cat.setdefault(m["category"],[]).append(m["fact"])
    text = "📝 Что знаю о тебе:\n\n"
    for cat, facts in by_cat.items():
        text += f"[{cat.upper()}]\n" + "".join(f"  • {f}\n" for f in facts[:5]) + "\n"
    await message.answer(text)

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    uid = message.from_user.id
    user = DB.get_user(uid)
    if not user: await message.answer("/start"); return
    voice = DB.get_voice(uid)
    voice_name = EDGE_TTS_VOICES.get(voice, "Авто") if voice != "auto" else "Авто"
    await message.answer(
        f"📊 Статистика:\n\n"
        f"👤 {user.get('name','Без имени')}\n"
        f"💬 Сообщений: {user.get('total_messages',0)}\n"
        f"🧠 Фактов: {len(user.get('memories',[]))}\n"
        f"🎙 Голос: {voice_name}\n"
        f"📅 С: {(user.get('first_seen') or '')[:10]}"
    )

@dp.message(Command("groupstats"))
async def cmd_groupstats(message: Message):
    stats = DB.get_group_stats(message.chat.id)
    if not stats: await message.answer("Статистика пустая 📊"); return
    medals = ["🥇","🥈","🥉"]
    text = "📊 Статистика группы:\n\n"
    for i, s in enumerate(stats[:15], 1):
        nm = s.get("name") or s.get("username") or f"User{s['uid']}"
        medal = medals[i-1] if i <= 3 else f"{i}."
        text += f"{medal} {nm}: {s['messages']} сообщ., {s['words']} слов"
        if s.get("media"): text += f", {s['media']} медиа"
        text += "\n"
    await message.answer(text, reply_markup=kb_group_manage())

@dp.message(Command("manage"))
async def cmd_manage(message: Message):
    uid = message.from_user.id; chat_id = message.chat.id
    if not await is_admin(chat_id, uid):
        await message.answer("Только для администраторов."); return
    await message.answer("⚙️ Управление группой:", reply_markup=kb_group_manage())

@dp.message(Command("channel"))
async def cmd_channel(message: Message):
    await message.answer("📺 Управление каналом:", reply_markup=kb_channel_manage())

@dp.message(Command("schedule"))
async def cmd_schedule(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Использование: /schedule ЧЧ:ММ тема\nПример: /schedule 09:00 утренние новости"); return
    uid = message.from_user.id; chat_id = message.chat.id
    if not await is_admin(chat_id, uid):
        await message.answer("Только для администраторов"); return
    time_str = parts[1]; topic = parts[2]
    try:
        h, m = map(int, time_str.split(":"))
        cron = f"{m} {h} * * *"
        DB.add_scheduled_post(chat_id, cron, topic)
        scheduler.add_job(scheduled_post_job, trigger=CronTrigger(hour=h, minute=m),
            args=[chat_id, topic], id=f"post_{chat_id}_{h}_{m}", replace_existing=True)
        await message.answer(f"✅ Расписание: каждый день в {time_str}\nТема: {topic}")
    except ValueError:
        await message.answer("Неверный формат. Используй ЧЧ:ММ")

async def scheduled_post_job(chat_id, topic):
    try:
        post = await generate_channel_post(chat_id, topic)
        await bot.send_message(chat_id, strip_markdown(post))
        logger.info(f"Scheduled post sent to {chat_id}")
    except Exception as e:
        logger.error(f"Scheduled post err: {e}")

@dp.message(Command("delete"))
async def cmd_delete(message: Message):
    uid = message.from_user.id; chat_id = message.chat.id
    if not await is_admin(chat_id, uid):
        await message.answer("Только для администраторов"); return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /delete слово"); return
    keyword = parts[1].strip()
    action_id = f"delkw_{chat_id}_{int(time.time())}"
    PENDING_ACTIONS[action_id] = {"type":"delete_keyword","chat_id":chat_id,"keyword":keyword,"description":f"удалить сообщения со словом '{keyword}'"}
    await message.answer(f"⚠️ Удалить все сообщения со словом '{keyword}'?", reply_markup=kb_confirm(action_id,"удалить"))

@dp.message(Command("post"))
async def cmd_post(message: Message):
    parts = message.text.split(maxsplit=1)
    topic = parts[1].strip() if len(parts) > 1 else ""
    await message.answer("📝 Генерирую пост...")
    try:
        post = await generate_channel_post(message.chat.id, topic)
        await message.answer(
            f"📝 Пост:\n\n{strip_markdown(post)}\n\n---\nОпубликовать?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"pub_post_{message.chat.id}"),
                InlineKeyboardButton(text="🔄 Другой", callback_data="ch_post"),
            ]])
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@dp.message(Command("improve"))
async def cmd_improve(message: Message):
    await bot.send_chat_action(message.chat.id, "typing")
    await message.answer("🔍 Анализирую NEXUM v4.0...")
    try:
        with open(__file__,"r",encoding="utf-8") as f: source = f.read()
        prompt = f"""Ты Python эксперт. Проанализируй бот NEXUM v4.0.

КОД (первые 6000 символов):
{source[:6000]}

Дай:
1. КРИТИЧЕСКИЕ БАГИ — что сломано
2. УЛУЧШЕНИЯ — что лучше
3. НОВЫЕ ФУНКЦИИ — 5 идей
4. ОПТИМИЗАЦИЯ

Конкретно, с примерами кода."""
        suggestions = await ai_generate([{"role":"user","content":prompt}], max_tokens=3000, task_type="code")
        await send_long(message, f"🧠 Анализ:\n\n{suggestions}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ХЭНДЛЕРЫ СООБЩЕНИЙ
# ══════════════════════════════════════════════════════════════════════════════

@dp.message(F.text)
async def handle_text(message: Message):
    text = message.text or ""
    uid = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type

    if chat_type in ("group","supergroup","channel"):
        DB.update_group_stats(chat_id, uid, message.from_user.first_name or "", message.from_user.username or "", text=text)

    if chat_type in ("group","supergroup"):
        try:
            me = await bot.get_me()
            my_id = me.id
            my_username = f"@{(me.username or '').lower()}"
            mentioned = False
            if message.entities:
                for e in message.entities:
                    if e.type == "mention" and text[e.offset:e.offset+e.length].lower() == my_username:
                        mentioned = True; break
                    elif e.type == "text_mention" and e.user and e.user.id == my_id:
                        mentioned = True; break
            if not mentioned and my_username and my_username in text.lower():
                mentioned = True
            replied = (message.reply_to_message and message.reply_to_message.from_user and
                      message.reply_to_message.from_user.id == my_id)
            if not mentioned and not replied: return
            if me.username:
                text = re.sub(rf'@{me.username}\s*','',text,flags=re.IGNORECASE).strip()
            text = text or "привет"
        except Exception as e: logger.error(f"Group err: {e}"); return

    reply = message.reply_to_message
    if reply:
        if reply.video_note: await handle_vidnote_q(message, reply.video_note, text); return
        elif reply.video: await analyze_video(message, reply.video.file_id, text or reply.caption or ""); return
        elif reply.photo: await handle_photo_q(message, reply.photo[-1], text or "Опиши фото"); return
        elif reply.voice: await handle_voice_q(message, reply.voice, text); return

    ttype = "general"
    tl = text.lower()
    if any(k in tl for k in ["код","функция","скрипт","python","javascript","программ","def ","class "]): ttype = "code"
    elif any(k in tl for k in ["новости","сегодня","текущий","актуальн","2025","2026","цена","курс"]): ttype = "analysis"
    elif any(k in tl for k in ["напиши","стихотворение","рассказ","история","стиль","творч"]): ttype = "creative"

    await process_message(message, text, ttype)

@dp.message(F.voice)
async def handle_voice(message: Message):
    uid = message.from_user.id; chat_id = message.chat.id
    if message.chat.type in ("group","supergroup"):
        DB.update_group_stats(chat_id, uid, message.from_user.first_name or "", message.from_user.username or "", msg_type="voice")
    await bot.send_chat_action(chat_id, "typing")
    try:
        file = await bot.get_file(message.voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg",delete=False) as tmp:
            await bot.download_file(file.file_path,tmp.name); ap = tmp.name
        text = await speech_to_text(ap)
        try: os.unlink(ap)
        except: pass
        if not text or len(text.strip()) < 2:
            await message.answer("🎤 Не распознал речь. Попробуй ещё раз."); return
        await message.answer(f"🎤 {text}")
        await process_message(message, text)
    except Exception as e: logger.error(f"Voice err: {e}"); await message.answer("Ошибка голосового 😕")

@dp.message(F.video_note)
async def handle_vidnote(message: Message):
    uid = message.from_user.id; chat_id = message.chat.id
    if message.chat.type in ("group","supergroup"):
        DB.update_group_stats(chat_id, uid, message.from_user.first_name or "", message.from_user.username or "", msg_type="video_note")
    await bot.send_chat_action(chat_id, "typing")
    try:
        file = await bot.get_file(message.video_note.file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp4",delete=False) as tmp:
            await bot.download_file(file.file_path,tmp.name); vp = tmp.name
        vis = speech = None
        if FFMPEG:
            fp, ap = extract_video_parts(vp)
            try: os.unlink(vp)
            except: pass
            if fp:
                with open(fp,"rb") as f: b64 = base64.b64encode(f.read()).decode()
                try: os.unlink(fp)
                except: pass
                vis = await gemini_vision(b64,"Опиши кружочек: кто, что делает, эмоции.")
            if ap:
                speech = await speech_to_text(ap)
                try: os.unlink(ap)
                except: pass
        else:
            try: os.unlink(vp)
            except: pass
        parts_r = []
        if vis: parts_r.append(f"👁 {vis[:300]}")
        if speech: parts_r.append(f"🎤 {speech}")
        if parts_r: await message.answer("📹 " + "\n\n".join(parts_r))
        ctx = "Пользователь прислал видеокружок. "
        if vis: ctx += f"Видео: {vis}. "
        if speech: ctx += f"Говорит: {speech}. "
        if not vis and not speech: ctx += "Не удалось проанализировать."
        await process_message(message, ctx)
    except Exception as e: logger.error(f"Vidnote err: {e}"); await message.answer("Не смог обработать кружочек 😕")

@dp.message(F.video)
async def handle_video(message: Message):
    uid = message.from_user.id; chat_id = message.chat.id
    if message.chat.type in ("group","supergroup"):
        DB.update_group_stats(chat_id, uid, message.from_user.first_name or "", message.from_user.username or "", msg_type="video")
    await bot.send_chat_action(chat_id, "typing")
    await analyze_video(message, message.video.file_id, message.caption or "")

@dp.message(F.photo)
async def handle_photo(message: Message):
    uid = message.from_user.id; chat_id = message.chat.id
    if message.chat.type in ("group","supergroup"):
        DB.update_group_stats(chat_id, uid, message.from_user.first_name or "", message.from_user.username or "", msg_type="photo")
    caption = message.caption or "Опиши подробно что на фото"
    await bot.send_chat_action(chat_id, "typing")
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        with tempfile.NamedTemporaryFile(suffix=".jpg",delete=False) as tmp:
            await bot.download_file(file.file_path,tmp.name); pp = tmp.name
        with open(pp,"rb") as f: b64 = base64.b64encode(f.read()).decode()
        try: os.unlink(pp)
        except: pass
        analysis = await gemini_vision(b64, caption)
        if analysis:
            DB.add_msg(uid, chat_id, "user", f"[фото] {caption}")
            DB.add_msg(uid, chat_id, "assistant", analysis)
            await message.answer(strip_markdown(analysis))
        else:
            await message.answer("Не смог проанализировать фото 😕")
    except Exception as e: logger.error(f"Photo err: {e}"); await message.answer("Ошибка 😕")

@dp.message(F.document)
async def handle_doc(message: Message):
    caption = message.caption or "Проанализируй этот файл"
    if message.chat.type in ("group","supergroup"):
        DB.update_group_stats(message.chat.id, message.from_user.id, message.from_user.first_name or "", message.from_user.username or "", msg_type="document")
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        file = await bot.get_file(message.document.file_id)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            await bot.download_file(file.file_path,tmp.name); fp = tmp.name
        try:
            with open(fp,"r",encoding="utf-8",errors="ignore") as f: content = f.read()[:12000]
        except: content = "[Не удалось прочитать]"
        try: os.unlink(fp)
        except: pass
        fname = message.document.file_name or "файл"
        await process_message(message, f"{caption}\n\nФайл '{fname}':\n{content}", task_type="analysis")
    except Exception as e: logger.error(f"Doc err: {e}"); await message.answer("Не удалось прочитать 😕")

@dp.message(F.audio)
async def handle_audio(message: Message):
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        file = await bot.get_file(message.audio.file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp3",delete=False) as tmp:
            await bot.download_file(file.file_path,tmp.name); ap = tmp.name
        text = await speech_to_text(ap)
        try: os.unlink(ap)
        except: pass
        if text:
            await message.answer(f"🎵 Транскрипция:\n\n{text}")
        else:
            await process_message(message, f"Пользователь прислал аудио. {message.caption or ''}")
    except Exception as e: logger.error(f"Audio err: {e}"); await message.answer("Не смог обработать 😕")

@dp.message(F.sticker)
async def handle_sticker(message: Message):
    if message.chat.type in ("group","supergroup"):
        DB.update_group_stats(message.chat.id, message.from_user.id, message.from_user.first_name or "", message.from_user.username or "", msg_type="sticker")
    await process_message(message, "[стикер] Отреагируй живо как настоящий друг!")

@dp.message(F.location)
async def handle_location(message: Message):
    lat = message.location.latitude; lon = message.location.longitude
    w = await get_weather(f"{lat},{lon}")
    if w: await message.answer(f"📍 Погода:\n\n{w}")
    else: await message.answer("📍 Геолокация получена!")

async def handle_vidnote_q(message, vn, q):
    file = await bot.get_file(vn.file_id)
    with tempfile.NamedTemporaryFile(suffix=".mp4",delete=False) as tmp:
        await bot.download_file(file.file_path,tmp.name); vp = tmp.name
    vis = speech = None
    if FFMPEG:
        fp, ap = extract_video_parts(vp)
        try: os.unlink(vp)
        except: pass
        if fp:
            with open(fp,"rb") as f: b64 = base64.b64encode(f.read()).decode()
            try: os.unlink(fp)
            except: pass
            vis = await gemini_vision(b64, q or "Опиши видеокружок")
        if ap:
            speech = await speech_to_text(ap)
            try: os.unlink(ap)
            except: pass
    else:
        try: os.unlink(vp)
        except: pass
    ctx = f"Вопрос: {q}. Видеокружок — "
    if vis: ctx += f"визуально: {vis}. "
    if speech: ctx += f"говорит: {speech}. "
    if not vis and not speech: ctx += "не смог проанализировать."
    await process_message(message, ctx)

async def handle_photo_q(message, photo, q):
    uid = message.from_user.id; chat_id = message.chat.id
    file = await bot.get_file(photo.file_id)
    with tempfile.NamedTemporaryFile(suffix=".jpg",delete=False) as tmp:
        await bot.download_file(file.file_path,tmp.name); pp = tmp.name
    with open(pp,"rb") as f: b64 = base64.b64encode(f.read()).decode()
    try: os.unlink(pp)
    except: pass
    analysis = await gemini_vision(b64, q)
    if analysis:
        DB.add_msg(uid, chat_id, "user", f"[фото+вопрос] {q}")
        DB.add_msg(uid, chat_id, "assistant", analysis)
        await message.answer(strip_markdown(analysis))
    else:
        await message.answer("Не смог проанализировать 😕")

async def handle_voice_q(message, voice, q):
    await bot.send_chat_action(message.chat.id, "typing")
    file = await bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg",delete=False) as tmp:
        await bot.download_file(file.file_path,tmp.name); ap = tmp.name
    text = await speech_to_text(ap)
    try: os.unlink(ap)
    except: pass
    if text: await process_message(message, f"{q}\n\nГолосовое: {text}")
    else: await message.answer("Не смог разобрать речь 🎤")

@dp.my_chat_member()
async def handle_bot_added(update):
    try:
        new_status = update.new_chat_member.status
        chat_id = update.chat.id
        if new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
            chat = await bot.get_chat(chat_id)
            title = chat.title or "Без названия"
            ctype = chat.type
            if ctype == "channel":
                await asyncio.sleep(2)
                await bot.send_message(chat_id,
                    f"Привет! Я NEXUM v4.0.\n\nПровожу анализ канала и подстроюсь под его стиль.\n/channel — управление",
                    reply_markup=kb_channel_manage()
                )
                asyncio.create_task(auto_analyze_channel(chat_id, title))
            elif ctype in ("group","supergroup"):
                await bot.send_message(chat_id,
                    f"Привет! Я NEXUM v4.0 — AI для вашей группы.\n\n"
                    f"@упоминание или reply на мои сообщения.\n/help — команды"
                )
    except Exception as e:
        logger.error(f"Bot added err: {e}")

async def auto_analyze_channel(chat_id, title):
    try:
        await asyncio.sleep(5)
        analysis = await analyze_channel(chat_id)
        style_prompt = [{"role":"user","content":f"На основе анализа канала '{title}', напиши в 3-5 предложениях КАК писать посты (стиль, тон, длина):\n\n{analysis}"}]
        style = await ai_generate(style_prompt, max_tokens=300, task_type="analysis")
        DB.save_channel_profile(chat_id, title, analysis, style)
        logger.info(f"Channel {chat_id} analyzed")
    except Exception as e:
        logger.error(f"Auto analyze err: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ЗАПУСК
# ══════════════════════════════════════════════════════════════════════════════

async def restore_scheduled_posts():
    try:
        with DB.conn() as conn:
            rows = conn.execute("SELECT chat_id, cron_expr, template FROM scheduled_posts WHERE active=1").fetchall()
        for chat_id, cron_expr, topic in rows:
            parts = cron_expr.split()
            if len(parts) >= 2:
                m, h = int(parts[0]), int(parts[1])
                scheduler.add_job(scheduled_post_job, trigger=CronTrigger(hour=h, minute=m),
                    args=[chat_id, topic], id=f"post_{chat_id}_{h}_{m}", replace_existing=True)
        logger.info(f"Restored {len(rows)} scheduled posts")
    except Exception as e:
        logger.error(f"Restore schedule err: {e}")

async def start_polling():
    init_database()
    scheduler.start()
    await restore_scheduled_posts()

    logger.info("=" * 60)
    logger.info("NEXUM v4.0 Starting...")
    logger.info(f"Gemini:   {len(GEMINI_KEYS)} keys")
    logger.info(f"Groq:     {len(GROQ_KEYS)} keys")
    logger.info(f"Claude:   {len(CLAUDE_KEYS)} keys")
    logger.info(f"DeepSeek: {len(DEEPSEEK_KEYS)} keys")
    logger.info(f"Grok/xAI: {len(GROK_KEYS)} keys")
    logger.info(f"SUNO:     {len(SUNO_KEYS)} keys")
    logger.info(f"ffmpeg:   {'YES' if FFMPEG else 'NO'}")
    logger.info(f"yt-dlp:   {'YES' if YTDLP else 'NO'}")
    logger.info("=" * 60)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(start_polling())
