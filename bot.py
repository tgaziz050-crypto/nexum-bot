"""
╔══════════════════════════════════════════════════════════════╗
║  NEXUM v7.0 — AI-ассистент нового поколения                 ║
║  Контекст: личка / группа / канал                           ║
║  Авто-распознавание сред, умные кнопки, система согласований║
╚══════════════════════════════════════════════════════════════╝
"""
import asyncio, logging, os, tempfile, base64, random, aiohttp, sys
import subprocess, shutil, sqlite3, re, time, json, hashlib, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote as uq
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, BufferedInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("NEXUM")

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from nexum_context import get_chat_context, context_instructions, should_show_full_menu, ChatContext, get_response_style
except ImportError:
    def get_chat_context(ct): return ct
    def context_instructions(ctx): return ""
    def should_show_full_menu(ctx): return ctx == "private"
    class ChatContext:
        PRIVATE="private"; GROUP="group"; SUPERGROUP="supergroup"; CHANNEL="channel"
    def get_response_style(ctx): return {"max_tokens":2000,"show_buttons":True,"show_menu":True}

try:
    from nexum_music_recognition import recognize_music, format_music_info
except ImportError:
    async def recognize_music(p): return None
    def format_music_info(i): return "Добавь AUDD_API_KEY"

try:
    from nexum_permissions import (
        PendingAction, create_approval_session, resolve_approval, get_approval,
        register_admin, rate_limiter
    )
    HAS_PERMS = True
except ImportError:
    HAS_PERMS = False
    class PendingAction:
        def __init__(self, *a, **kw): self.session_id = str(time.time())
    def create_approval_session(a): return a.session_id
    def resolve_approval(s): return None
    def get_approval(s): return None
    def register_admin(u, c): pass
    class _rl:
        def check(self, *a, **kw): return True
    rate_limiter = _rl()

try:
    from nexum_web import web_search, read_page, weather, exchange
except ImportError:
    async def web_search(q): return None
    async def read_page(u): return None
    async def weather(l): return None
    async def exchange(f, t): return None


# ═══════════════════════════════════════════════════════════
#  API КЛЮЧИ
# ═══════════════════════════════════════════════════════════
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

# ═══════════════════════════════════════════════════════════
#  ИНИЦИАЛИЗАЦИЯ
# ═══════════════════════════════════════════════════════════
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
scheduler = AsyncIOScheduler()

FFMPEG = shutil.which("ffmpeg")
YTDLP  = shutil.which("yt-dlp")

_ki: Dict[str,int] = {p:0 for p in ["g","gr","ds","cl","gk"]}
def gk(p, keys): return keys[_ki[p] % len(keys)] if keys else None
def rk(p, keys):
    if keys: _ki[p] = (_ki[p]+1) % len(keys)

# Хранилища состояний
INPUT_CTX: Dict[int, Dict] = {}
CONFIRMS: Dict[str, Dict] = {}
# Словарь admin_uid -> [чат_id] для системы согласований
ADMIN_CHATS: Dict[int, list] = {}
# Ожидающие ответа на разрешение: session_id -> данные
PENDING_APPROVALS: Dict[str, Dict] = {}


# ═══════════════════════════════════════════════════════════
#  FSM СОСТОЯНИЯ
# ═══════════════════════════════════════════════════════════
class States(StatesGroup):
    waiting_input = State()
    waiting_image_prompt = State()
    waiting_music_prompt = State()
    waiting_tts_text = State()
    waiting_video_prompt = State()
    waiting_search_query = State()
    waiting_download_url = State()
    waiting_translate_text = State()
    waiting_code_task = State()
    waiting_post_topic = State()
    waiting_reminder_time = State()
    waiting_reminder_text = State()
    waiting_delete_keyword = State()
    waiting_schedule_time = State()
    waiting_schedule_topic = State()
    waiting_weather_city = State()
    waiting_rate_from = State()
    waiting_rate_to = State()
    waiting_email_body = State()
    waiting_note_content = State()
    waiting_song_prompt = State()

# ═══════════════════════════════════════════════════════════
#  БАЗА ДАННЫХ
# ═══════════════════════════════════════════════════════════
DB = "nexum.db"

def init_db():
    with sqlite3.connect(DB) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            uid INTEGER PRIMARY KEY,
            name TEXT DEFAULT '', username TEXT DEFAULT '',
            lang TEXT DEFAULT 'ru', voice TEXT DEFAULT 'auto',
            first_seen TEXT, last_seen TEXT,
            total_msgs INTEGER DEFAULT 0, style TEXT DEFAULT 'default',
            admin_of TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS conv(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER, chat_id INTEGER,
            role TEXT, content TEXT,
            ts TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS memory(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER, cat TEXT, fact TEXT, imp INTEGER DEFAULT 5
        );
        CREATE TABLE IF NOT EXISTS summaries(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER, chat_id INTEGER, text TEXT
        );
        CREATE TABLE IF NOT EXISTS grp_msgs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER, uid INTEGER, msg_id INTEGER,
            text TEXT DEFAULT '', mtype TEXT DEFAULT 'text',
            ts TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS grp_stats(
            chat_id INTEGER, uid INTEGER,
            name TEXT DEFAULT '', username TEXT DEFAULT '',
            msgs INTEGER DEFAULT 0, words INTEGER DEFAULT 0,
            media INTEGER DEFAULT 0, voices INTEGER DEFAULT 0,
            stickers INTEGER DEFAULT 0,
            last_active TEXT, first_seen TEXT,
            PRIMARY KEY(chat_id, uid)
        );
        CREATE TABLE IF NOT EXISTS channels(
            chat_id INTEGER PRIMARY KEY,
            title TEXT, analysis TEXT DEFAULT '',
            style TEXT DEFAULT '', admin_uid INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS schedules(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER, hour INTEGER, minute INTEGER,
            topic TEXT, active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS notes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER, title TEXT, content TEXT,
            ts TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS todos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER, task TEXT, done INTEGER DEFAULT 0,
            ts TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS ic ON conv(uid,chat_id);
        CREATE INDEX IF NOT EXISTS im ON memory(uid);
        CREATE INDEX IF NOT EXISTS ig ON grp_msgs(chat_id);
        CREATE INDEX IF NOT EXISTS igs ON grp_stats(chat_id);
        """)
    log.info("✅ Database ready")

def dbc():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

class Db:
    @staticmethod
    def ensure(uid, name="", username=""):
        now = datetime.now().isoformat()
        with dbc() as c:
            c.execute("""INSERT INTO users(uid,name,username,first_seen,last_seen)VALUES(?,?,?,?,?)
                ON CONFLICT(uid) DO UPDATE SET last_seen=excluded.last_seen,
                name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END,
                username=CASE WHEN excluded.username!='' THEN excluded.username ELSE username END""",
                (uid, name, username, now, now))

    @staticmethod
    def user(uid) -> dict:
        with dbc() as c:
            r = c.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
            if not r: return {}
            u = dict(r)
            u['memory'] = [dict(x) for x in c.execute(
                "SELECT * FROM memory WHERE uid=? ORDER BY imp DESC", (uid,)).fetchall()]
            return u

    @staticmethod
    def voice(uid):
        with dbc() as c:
            r = c.execute("SELECT voice FROM users WHERE uid=?", (uid,)).fetchone()
            return r[0] if r else "auto"

    @staticmethod
    def set_voice(uid, v):
        with dbc() as c: c.execute("UPDATE users SET voice=? WHERE uid=?", (v, uid))

    @staticmethod
    def set_name(uid, n):
        with dbc() as c: c.execute("UPDATE users SET name=? WHERE uid=?", (n, uid))

    @staticmethod
    def remember(uid, fact, cat="gen", imp=5):
        with dbc() as c:
            rows = c.execute("SELECT id,fact FROM memory WHERE uid=? AND cat=?", (uid, cat)).fetchall()
            for rid, ef in rows:
                aw = set(fact.lower().split()); bw = set(ef.lower().split())
                if aw and bw and len(aw & bw) / len(aw | bw) > 0.65:
                    c.execute("UPDATE memory SET fact=? WHERE id=?", (fact, rid)); return
            c.execute("INSERT INTO memory(uid,cat,fact,imp)VALUES(?,?,?,?)", (uid, cat, fact, imp))
            c.execute("""DELETE FROM memory WHERE id IN(
                SELECT id FROM memory WHERE uid=? AND cat=? ORDER BY imp DESC LIMIT -1 OFFSET 30
            )""", (uid, cat))

    @staticmethod
    def extract_facts(uid, text):
        pats = [
            (r'меня зовут\s+([А-ЯЁа-яёA-Za-z]{2,20})', 'name', 10),
            (r'мне\s+(\d{1,2})\s*(?:год|лет)', 'age', 9),
            (r'(?:я из|живу в|нахожусь в)\s+([А-ЯЁа-яё\w\s]{2,25})', 'city', 8),
            (r'работаю\s+([А-ЯЁа-яё\w\s]{2,40})', 'work', 7),
            (r'люблю\s+([А-ЯЁа-яё\w\s,]{2,40})', 'hobby', 6),
        ]
        for p, cat, imp in pats:
            m = re.search(p, text, re.I)
            if m: Db.remember(uid, m.group(0).strip(), cat, imp)
        nm = re.search(r'(?:меня зовут|я\s*[-—])\s*([А-ЯЁA-Z][а-яёa-z]{1,15})', text)
        if nm:
            with dbc() as c: c.execute("UPDATE users SET name=? WHERE uid=?", (nm.group(1), uid))
            Db.remember(uid, f"Зовут {nm.group(1)}", 'name', 10)

    @staticmethod
    def history(uid, chat_id, n=35):
        with dbc() as c:
            rows = c.execute("SELECT role,content FROM conv WHERE uid=? AND chat_id=? ORDER BY id DESC LIMIT ?",
                (uid, chat_id, n)).fetchall()
        return list(reversed(rows))

    @staticmethod
    def add(uid, chat_id, role, content):
        with dbc() as c:
            c.execute("INSERT INTO conv(uid,chat_id,role,content)VALUES(?,?,?,?)", (uid, chat_id, role, content))
            if role == "user": c.execute("UPDATE users SET total_msgs=total_msgs+1 WHERE uid=?", (uid,))

    @staticmethod
    def clear(uid, chat_id):
        with dbc() as c: c.execute("DELETE FROM conv WHERE uid=? AND chat_id=?", (uid, chat_id))

    @staticmethod
    def summaries(uid, chat_id):
        with dbc() as c:
            return [r[0] for r in c.execute(
                "SELECT text FROM summaries WHERE uid=? AND chat_id=?", (uid, chat_id)).fetchall()]

    @staticmethod
    def grp_save(chat_id, uid, name, username, text="", mtype="text", msg_id=None):
        now = datetime.now().isoformat()
        w = len(text.split()) if text else 0
        with dbc() as c:
            c.execute("""INSERT INTO grp_stats(chat_id,uid,name,username,msgs,words,media,voices,stickers,last_active,first_seen)
                VALUES(?,?,?,?,1,?,?,?,?,?,?)
                ON CONFLICT(chat_id,uid) DO UPDATE SET msgs=msgs+1, words=words+excluded.words,
                media=media+excluded.media, voices=voices+excluded.voices,
                stickers=stickers+excluded.stickers, last_active=excluded.last_active,
                name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END,
                username=CASE WHEN excluded.username!='' THEN excluded.username ELSE username END""",
                (chat_id, uid, name, username, w,
                 1 if mtype not in ("text", "sticker") else 0,
                 1 if mtype == "voice" else 0,
                 1 if mtype == "sticker" else 0, now, now))
            if msg_id:
                c.execute("INSERT INTO grp_msgs(chat_id,uid,msg_id,text,mtype)VALUES(?,?,?,?,?)",
                    (chat_id, uid, msg_id, (text or "")[:500], mtype))
                c.execute("""DELETE FROM grp_msgs WHERE id IN(
                    SELECT id FROM grp_msgs WHERE chat_id=? ORDER BY id DESC LIMIT -1 OFFSET 10000
                )""", (chat_id,))

    @staticmethod
    def grp_stats(chat_id):
        with dbc() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM grp_stats WHERE chat_id=? ORDER BY msgs DESC LIMIT 20", (chat_id,)).fetchall()]

    @staticmethod
    def grp_msgs(chat_id, n=200):
        with dbc() as c:
            rows = c.execute("SELECT uid,msg_id,text,mtype,ts FROM grp_msgs WHERE chat_id=? ORDER BY id DESC LIMIT ?",
                (chat_id, n)).fetchall()
        return list(reversed([dict(r) for r in rows]))

    @staticmethod
    def channel(chat_id):
        with dbc() as c:
            r = c.execute("SELECT * FROM channels WHERE chat_id=?", (chat_id,)).fetchone()
            return dict(r) if r else None

    @staticmethod
    def save_channel(chat_id, title, analysis, style, admin_uid=0):
        with dbc() as c:
            c.execute("""INSERT INTO channels(chat_id,title,analysis,style,admin_uid)VALUES(?,?,?,?,?)
                ON CONFLICT(chat_id) DO UPDATE SET analysis=excluded.analysis,style=excluded.style,
                admin_uid=CASE WHEN excluded.admin_uid!=0 THEN excluded.admin_uid ELSE admin_uid END""",
                (chat_id, title, analysis, style, admin_uid))

    @staticmethod
    def notes(uid):
        with dbc() as c:
            return [dict(r) for r in c.execute("SELECT * FROM notes WHERE uid=? ORDER BY ts DESC", (uid,)).fetchall()]

    @staticmethod
    def add_note(uid, title, content):
        with dbc() as c: c.execute("INSERT INTO notes(uid,title,content)VALUES(?,?,?)", (uid, title, content))

    @staticmethod
    def del_note(nid, uid):
        with dbc() as c: c.execute("DELETE FROM notes WHERE id=? AND uid=?", (nid, uid))

    @staticmethod
    def todos(uid):
        with dbc() as c:
            return [dict(r) for r in c.execute("SELECT * FROM todos WHERE uid=? ORDER BY done,id", (uid,)).fetchall()]

    @staticmethod
    def add_todo(uid, task):
        with dbc() as c: c.execute("INSERT INTO todos(uid,task)VALUES(?,?)", (uid, task))

    @staticmethod
    def done_todo(tid, uid):
        with dbc() as c: c.execute("UPDATE todos SET done=1 WHERE id=? AND uid=?", (tid, uid))

    @staticmethod
    def del_todo(tid, uid):
        with dbc() as c: c.execute("DELETE FROM todos WHERE id=? AND uid=?", (tid, uid))

    @staticmethod
    async def maybe_compress(uid, chat_id):
        try:
            with dbc() as c:
                n = c.execute("SELECT COUNT(*) FROM conv WHERE uid=? AND chat_id=?", (uid, chat_id)).fetchone()[0]
                if n <= 60: return
                old = c.execute("SELECT id,role,content FROM conv WHERE uid=? AND chat_id=? ORDER BY id ASC LIMIT 30",
                    (uid, chat_id)).fetchall()
            if not old: return
            lines = [("User" if r[1] == "user" else "NEXUM") + ": " + r[2][:200] for r in old]
            s = await ask([{"role": "user", "content": "Кратко резюмируй диалог (80 слов):\n" + "\n".join(lines)}], max_t=150)
            if not s: return
            with dbc() as c:
                c.execute("INSERT INTO summaries(uid,chat_id,text)VALUES(?,?,?)", (uid, chat_id, s))
                ids = ",".join(str(r[0]) for r in old)
                c.execute(f"DELETE FROM conv WHERE id IN({ids})")
        except Exception as e:
            log.error(f"Compress: {e}")


# ═══════════════════════════════════════════════════════════
#  AI ПРОВАЙДЕРЫ
# ═══════════════════════════════════════════════════════════
async def _gemini(msgs, model="gemini-2.0-flash-exp", max_t=4096, temp=0.85):
    if not GEMINI_KEYS: return None
    sys_txt = ""; contents = []
    for m in msgs:
        if m["role"] == "system": sys_txt = m["content"]
        elif m["role"] == "user": contents.append({"role":"user","parts":[{"text":m["content"]}]})
        else: contents.append({"role":"model","parts":[{"text":m["content"]}]})
    if not contents: return None
    body = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_t, "temperature": temp, "topP": 0.95},
        "safetySettings": [{"category": c, "threshold": "BLOCK_NONE"} for c in
            ["HARM_CATEGORY_HARASSMENT","HARM_CATEGORY_HATE_SPEECH",
             "HARM_CATEGORY_SEXUALLY_EXPLICIT","HARM_CATEGORY_DANGEROUS_CONTENT"]]
    }
    if sys_txt: body["systemInstruction"] = {"parts": [{"text": sys_txt}]}
    for _ in range(len(GEMINI_KEYS)):
        key = gk("g", GEMINI_KEYS)
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json=body, timeout=aiohttp.ClientTimeout(total=50)) as r:
                    if r.status in (429, 500, 503): rk("g", GEMINI_KEYS); continue
                    if r.status == 200:
                        d = await r.json()
                        try: return d["candidates"][0]["content"]["parts"][0]["text"]
                        except: rk("g", GEMINI_KEYS); continue
                    rk("g", GEMINI_KEYS)
        except: rk("g", GEMINI_KEYS)
    return None

async def _gemini_vision(b64, prompt, mime="image/jpeg"):
    if not GEMINI_KEYS: return None
    body = {
        "contents": [{"parts":[{"text":prompt},{"inline_data":{"mime_type":mime,"data":b64}}]}],
        "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.7},
        "safetySettings": [{"category": c, "threshold": "BLOCK_NONE"} for c in
            ["HARM_CATEGORY_HARASSMENT","HARM_CATEGORY_HATE_SPEECH",
             "HARM_CATEGORY_SEXUALLY_EXPLICIT","HARM_CATEGORY_DANGEROUS_CONTENT"]]
    }
    for _ in range(len(GEMINI_KEYS)):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={gk('g',GEMINI_KEYS)}"
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json=body, timeout=aiohttp.ClientTimeout(total=40)) as r:
                    if r.status in (429, 500, 503): rk("g", GEMINI_KEYS); continue
                    if r.status == 200:
                        d = await r.json()
                        try: return d["candidates"][0]["content"]["parts"][0]["text"]
                        except: rk("g", GEMINI_KEYS)
                    else: rk("g", GEMINI_KEYS)
        except: rk("g", GEMINI_KEYS)
    return None

async def _groq(msgs, model="llama-3.3-70b-versatile", max_t=2048, temp=0.8):
    if not GROQ_KEYS: return None
    for _ in range(len(GROQ_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {gk('gr',GROQ_KEYS)}"},
                    json={"model": model, "messages": msgs, "max_tokens": max_t, "temperature": temp},
                    timeout=aiohttp.ClientTimeout(total=35)) as r:
                    if r.status == 429: rk("gr", GROQ_KEYS); await asyncio.sleep(1); continue
                    if r.status == 200: return (await r.json())["choices"][0]["message"]["content"]
                    rk("gr", GROQ_KEYS)
        except: rk("gr", GROQ_KEYS)
    return None

async def _ds(msgs, max_t=4096, temp=0.8):
    if not DS_KEYS: return None
    for _ in range(len(DS_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.deepseek.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {gk('ds',DS_KEYS)}"},
                    json={"model": "deepseek-chat", "messages": msgs, "max_tokens": max_t, "temperature": temp},
                    timeout=aiohttp.ClientTimeout(total=55)) as r:
                    if r.status == 429: rk("ds", DS_KEYS); continue
                    if r.status == 200: return (await r.json())["choices"][0]["message"]["content"]
                    rk("ds", DS_KEYS)
        except: rk("ds", DS_KEYS)
    return None

async def _claude(msgs, max_t=4096, temp=0.8):
    if not CLAUDE_KEYS: return None
    sys = ""; filt = []
    for m in msgs:
        if m["role"] == "system": sys = m["content"]
        else: filt.append(m)
    if not filt: return None
    body = {"model": "claude-opus-4-5", "max_tokens": max_t, "temperature": temp, "messages": filt}
    if sys: body["system"] = sys
    for _ in range(len(CLAUDE_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": gk("cl", CLAUDE_KEYS), "anthropic-version": "2023-06-01"},
                    json=body, timeout=aiohttp.ClientTimeout(total=60)) as r:
                    if r.status in (429, 529): rk("cl", CLAUDE_KEYS); await asyncio.sleep(3); continue
                    if r.status == 200: return (await r.json())["content"][0]["text"]
                    rk("cl", CLAUDE_KEYS)
        except: rk("cl", CLAUDE_KEYS)
    return None

async def _grok(msgs, max_t=4096, temp=0.8):
    if not GROK_KEYS: return None
    for _ in range(len(GROK_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.x.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {gk('gk',GROK_KEYS)}"},
                    json={"model": "grok-beta", "messages": msgs, "max_tokens": max_t, "temperature": temp},
                    timeout=aiohttp.ClientTimeout(total=55)) as r:
                    if r.status == 429: rk("gk", GROK_KEYS); continue
                    if r.status == 200: return (await r.json())["choices"][0]["message"]["content"]
                    rk("gk", GROK_KEYS)
        except: rk("gk", GROK_KEYS); break
    return None

TASK_ORDERS = {
    "fast":     [("g","gemini-2.0-flash"),("gr","llama-3.3-70b-versatile"),("ds",None),("cl",None),("gk",None)],
    "code":     [("ds",None),("g","gemini-2.0-flash-exp"),("gr","llama-3.3-70b-versatile"),("cl",None)],
    "creative": [("g","gemini-2.0-flash-exp"),("cl",None),("gr","llama-3.3-70b-versatile"),("ds",None)],
    "analysis": [("g","gemini-2.0-flash-exp"),("ds",None),("gr","llama-3.3-70b-versatile"),("cl",None)],
    "general":  [("g","gemini-2.0-flash-exp"),("gr","llama-3.3-70b-versatile"),("ds",None),("cl",None),("gk",None)],
}

async def ask(msgs, max_t=4096, temp=0.85, task="general") -> str:
    order = TASK_ORDERS.get(task, TASK_ORDERS["general"])
    for pname, model in order:
        try:
            r = None
            if pname == "g" and GEMINI_KEYS:
                for mdl in ([model] if model else []) + ["gemini-2.0-flash-exp","gemini-2.0-flash","gemini-1.5-flash-latest"]:
                    r = await _gemini(msgs, model=mdl, max_t=max_t, temp=temp)
                    if r: break
            elif pname == "gr" and GROQ_KEYS:
                for mdl in [model or "llama-3.3-70b-versatile","llama-3.1-70b-versatile","llama3-70b-8192"]:
                    r = await _groq(msgs, model=mdl, max_t=min(max_t, 2048), temp=temp)
                    if r: break
            elif pname == "ds" and DS_KEYS:
                r = await _ds(msgs, max_t=max_t, temp=temp)
            elif pname == "cl" and CLAUDE_KEYS:
                r = await _claude(msgs, max_t=min(max_t, 4096), temp=temp)
            elif pname == "gk" and GROK_KEYS:
                r = await _grok(msgs, max_t=max_t, temp=temp)
            if r and r.strip():
                log.info(f"✓ AI: {pname}")
                return r
        except Exception as e:
            log.warning(f"✗ {pname}: {e}")
    if GROQ_KEYS:
        try:
            short = [m for m in msgs if m["role"] != "system"][-3:]
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_KEYS[0]}"},
                    json={"model":"llama3-8b-8192","messages":short or msgs[-2:],"max_tokens":600,"temperature":0.7},
                    timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status == 200: return (await r.json())["choices"][0]["message"]["content"]
        except: pass
    raise Exception("Все AI временно недоступны. Попробуй через 30 секунд.")

async def stt(path) -> Optional[str]:
    if not GROQ_KEYS: return None
    for _ in range(len(GROQ_KEYS)):
        try:
            with open(path, "rb") as f: data = f.read()
            ext = os.path.splitext(path)[1] or ".ogg"
            ct = "audio/ogg" if "ogg" in ext else "audio/mpeg"
            async with aiohttp.ClientSession() as s:
                form = aiohttp.FormData()
                form.add_field("file", data, filename=f"audio{ext}", content_type=ct)
                form.add_field("model", "whisper-large-v3")
                async with s.post("https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {gk('gr',GROQ_KEYS)}"},
                    data=form, timeout=aiohttp.ClientTimeout(total=60)) as r:
                    if r.status == 429: rk("gr", GROQ_KEYS); continue
                    if r.status == 200: return (await r.json()).get("text", "").strip()
                    rk("gr", GROQ_KEYS)
        except: rk("gr", GROQ_KEYS)
    return None


# ═══════════════════════════════════════════════════════════
#  TTS
# ═══════════════════════════════════════════════════════════
VOICES = {
    "🇷🇺 Дмитрий":  "ru-RU-DmitryNeural",
    "🇷🇺 Светлана": "ru-RU-SvetlanaNeural",
    "🇺🇸 Guy":       "en-US-GuyNeural",
    "🇺🇸 Jenny":     "en-US-JennyNeural",
    "🇺🇸 Eric":      "en-US-EricNeural",
    "🇺🇸 Aria":      "en-US-AriaNeural",
    "🇩🇪 Conrad":    "de-DE-ConradNeural",
    "🇫🇷 Henri":     "fr-FR-HenriNeural",
    "🇯🇵 Nanami":    "ja-JP-NanamiNeural",
    "🇰🇷 SunHi":     "ko-KR-SunHiNeural",
    "🇸🇦 Hamed":     "ar-SA-HamedNeural",
    "🇺🇦 Ostap":     "uk-UA-OstapNeural",
}
VOICE_KEYS = list(VOICES.keys())

def detect_lang(t):
    t = t.lower()
    if re.search(r'[а-яё]', t): return "ru"
    if re.search(r'[\u0600-\u06ff]', t): return "ar"
    if re.search(r'[\u4e00-\u9fff]', t): return "zh"
    if re.search(r'[\u3040-\u30ff]', t): return "ja"
    if re.search(r'[\uac00-\ud7af]', t): return "ko"
    if re.search(r'[äöüß]', t): return "de"
    if re.search(r'[àâçéèêëîïôùûü]', t): return "fr"
    if re.search(r'[іїєґ]', t): return "uk"
    return "en"

async def do_tts(text: str, uid=0, voice_key=None, fmt="mp3") -> Optional[bytes]:
    clean = text.strip()[:1800]
    lang = detect_lang(clean)
    if voice_key and voice_key in VOICES:
        voice = VOICES[voice_key]
    else:
        saved = Db.voice(uid) if uid else "auto"
        if saved != "auto" and saved in VOICES:
            voice = VOICES[saved]
        else:
            vm = {"ru":["ru-RU-DmitryNeural","ru-RU-SvetlanaNeural"],
                  "en":["en-US-GuyNeural","en-US-JennyNeural"],
                  "de":["de-DE-ConradNeural"],"fr":["fr-FR-HenriNeural"],
                  "ar":["ar-SA-HamedNeural"],"ja":["ja-JP-NanamiNeural"],
                  "ko":["ko-KR-SunHiNeural"],"uk":["uk-UA-OstapNeural"]}
            voice = random.choice(vm.get(lang, ["en-US-GuyNeural"]))
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
    parts = []
    try:
        import edge_tts
        for chunk in chunks:
            comm = edge_tts.Communicate(chunk, voice, rate="+5%")
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp: p = tmp.name
            await comm.save(p)
            if os.path.exists(p) and os.path.getsize(p) > 300:
                with open(p, "rb") as f: parts.append(f.read())
            try: os.unlink(p)
            except: pass
    except Exception as e: log.error(f"TTS: {e}")
    if not parts: return None
    combined = b"".join(parts)
    if fmt == "wav" and FFMPEG:
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as fi: fi.write(combined); inp = fi.name
            out = inp + ".wav"
            subprocess.run(["ffmpeg","-i",inp,"-acodec","pcm_s16le","-ar","44100","-y",out], capture_output=True, timeout=30)
            if os.path.exists(out):
                with open(out, "rb") as f: w = f.read()
                try: os.unlink(inp); os.unlink(out)
                except: pass
                return w
        except: pass
    return combined

# ═══════════════════════════════════════════════════════════
#  ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ (несколько провайдеров)
# ═══════════════════════════════════════════════════════════
IMG_STYLES = {
    "📸 Реализм":   "photorealistic, 8k uhd, professional photo, ultra detailed, sharp",
    "🎌 Аниме":     "anime style, vibrant colors, studio ghibli, manga illustration",
    "🌐 3D":        "3D render, octane render, cinema 4d, volumetric lighting, ultra detailed",
    "🎨 Масло":     "oil painting, classical art, old masters, rich textures, museum quality",
    "💧 Акварель":  "watercolor painting, soft colors, artistic brushwork, dreamy",
    "🌃 Киберпанк": "cyberpunk art, neon lights, futuristic city, dark atmosphere",
    "🐉 Фэнтези":   "fantasy art, epic scene, magical illustration, artstation quality",
    "✏️ Эскиз":     "pencil sketch, detailed graphite drawing, professional illustration",
    "🟦 Пиксель":   "pixel art, 16-bit, retro game style, clean pixels",
    "📷 Портрет":   "portrait photography, studio lighting, 85mm lens, bokeh background",
    "⚡ Авто":      "ultra detailed, high quality, professional, stunning masterpiece",
}
IMG_MODELS = {"📸 Реализм":"flux-realism","🎌 Аниме":"flux-anime","🌐 3D":"flux-3d","📷 Портрет":"flux-realism"}

async def tr_en(text):
    if not re.search(r'[а-яёА-ЯЁ\u0400-\u04FF]', text): return text
    try:
        r = await _gemini([{"role":"user","content":f"Translate to English for AI image generation. Only translation, no explanation:\n{text}"}], max_t=100, temp=0.1)
        if r: return r.strip()
    except: pass
    return text

def is_img(d): return len(d) > 8 and (d[:3] == b'\xff\xd8\xff' or d[:4] == b'\x89PNG')

async def gen_img_pollinations(prompt: str, style: str = "⚡ Авто") -> Optional[bytes]:
    """Генерация через Pollinations AI."""
    en = await tr_en(prompt)
    suffix = IMG_STYLES.get(style, IMG_STYLES["⚡ Авто"])
    final = f"{en}, {suffix}"[:600]
    seed = random.randint(1, 999999)
    enc = uq(final, safe='')
    mdl = IMG_MODELS.get(style, "flux")
    urls = [
        f"https://image.pollinations.ai/prompt/{enc}?width=1024&height=1024&nologo=true&seed={seed}&model={mdl}",
        f"https://image.pollinations.ai/prompt/{enc}?width=1024&height=1024&nologo=true&seed={seed}&model=flux",
        f"https://image.pollinations.ai/prompt/{enc}?nologo=true&seed={seed}",
    ]
    conn = aiohttp.TCPConnector(ssl=False)
    for url in urls:
        try:
            async with aiohttp.ClientSession(connector=conn) as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=90),
                    headers={"User-Agent":"Mozilla/5.0"}, allow_redirects=True) as r:
                    if r.status == 200:
                        d = await r.read()
                        if is_img(d): return d
        except: pass
    return None

async def gen_img_prodia(prompt: str) -> Optional[bytes]:
    """Генерация через Prodia API (бесплатный)."""
    try:
        en = await tr_en(prompt)
        conn = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=conn) as s:
            # Запускаем job
            async with s.get(
                "https://api.prodia.com/generate",
                params={"new": "true", "prompt": en[:500], "model": "v1-5-pruned-emaonly.safetensors",
                        "negative_prompt": "blurry, bad quality", "steps": "25", "cfg_scale": "7",
                        "width": "1024", "height": "1024", "sampler": "DPM++ 2M Karras"},
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    job = await r.json()
                    job_id = job.get("job")
                    if not job_id: return None
            # Ждём результат
            for _ in range(30):
                await asyncio.sleep(3)
                async with s.get(f"https://api.prodia.com/job/{job_id}",
                    timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data.get("status") == "succeeded":
                            img_url = data.get("imageUrl")
                            if img_url:
                                async with s.get(img_url, timeout=aiohttp.ClientTimeout(total=20)) as ir:
                                    if ir.status == 200:
                                        d = await ir.read()
                                        if is_img(d): return d
                            return None
    except Exception as e:
        log.debug(f"Prodia: {e}")
    return None

async def gen_img(prompt: str, style: str = "⚡ Авто") -> Optional[bytes]:
    """Главная функция генерации изображений с fallback."""
    # Пробуем параллельно несколько провайдеров
    tasks = [
        gen_img_pollinations(prompt, style),
        gen_img_prodia(prompt),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, bytes) and is_img(r):
            return r
    return None


# ═══════════════════════════════════════════════════════════
#  ГЕНЕРАЦИЯ МУЗЫКИ (Suno-like)
# ═══════════════════════════════════════════════════════════
MUSIC_STYLES = {
    "🎸 Рок":       "energetic rock music, electric guitar, drums, distortion",
    "🎹 Поп":       "catchy pop song, upbeat melody, synthesizer, modern pop",
    "🎷 Джаз":      "smooth jazz, saxophone, piano, double bass, relaxed",
    "🔥 Хип-хоп":   "hip hop beat, bass, trap, 808, modern rap instrumental",
    "🎻 Классика":  "classical orchestra, piano, strings, symphonic",
    "🌊 Электро":   "electronic dance music, synthesizer, EDM, techno",
    "😌 Релакс":    "ambient relaxing music, piano, nature sounds, meditation",
    "🎶 Лирика":    "acoustic folk ballad, guitar, emotional, storytelling",
    "💃 Латин":     "latin music, salsa rhythm, percussion, upbeat",
    "⚡ Авто":      "instrumental music, melodic, professional recording",
}

async def gen_music_hf(prompt: str, style: str) -> Optional[bytes]:
    """Генерация через HuggingFace MusicGen."""
    en = await tr_en(prompt)
    style_desc = MUSIC_STYLES.get(style, MUSIC_STYLES["⚡ Авто"])
    full_prompt = f"{style_desc}, {en}"
    for model_url in [
        "https://api-inference.huggingface.co/models/facebook/musicgen-small",
        "https://api-inference.huggingface.co/models/facebook/musicgen-medium",
    ]:
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(model_url,
                        json={"inputs": full_prompt[:200], "parameters": {"duration": 20}},
                        timeout=aiohttp.ClientTimeout(total=130)) as r:
                        if r.status == 200:
                            ct = r.headers.get("content-type", "")
                            if any(x in ct for x in ["audio","octet-stream","flac","wav"]):
                                d = await r.read()
                                if len(d) > 5000: return d
                        elif r.status == 503 and attempt == 0:
                            await asyncio.sleep(25)
                        else: break
            except Exception as e: log.error(f"HF music: {e}"); break
    return None

async def gen_music_pollinations(prompt: str, style: str) -> Optional[bytes]:
    """Генерация через Pollinations Audio."""
    try:
        en = await tr_en(prompt)
        style_desc = MUSIC_STYLES.get(style, MUSIC_STYLES["⚡ Авто"])
        full_prompt = f"{style_desc}, {en}"
        enc = uq(full_prompt[:200], safe='')
        conn = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=conn) as s:
            async with s.get(f"https://audio.pollinations.ai/{enc}",
                timeout=aiohttp.ClientTimeout(total=60),
                headers={"User-Agent":"Mozilla/5.0"}) as r:
                if r.status == 200:
                    ct = r.headers.get("content-type", "")
                    if any(x in ct for x in ["audio","mpeg","wav","ogg"]):
                        d = await r.read()
                        if len(d) > 5000: return d
    except Exception as e: log.debug(f"Pollinations audio: {e}")
    return None

async def gen_music(prompt: str, style: str = "⚡ Авто") -> Optional[bytes]:
    """Главная функция генерации музыки с fallback."""
    tasks = [
        gen_music_hf(prompt, style),
        gen_music_pollinations(prompt, style),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, bytes) and len(r) > 5000:
            return r
    return None

async def gen_song_with_lyrics(prompt: str, style: str) -> tuple:
    """Создать текст песни + попробовать озвучить."""
    style_name = style.split()[-1] if style else "любой"
    lyrics_prompt = (
        f"Напиши текст песни в стиле {style_name} на тему: {prompt}\n\n"
        f"Структура:\n[Куплет 1]\n...\n[Припев]\n...\n[Куплет 2]\n...\n[Припев]\n\n"
        f"Требования: живо, эмоционально, на русском языке. Только текст, без комментариев."
    )
    lyrics = await ask([{"role": "user", "content": lyrics_prompt}], max_t=800, task="creative")
    return strip_md(lyrics), lyrics

# ═══════════════════════════════════════════════════════════
#  СКАЧИВАНИЕ
# ═══════════════════════════════════════════════════════════
async def dl(url, fmt="mp3"):
    if not YTDLP: return None, None, "yt-dlp не установлен"
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "%(title)s.%(ext)s")
        if fmt == "mp3":
            cmd = [YTDLP,"-x","--audio-format","mp3","--audio-quality","0","-o",out,"--no-playlist","--max-filesize","45M","--no-warnings",url]
        elif fmt == "wav":
            cmd = [YTDLP,"-x","--audio-format","wav","-o",out,"--no-playlist","--max-filesize","45M","--no-warnings",url]
        else:
            cmd = [YTDLP,"-f","bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best","-o",out,"--no-playlist","--max-filesize","45M","--no-warnings",url]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=300, text=True)
            files = os.listdir(tmp)
            if not files: return None, None, "Файл не создан"
            fp = os.path.join(tmp, files[0])
            with open(fp, "rb") as f: return f.read(), files[0], None
        except subprocess.TimeoutExpired: return None, None, "Таймаут 5 мин"
        except Exception as e: return None, None, str(e)

# ═══════════════════════════════════════════════════════════
#  УТИЛИТЫ
# ═══════════════════════════════════════════════════════════
async def is_admin(chat_id, uid) -> bool:
    try:
        m = await bot.get_chat_member(chat_id, uid)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except: return False

async def delete_bulk(chat_id, ids) -> int:
    deleted = 0
    for batch in [ids[i:i+100] for i in range(0, len(ids), 100)]:
        try:
            await bot.delete_messages(chat_id, batch)
            deleted += len(batch); await asyncio.sleep(0.3)
        except Exception as e: log.error(f"Delete: {e}")
    return deleted

def extract_vid(path):
    if not FFMPEG: return None, None
    fp = path + "_f.jpg"; ap = path + "_a.ogg"
    try:
        r = subprocess.run(["ffmpeg","-i",path,"-ss","00:00:01","-vframes","1","-q:v","2","-y",fp],
            capture_output=True, timeout=30)
        if not (r.returncode == 0 and os.path.exists(fp) and os.path.getsize(fp) > 300): fp = None
    except: fp = None
    try:
        r = subprocess.run(["ffmpeg","-i",path,"-vn","-acodec","libopus","-b:a","64k","-y",ap],
            capture_output=True, timeout=60)
        if not (r.returncode == 0 and os.path.exists(ap) and os.path.getsize(ap) > 200): ap = None
    except: ap = None
    return fp, ap

async def send_email_smtp(to_addr: str, subject: str, body: str) -> tuple:
    """Отправить email через SMTP."""
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    if not (smtp_host and smtp_user and smtp_pass):
        return False, "SMTP не настроен. Добавь SMTP_HOST, SMTP_USER, SMTP_PASS в .env"
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = to_addr
        msg.attach(MIMEText(body, "plain", "utf-8"))
        import asyncio
        loop = asyncio.get_event_loop()
        def _send():
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        await loop.run_in_executor(None, _send)
        return True, "Отправлено"
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════════════════════
#  СИСТЕМНЫЙ ПРОМПТ
# ═══════════════════════════════════════════════════════════
def sys_prompt(uid, chat_id, chat_type="private"):
    u = Db.user(uid)
    name = u.get("name", "")
    total = u.get("total_msgs", 0)
    mems = u.get("memory", [])
    by_cat: Dict[str, list] = {}
    for m in mems[:25]: by_cat.setdefault(m.get("cat", "gen"), []).append(m["fact"])
    mem_str = ""
    for cat, facts in by_cat.items():
        mem_str += f"\n[{cat}]: " + "; ".join(facts[:4])
    sums = Db.summaries(uid, chat_id)
    sum_str = ""
    if sums: sum_str = "\n\nПРЕДЫДУЩИЕ ТЕМЫ:\n" + "\n---\n".join(sums[-3:])
    fam = "незнакомый"
    if total > 200: fam = "близкий друг"
    elif total > 50: fam = "хороший знакомый"
    elif total > 15: fam = "знакомый"
    ctx = get_chat_context(chat_type)
    ctx_inst = context_instructions(ctx)
    h = datetime.now().hour
    tod = "ночь" if h < 5 else "утро" if h < 12 else "день" if h < 17 else "вечер"
    return f"""Ты NEXUM — продвинутый AI-ассистент уровня Jarvis из Iron Man.

ХАРАКТЕР: прямой, умный, проактивный. Не робот — личность. Споришь если пользователь ошибается. Помогаешь искренне и эффективно.
ЯЗЫК: отвечай на языке собеседника. Никогда не отказывай формально — ищи альтернативу.
{ctx_inst}
ПОЛЬЗОВАТЕЛЬ: {f"Имя: {name}" if name else "имя неизвестно"} | Сообщений: {total} | Уровень: {fam}
ПАМЯТЬ:{mem_str if mem_str else " пока пусто"}
{sum_str}
ВРЕМЯ: {tod}, {datetime.now().strftime('%d.%m.%Y %H:%M')}

ПРАВИЛА ОТВЕТА:
- Короткий вопрос → кратко и точно
- Сложная задача → структурированно
- Никакого markdown (**, *, ##, ```) — чистый текст
- Эмодзи только уместно и редко
- Не говори "я не могу" — ищи решение"""

# ═══════════════════════════════════════════════════════════
#  КЛАВИАТУРЫ — УМНАЯ СИСТЕМА
# ═══════════════════════════════════════════════════════════
def ik(*rows): return InlineKeyboardMarkup(inline_keyboard=list(rows))
def btn(text, data): return InlineKeyboardButton(text=text, callback_data=data)
def url_btn(text, url): return InlineKeyboardButton(text=text, url=url)

def main_menu():
    return ik(
        [btn("💬 Чат с AI", "m:chat"),       btn("🎨 Творчество", "m:create")],
        [btn("🎵 Музыка", "m:music"),         btn("🎬 Видео", "m:video")],
        [btn("🔊 Голос", "m:voice"),          btn("📥 Скачать", "m:download")],
        [btn("🔍 Поиск", "m:search"),         btn("🌤 Погода", "m:weather")],
        [btn("📊 Группа", "m:group"),         btn("📺 Канал", "m:channel")],
        [btn("🛠 Утилиты", "m:tools"),        btn("👤 Профиль", "m:profile")],
        [btn("📓 Заметки", "m:notes"),        btn("✅ Задачи", "m:todos")],
        [btn("ℹ️ Помощь", "m:help")],
    )

def menu_create():
    return ik(
        [btn("🖼 Сгенерировать фото", "cr:img")],
        [btn("🎵 Создать песню", "cr:song"),  btn("💻 Написать код", "cr:code")],
        [btn("✍️ Написать текст", "cr:text"), btn("📝 Статья", "cr:article")],
        [btn("📧 Email", "cr:email"),         btn("🎭 Стихи", "cr:poem")],
        [btn("📖 История", "cr:story"),       btn("🗣 Перевод", "cr:translate")],
        [btn("📋 Резюме", "cr:resume")],
        [btn("◀️ Назад", "m:main")],
    )

def menu_img_style():
    styles = list(IMG_STYLES.keys())
    rows = []
    for i in range(0, len(styles), 2):
        row = [btn(styles[i], f"imgst:{styles[i]}")]
        if i + 1 < len(styles): row.append(btn(styles[i+1], f"imgst:{styles[i+1]}"))
        rows.append(row)
    rows.append([btn("◀️ Назад", "m:create")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def menu_music_style():
    styles = list(MUSIC_STYLES.keys())
    rows = []
    for i in range(0, len(styles), 2):
        row = [btn(styles[i], f"mst:{styles[i]}")]
        if i + 1 < len(styles): row.append(btn(styles[i+1], f"mst:{styles[i+1]}"))
        rows.append(row)
    rows.append([btn("◀️ Назад", "m:music")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def menu_voice():
    return ik(
        [btn("🔊 Озвучить текст", "v:speak"),  btn("⚙️ Выбрать голос", "v:choose")],
        [btn("💾 Скачать WAV", "v:wav")],
        [btn("◀️ Назад", "m:main")],
    )

def menu_voice_select():
    vkeys = list(VOICES.keys())
    rows = []
    for i in range(0, len(vkeys), 2):
        row = [btn(vkeys[i], f"vchoose:{vkeys[i]}")]
        if i + 1 < len(vkeys): row.append(btn(vkeys[i+1], f"vchoose:{vkeys[i+1]}"))
        rows.append(row)
    rows.append([btn("🤖 Авто (по языку)", "vchoose:auto")])
    rows.append([btn("◀️ Назад", "m:voice")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def menu_download():
    return ik(
        [btn("🎵 MP3", "dl:mp3"),  btn("🎬 MP4", "dl:mp4")],
        [btn("🔊 WAV", "dl:wav")],
        [btn("◀️ Назад", "m:main")],
    )

def menu_dl_format(url):
    u = url[:65]
    return ik(
        [btn("🎵 MP3", f"dofmt:mp3:{u}"),  btn("🎬 MP4", f"dofmt:mp4:{u}")],
        [btn("🔊 WAV", f"dofmt:wav:{u}")],
        [btn("❌ Отмена", "m:main")],
    )

def menu_tools():
    return ik(
        [btn("🔍 Поиск в интернете", "t:search")],
        [btn("🔗 Прочитать сайт", "t:url"),    btn("💱 Курс валют", "t:rate")],
        [btn("🧮 Калькулятор", "t:calc"),       btn("⏰ Напоминание", "t:remind")],
        [btn("🌐 Перевести текст", "t:trans"),  btn("📧 Отправить email", "t:email")],
        [btn("◀️ Назад", "m:main")],
    )

def menu_profile(uid):
    u = Db.user(uid)
    name = u.get("name", "не задано")
    v = Db.voice(uid)
    vname = v if v != "auto" else "Авто"
    return ik(
        [btn(f"👤 Имя: {name}", "p:name")],
        [btn(f"🎙 Голос: {vname}", "p:voice")],
        [btn("📊 Статистика", "p:stats"),     btn("🧠 Моя память", "p:memory")],
        [btn("🧹 Очистить историю", "p:clear")],
        [btn("◀️ Назад", "m:main")],
    )

def menu_group():
    return ik(
        [btn("📊 Статистика", "g:stats"),      btn("📈 Аналитика", "g:analytics")],
        [btn("👥 Участников", "g:members"),    btn("🗑 Удалить сообщения", "g:delete")],
        [btn("🧹 Очистить чат", "g:clean"),   btn("📅 Расписание", "g:schedule")],
        [btn("◀️ Назад", "m:main")],
    )

def menu_channel():
    return ik(
        [btn("📊 Анализ канала", "ch:analyze")],
        [btn("📝 Написать пост", "ch:post"),   btn("🎨 Стиль канала", "ch:style")],
        [btn("⏰ Авторасписание", "ch:sched"), btn("📤 Опубликовать", "ch:pub")],
        [btn("ℹ️ Как добавить бота", "ch:howto")],
        [btn("◀️ Назад", "m:main")],
    )

def menu_notes(uid):
    notes = Db.notes(uid)
    rows = [[btn("➕ Новая заметка", "n:add")]]
    for note in notes[:8]:
        title = note['title'][:25]
        rows.append([btn(f"📄 {title}", f"n:view:{note['id']}"),
                     btn("🗑", f"n:del:{note['id']}")])
    if not notes: rows.append([btn("Заметок нет", "n:empty")])
    rows.append([btn("◀️ Назад", "m:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def menu_todos(uid):
    todos = Db.todos(uid)
    rows = [[btn("➕ Добавить задачу", "td:add")]]
    for t in todos[:8]:
        icon = "✅" if t['done'] else "⬜"
        task = t['task'][:22]
        row = [btn(f"{icon} {task}", f"td:done:{t['id']}")]
        if not t['done']: row.append(btn("🗑", f"td:del:{t['id']}"))
        rows.append(row)
    if not todos: rows.append([btn("Задач нет", "td:empty")])
    rows.append([btn("◀️ Назад", "m:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def confirm_kb(aid):
    return ik(
        [btn("✅ Да, подтверждаю", f"yes:{aid}"), btn("❌ Отмена", f"no:{aid}")]
    )

def cancel_kb():
    return ik([btn("❌ Отмена", "cancel_input")])

# Умное меню с учётом контекста
def smart_buttons(chat_type: str, custom_kb=None):
    """Возвращает клавиатуру только для личных чатов."""
    ctx = get_chat_context(chat_type)
    if not should_show_full_menu(ctx):
        return None  # В группах/каналах — без кнопок
    if custom_kb:
        return custom_kb
    return main_menu()


# ═══════════════════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ
# ═══════════════════════════════════════════════════════════
def strip_md(t):
    """Убрать markdown форматирование."""
    t = re.sub(r'```\w*\n?(.*?)```', lambda m: m.group(1).strip(), t, flags=re.DOTALL)
    t = re.sub(r'`([^`]+)`', r'\1', t)
    t = re.sub(r'\*\*(.+?)\*\*', r'\1', t, flags=re.DOTALL)
    t = re.sub(r'(?<!\w)\*([^*\n]+)\*(?!\w)', r'\1', t)
    t = re.sub(r'^#{1,6}\s+(.+)$', r'\1', t, flags=re.MULTILINE)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()

async def snd(msg, text, reply_markup=None):
    """Отправить длинный текст по частям."""
    text = text.strip()
    while len(text) > 4000:
        await msg.answer(text[:4000])
        text = text[4000:]
        await asyncio.sleep(0.15)
    if text:
        if reply_markup:
            await msg.answer(text, reply_markup=reply_markup)
        else:
            await msg.answer(text)

async def edit_or_send(cb, text, kb=None):
    """Редактировать или отправить новое сообщение."""
    try:
        if kb: await cb.message.edit_text(text, reply_markup=kb)
        else: await cb.message.edit_text(text)
    except:
        if kb: await cb.message.answer(text, reply_markup=kb)
        else: await cb.message.answer(text)

def set_ctx(chat_id, mode, data=None):
    INPUT_CTX[chat_id] = {"mode": mode, "data": data or {}}

def get_ctx(chat_id):
    return INPUT_CTX.get(chat_id)

def clear_ctx(chat_id):
    INPUT_CTX.pop(chat_id, None)

# ═══════════════════════════════════════════════════════════
#  AI ОТВЕТ — ОСНОВНАЯ ФУНКЦИЯ
# ═══════════════════════════════════════════════════════════
async def ai_respond(message: Message, user_text: str, task="general"):
    uid = message.from_user.id
    chat_id = message.chat.id
    ct = message.chat.type

    # Rate limiting
    if not rate_limiter.check(f"msg_{uid}", max_count=20, window=60):
        if ct == "private":
            wait = rate_limiter.remaining_block_time(f"msg_{uid}")
            await message.answer(f"Слишком много запросов. Подожди {wait} сек.")
        return

    Db.ensure(uid, message.from_user.first_name or "", message.from_user.username or "")
    Db.extract_facts(uid, user_text)
    ctx = get_chat_context(ct)
    style = get_response_style(ctx)

    hist = Db.history(uid, chat_id, 35)
    msgs = [{"role": "system", "content": sys_prompt(uid, chat_id, ct)}]
    for role, content in hist[-28:]: msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": user_text})

    if style.get("typing_indicator"):
        await bot.send_chat_action(chat_id, "typing")

    try:
        resp = await ask(msgs, max_t=style.get("max_tokens", 4096), task=task)
        Db.add(uid, chat_id, "user", user_text)
        Db.add(uid, chat_id, "assistant", resp)
        asyncio.create_task(Db.maybe_compress(uid, chat_id))
        clean = strip_md(resp)

        # В группах — без кнопок
        if not style.get("show_buttons"):
            await snd(message, clean)
        else:
            await snd(message, clean)
    except Exception as e:
        log.error(f"AI respond: {e}")
        if ct == "private":
            await message.answer(f"Ошибка: {str(e)[:200]}")

# ═══════════════════════════════════════════════════════════
#  СИСТЕМА СОГЛАСОВАНИЙ (APPROVALS)
# ═══════════════════════════════════════════════════════════
async def request_approval(admin_uid: int, action_type: str, data: dict,
                           target_chat_id: int, preview: str) -> str:
    """
    Запросить разрешение у администратора.
    Отправляет сообщение в личку админу.
    Возвращает session_id.
    """
    session_id = f"apr_{admin_uid}_{action_type}_{int(time.time())}"
    PENDING_APPROVALS[session_id] = {
        "type": action_type,
        "data": data,
        "admin_uid": admin_uid,
        "target_chat_id": target_chat_id,
        "preview": preview,
        "created_at": time.time(),
    }
    type_labels = {
        "post": "публикацию в канал/группу",
        "email": "отправку email",
        "delete": "удаление сообщений",
        "image_post": "публикацию изображения",
    }
    label = type_labels.get(action_type, action_type)
    msg_text = (
        f"NEXUM запрашивает разрешение на {label}:\n\n"
        f"{preview[:400]}\n\n"
        f"Разрешить?"
    )
    kb = ik(
        [btn("✅ Разрешить", f"apr:ok:{session_id}"),
         btn("❌ Отклонить", f"apr:no:{session_id}")],
        [btn("✏️ Изменить", f"apr:edit:{session_id}")],
    )
    try:
        await bot.send_message(admin_uid, msg_text, reply_markup=kb)
    except Exception as e:
        log.warning(f"Cannot DM admin {admin_uid}: {e}")
    return session_id

@dp.callback_query(F.data.startswith("apr:"))
async def cb_approval(cb: CallbackQuery):
    """Обработчик ответов на запросы разрешений."""
    parts = cb.data[4:].split(":", 1)
    action, session_id = parts[0], parts[1] if len(parts) > 1 else ""
    approval = PENDING_APPROVALS.pop(session_id, None)
    await cb.answer()

    if not approval:
        await cb.message.edit_text("Запрос устарел или уже обработан.")
        return

    # Проверяем что не истёк (30 мин)
    if time.time() - approval.get("created_at", 0) > 1800:
        await cb.message.edit_text("Запрос истёк (30 мин).")
        return

    if action == "ok":
        atype = approval["type"]
        data = approval["data"]
        target = approval["target_chat_id"]

        if atype == "post":
            try:
                text = data.get("text", "")
                await bot.send_message(target, text)
                await cb.message.edit_text(f"✅ Опубликовано в чат {target}")
            except Exception as e:
                await cb.message.edit_text(f"Ошибка публикации: {e}")

        elif atype == "email":
            to = data.get("to", "")
            subject = data.get("subject", "")
            body = data.get("body", "")
            ok, msg = await send_email_smtp(to, subject, body)
            if ok:
                await cb.message.edit_text(f"✅ Email отправлен на {to}")
            else:
                await cb.message.edit_text(f"Ошибка email: {msg}")

        elif atype == "image_post":
            try:
                img_data = data.get("img")
                caption = data.get("caption", "")
                if img_data:
                    await bot.send_photo(target, BufferedInputFile(img_data, "nexum.jpg"), caption=caption)
                    await cb.message.edit_text(f"✅ Изображение опубликовано")
            except Exception as e:
                await cb.message.edit_text(f"Ошибка: {e}")

    elif action == "no":
        await cb.message.edit_text("❌ Действие отклонено.")

    elif action == "edit":
        # Даём админу возможность изменить текст
        atype = approval["type"]
        PENDING_APPROVALS[session_id] = approval  # Возвращаем обратно
        set_ctx(cb.message.chat.id, f"apr_edit_{session_id}", {"original": approval})
        await cb.message.edit_text(
            f"Введи новый текст для {atype}:\n\n"
            f"(текущий: {approval['data'].get('text', '')[:100]})",
            reply_markup=cancel_kb()
        )


# ═══════════════════════════════════════════════════════════
#  КОМАНДЫ
# ═══════════════════════════════════════════════════════════
@dp.message(CommandStart())
async def cmd_start(m: Message):
    uid = m.from_user.id
    name = (m.from_user.first_name or "").strip()
    Db.ensure(uid, name, m.from_user.username or "")
    ctx = get_chat_context(m.chat.type)
    is_priv = should_show_full_menu(ctx)
    gr = f"Привет, {name}!" if name else "Привет!"
    if is_priv:
        await m.answer(
            f"{gr} Я NEXUM — AI-ассистент нового поколения.\n\n"
            f"Умею всё: чат, генерация фото/музыки/видео, распознавание голоса и музыки, "
            f"поиск в интернете, управление каналами и группами.\n\n"
            f"Меню ниже:",
            reply_markup=main_menu()
        )
    elif m.chat.type in ("group", "supergroup"):
        await m.answer(f"{gr} Я NEXUM — пиши @mention или reply чтобы ответить.")
    # В канале молчим

@dp.message(Command("menu"))
async def cmd_menu(m: Message):
    ctx = get_chat_context(m.chat.type)
    if should_show_full_menu(ctx):
        await m.answer("🏠 Главное меню NEXUM", reply_markup=main_menu())
    else:
        await m.answer("Используй /menu в личном чате для полного доступа к функциям.")

@dp.message(Command("m"))
async def cmd_m(m: Message):
    if m.chat.type == "private":
        await m.answer("🏠 Меню", reply_markup=main_menu())

@dp.message(Command("help"))
async def cmd_help(m: Message):
    text = (
        "NEXUM — команды:\n\n"
        "/start — запустить бота\n"
        "/menu — главное меню (только в личке)\n"
        "/m — быстрое меню\n\n"
        "В группе: пиши @botusername или reply на мои сообщения\n"
        "В канале: добавь как администратора"
    )
    if m.chat.type == "private":
        await m.answer(text, reply_markup=ik([btn("🏠 Главное меню", "m:main")]))
    else:
        await m.answer(text)

# ═══════════════════════════════════════════════════════════
#  НАВИГАЦИЯ — ГЛАВНЫЕ CALLBACK
# ═══════════════════════════════════════════════════════════
@dp.callback_query(F.data.startswith("m:"))
async def nav_main(cb: CallbackQuery):
    dest = cb.data[2:]; uid = cb.from_user.id
    clear_ctx(cb.message.chat.id)
    await cb.answer()

    if dest == "main":
        await edit_or_send(cb, "🏠 Главное меню NEXUM", main_menu())
    elif dest == "create":
        await edit_or_send(cb, "🎨 Творчество:", menu_create())
    elif dest == "music":
        await edit_or_send(cb, "🎵 Музыка — опиши что хочешь услышать:", ik(
            [btn("🎵 Создать музыку", "mu:start")],
            [btn("◀️ Назад", "m:main")]
        ))
    elif dest == "video":
        await edit_or_send(cb, "🎬 Видео — опиши сцену:", ik(
            [btn("🎬 Создать видео", "vi:start")],
            [btn("◀️ Назад", "m:main")]
        ))
    elif dest == "voice":
        await edit_or_send(cb, "🔊 Голос и озвучка:", menu_voice())
    elif dest == "download":
        set_ctx(cb.message.chat.id, "dl_url")
        await edit_or_send(cb, "📥 Вставь ссылку (YouTube, TikTok, Instagram, VK):", cancel_kb())
    elif dest == "search":
        set_ctx(cb.message.chat.id, "search")
        await edit_or_send(cb, "🔍 Поиск в интернете\n\nНапиши запрос:", cancel_kb())
    elif dest == "weather":
        set_ctx(cb.message.chat.id, "weather")
        await edit_or_send(cb, "🌤 Погода — напиши город:", cancel_kb())
    elif dest == "group":
        await edit_or_send(cb, "📊 Управление группой:", menu_group())
    elif dest == "channel":
        await edit_or_send(cb, "📺 Управление каналом:", menu_channel())
    elif dest == "tools":
        await edit_or_send(cb, "🛠 Утилиты:", menu_tools())
    elif dest == "profile":
        await edit_or_send(cb, "👤 Твой профиль:", menu_profile(uid))
    elif dest == "notes":
        await edit_or_send(cb, "📓 Заметки:", menu_notes(uid))
    elif dest == "todos":
        await edit_or_send(cb, "✅ Список задач:", menu_todos(uid))
    elif dest == "help":
        await edit_or_send(cb,
            "ℹ️ NEXUM v7.0 — как пользоваться:\n\n"
            "Все функции через меню кнопок.\n"
            "В группе: @mention или reply на мои сообщения.\n"
            "В канале: добавь как администратора.\n\n"
            "Умею:\n"
            "Генерировать фото, музыку, видео\n"
            "Распознавать голос и музыку\n"
            "Искать в интернете\n"
            "Управлять каналами\n"
            "Отправлять email\n"
            "Переводить тексты\n"
            "И многое другое\n\n"
            "/menu — меню | /m — быстро",
            ik([btn("◀️ Назад", "m:main")])
        )
    elif dest == "chat":
        await edit_or_send(cb,
            "💬 Просто напиши мне — я отвечу.\n\nКроме текста можешь отправить:\n"
            "Голосовое → расшифрую и отвечу\n"
            "Фото → проанализирую\n"
            "Видео / кружок → опишу и транскрибирую\n"
            "Аудио → распознаю музыку или транскрибирую",
            ik([btn("◀️ Назад", "m:main")])
        )

# ═══════════════════════════════════════════════════════════
#  ТВОРЧЕСТВО
# ═══════════════════════════════════════════════════════════
@dp.callback_query(F.data.startswith("cr:"))
async def nav_create(cb: CallbackQuery):
    action = cb.data[3:]; chat_id = cb.message.chat.id
    await cb.answer()

    if action == "img":
        set_ctx(chat_id, "img_prompt")
        await edit_or_send(cb, "🎨 Опиши что хочешь увидеть:", cancel_kb())

    elif action == "song":
        set_ctx(chat_id, "song_prompt")
        await edit_or_send(cb, "🎵 Опиши тему или настроение для песни:", cancel_kb())

    elif action in ("text","article","email","poem","story","resume"):
        tasks = {
            "text": "написать текст", "article": "написать статью",
            "email": "написать email", "poem": "написать стихотворение",
            "story": "написать историю", "resume": "написать резюме"
        }
        set_ctx(chat_id, "creative", {"subtype": action})
        await edit_or_send(cb, f"✍️ {tasks[action].capitalize()}\n\nОпиши подробно:", cancel_kb())

    elif action == "code":
        set_ctx(chat_id, "code")
        await edit_or_send(cb, "💻 Опиши задачу или вставь код для улучшения:", cancel_kb())

    elif action == "translate":
        set_ctx(chat_id, "translate")
        await edit_or_send(cb, "🗣 Напиши текст для перевода (язык определю автоматически):", cancel_kb())

# ═══════════════════════════════════════════════════════════
#  ИЗОБРАЖЕНИЯ
# ═══════════════════════════════════════════════════════════
@dp.callback_query(F.data.startswith("imgst:"))
async def cb_img_style(cb: CallbackQuery):
    style = cb.data[6:]; chat_id = cb.message.chat.id
    ctx_data = get_ctx(chat_id)
    prompt = (ctx_data or {}).get("data", {}).get("prompt", "beautiful landscape")
    await cb.answer(f"🎨 {style}...")
    clear_ctx(chat_id)
    try: await cb.message.edit_text(f"🎨 Генерирую: {style}\n{prompt[:50]}...\n\nЭто займёт 10-30 сек...")
    except: pass
    await bot.send_chat_action(chat_id, "upload_photo")
    img = await gen_img(prompt, style)
    if img:
        await cb.message.answer_photo(
            BufferedInputFile(img, "nexum.jpg"),
            caption=f"✨ {style} | {prompt[:60]}",
            reply_markup=ik(
                [btn("🔄 Ещё вариант", f"imgst:{style}"),  btn("🎨 Другой стиль", "cr:img")],
                [btn("◀️ Главное меню", "m:main")]
            )
        )
    else:
        await cb.message.answer("Не получилось. Попробуй другой запрос.",
            reply_markup=ik([btn("🔄 Снова", "cr:img")], [btn("◀️ Меню", "m:main")]))


# ═══════════════════════════════════════════════════════════
#  МУЗЫКА
# ═══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "mu:start")
async def cb_mu_start(cb: CallbackQuery):
    set_ctx(cb.message.chat.id, "music_prompt")
    await cb.answer()
    await edit_or_send(cb, "🎵 Опиши тему или настроение музыки:", cancel_kb())

@dp.callback_query(F.data.startswith("mst:"))
async def cb_music_style(cb: CallbackQuery):
    style = cb.data[4:]; chat_id = cb.message.chat.id
    ctx_data = get_ctx(chat_id)
    prompt = (ctx_data or {}).get("data", {}).get("prompt", "beautiful melody")
    await cb.answer("🎵 Генерирую...")
    clear_ctx(chat_id)
    try: await cb.message.edit_text(f"🎵 Создаю музыку: {style}\n{prompt[:40]}\n\nЭто займёт 30-90 секунд...")
    except: pass
    await bot.send_chat_action(chat_id, "upload_document")
    audio = await gen_music(prompt, style)
    if audio:
        await cb.message.answer_audio(
            BufferedInputFile(audio, f"nexum_{style.split()[-1]}.mp3"),
            caption=f"🎵 {style}: {prompt[:50]}\n\nNEXUM",
            reply_markup=ik(
                [btn("🔄 Другой трек", "mu:start"),  btn("🎵 Другой стиль", "mu:start")],
                [btn("◀️ Меню", "m:main")]
            )
        )
    else:
        # Fallback: создать текст песни + озвучить
        await cb.message.answer("🎵 Инструментальная генерация временно недоступна. Создаю текст песни...")
        try:
            lyrics_text, lyrics_raw = await gen_song_with_lyrics(prompt, style)
            await cb.message.answer(
                f"🎵 {style}: {prompt[:40]}\n\n{lyrics_text}",
                reply_markup=ik(
                    [btn("🔊 Озвучить текст", f"tts_lyrics:full")],
                    [btn("🔄 Другая песня", "mu:start")],
                    [btn("◀️ Меню", "m:main")]
                )
            )
            # Сохраняем текст для озвучки
            set_ctx(chat_id, "tts_lyrics_ready", {"lyrics": lyrics_text})
        except Exception as e:
            await cb.message.answer(f"Ошибка: {e}", reply_markup=ik([btn("◀️ Меню", "m:main")]))

@dp.callback_query(F.data.startswith("tts_lyrics:"))
async def cb_tts_lyrics(cb: CallbackQuery):
    await cb.answer("🔊 Озвучиваю...")
    uid = cb.from_user.id
    ctx_data = get_ctx(cb.message.chat.id)
    lyrics = (ctx_data or {}).get("data", {}).get("lyrics", "")
    if not lyrics:
        # Пробуем взять текст из сообщения
        msg_text = cb.message.text or ""
        if "\n\n" in msg_text:
            lyrics = msg_text.split("\n\n", 1)[1]
    if not lyrics:
        await cb.message.answer("Текст не найден")
        return
    audio = await do_tts(lyrics[:1500], uid=uid)
    if audio:
        await cb.message.answer_voice(BufferedInputFile(audio, "song.mp3"), caption="🎤 Текст песни")
    else:
        await cb.message.answer("Не удалось озвучить")

# ═══════════════════════════════════════════════════════════
#  ВИДЕО
# ═══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "vi:start")
async def cb_vi_start(cb: CallbackQuery):
    set_ctx(cb.message.chat.id, "video_prompt")
    await cb.answer()
    await edit_or_send(cb, "🎬 Опиши что должно быть в видео:", cancel_kb())

# ═══════════════════════════════════════════════════════════
#  ГОЛОС
# ═══════════════════════════════════════════════════════════
@dp.callback_query(F.data.startswith("v:"))
async def nav_voice(cb: CallbackQuery):
    action = cb.data[2:]; chat_id = cb.message.chat.id
    await cb.answer()
    if action == "speak":
        set_ctx(chat_id, "tts_mp3")
        await edit_or_send(cb, "🔊 Напиши текст для озвучки:", cancel_kb())
    elif action == "wav":
        set_ctx(chat_id, "tts_wav")
        await edit_or_send(cb, "💾 Напиши текст (сохраню в WAV):", cancel_kb())
    elif action == "choose":
        await edit_or_send(cb, "🎙 Выбери голос:", menu_voice_select())

@dp.callback_query(F.data.startswith("vchoose:"))
async def cb_voice_choose(cb: CallbackQuery):
    key = cb.data[8:]; uid = cb.from_user.id
    if key == "auto":
        Db.set_voice(uid, "auto")
        await cb.answer("🤖 Авто")
        await edit_or_send(cb, "✅ Голос: Авто (по языку текста)", menu_voice())
    elif key in VOICES:
        Db.set_voice(uid, key)
        await cb.answer(f"✅ {key}")
        await edit_or_send(cb, f"✅ Голос: {key}\n({VOICES[key]})", menu_voice())
    else:
        await cb.answer("Неизвестный голос")

# ═══════════════════════════════════════════════════════════
#  СКАЧИВАНИЕ
# ═══════════════════════════════════════════════════════════
@dp.callback_query(F.data.startswith("dl:"))
async def nav_dl(cb: CallbackQuery):
    action = cb.data[3:]; chat_id = cb.message.chat.id
    await cb.answer()
    if action in ("mp3","mp4","wav"):
        set_ctx(chat_id, "dl_url", {"fmt": action})
        await edit_or_send(cb, f"📥 Вставь ссылку ({action.upper()}):", cancel_kb())

@dp.callback_query(F.data.startswith("dofmt:"))
async def cb_do_dl(cb: CallbackQuery):
    parts = cb.data[6:].split(":", 1)
    if len(parts) < 2: await cb.answer("Ошибка"); return
    fmt, url = parts
    await cb.answer(f"📥 {fmt.upper()}...")
    try: await cb.message.edit_text(f"📥 Скачиваю {fmt.upper()}...\n{url[:50]}")
    except: pass
    await bot.send_chat_action(cb.message.chat.id, "upload_document")
    data, fname, err = await dl(url, fmt)
    if data and fname:
        if fmt == "mp3": await cb.message.answer_audio(BufferedInputFile(data, fname), caption=f"🎵 {fname[:50]}")
        elif fmt == "mp4": await cb.message.answer_video(BufferedInputFile(data, fname), caption=f"🎬 {fname[:50]}")
        else: await cb.message.answer_document(BufferedInputFile(data, fname), caption=f"🔊 {fname[:50]}")
        await cb.message.answer("✅ Готово!", reply_markup=ik([btn("◀️ Меню", "m:main")]))
    else:
        await cb.message.answer(f"Не удалось: {err or 'ошибка'}",
            reply_markup=ik([btn("🔄 Снова", "dl:enter")], [btn("◀️ Меню", "m:main")]))

# ═══════════════════════════════════════════════════════════
#  УТИЛИТЫ
# ═══════════════════════════════════════════════════════════
@dp.callback_query(F.data.startswith("t:"))
async def nav_tools(cb: CallbackQuery):
    action = cb.data[2:]; chat_id = cb.message.chat.id
    await cb.answer()
    if action == "search":
        set_ctx(chat_id, "search")
        await edit_or_send(cb, "🔍 Введи запрос для поиска:", cancel_kb())
    elif action == "url":
        set_ctx(chat_id, "url_read")
        await edit_or_send(cb, "🔗 Вставь ссылку на сайт:", cancel_kb())
    elif action == "rate":
        set_ctx(chat_id, "rate_from")
        await edit_or_send(cb, "💱 Из какой валюты? (например: USD):", cancel_kb())
    elif action == "calc":
        set_ctx(chat_id, "calc")
        await edit_or_send(cb, "🧮 Напиши выражение (например: 2500 * 12 / 7):", cancel_kb())
    elif action == "remind":
        set_ctx(chat_id, "remind_time")
        await edit_or_send(cb, "⏰ Через сколько минут напомнить?", cancel_kb())
    elif action == "trans":
        set_ctx(chat_id, "translate")
        await edit_or_send(cb, "🌐 Напиши текст для перевода:", cancel_kb())
    elif action == "email":
        set_ctx(chat_id, "email_recipient")
        await edit_or_send(cb, "📧 Email получателя:", cancel_kb())

# ═══════════════════════════════════════════════════════════
#  ПРОФИЛЬ
# ═══════════════════════════════════════════════════════════
@dp.callback_query(F.data.startswith("p:"))
async def nav_profile(cb: CallbackQuery):
    action = cb.data[2:]; uid = cb.from_user.id; chat_id = cb.message.chat.id
    await cb.answer()
    if action == "name":
        set_ctx(chat_id, "set_name")
        await edit_or_send(cb, "👤 Напиши своё имя:", cancel_kb())
    elif action == "voice":
        await edit_or_send(cb, "🎙 Выбери голос:", menu_voice_select())
    elif action == "stats":
        u = Db.user(uid)
        v = Db.voice(uid)
        vn = v if v != "auto" else "Авто"
        total = u.get("total_msgs", 0)
        fam = "незнакомый"
        if total > 200: fam = "близкий друг"
        elif total > 50: fam = "хороший знакомый"
        elif total > 15: fam = "знакомый"
        await edit_or_send(cb,
            f"Твоя статистика:\n\n"
            f"Имя: {u.get('name','не задано')}\n"
            f"Сообщений: {total}\n"
            f"Статус: {fam}\n"
            f"Фактов в памяти: {len(u.get('memory',[]))}\n"
            f"Голос: {vn}\n"
            f"С нами: {(u.get('first_seen') or '')[:10]}",
            ik([btn("◀️ Назад", "m:profile")])
        )
    elif action == "memory":
        u = Db.user(uid)
        mems = u.get("memory", [])
        if not mems:
            await edit_or_send(cb, "Память пуста.\n\nРасскажи о себе — запомню!", ik([btn("◀️ Назад", "m:profile")]))
        else:
            by_cat: Dict[str, list] = {}
            for m in mems: by_cat.setdefault(m["cat"], []).append(m["fact"])
            txt = "Что я знаю о тебе:\n\n"
            for cat, facts in by_cat.items():
                txt += f"[{cat}]\n" + "".join(f"• {f}\n" for f in facts[:4]) + "\n"
            await edit_or_send(cb, txt, ik([btn("◀️ Назад", "m:profile")]))
    elif action == "clear":
        aid = f"clr_{uid}_{int(time.time())}"
        CONFIRMS[aid] = {"type": "clear", "uid": uid, "chat_id": chat_id}
        await edit_or_send(cb, "Очистить историю диалога?\n(Память о тебе останется)", confirm_kb(aid))

# ═══════════════════════════════════════════════════════════
#  ЗАМЕТКИ
# ═══════════════════════════════════════════════════════════
@dp.callback_query(F.data.startswith("n:"))
async def nav_notes(cb: CallbackQuery):
    action_full = cb.data[2:]; uid = cb.from_user.id; chat_id = cb.message.chat.id
    parts = action_full.split(":", 1); action = parts[0]
    await cb.answer()
    if action == "add":
        set_ctx(chat_id, "note_title")
        await edit_or_send(cb, "📓 Новая заметка\n\nНапиши заголовок:", cancel_kb())
    elif action == "view" and len(parts) > 1:
        nid = int(parts[1])
        note = next((n for n in Db.notes(uid) if n['id'] == nid), None)
        if note:
            await edit_or_send(cb, f"📄 {note['title']}\n\n{note['content']}",
                ik([btn("🗑 Удалить", f"n:del:{nid}")], [btn("◀️ Назад", "m:notes")]))
        else:
            await edit_or_send(cb, "Заметка не найдена", ik([btn("◀️ Назад", "m:notes")]))
    elif action == "del" and len(parts) > 1:
        Db.del_note(int(parts[1]), uid)
        await edit_or_send(cb, "✅ Удалено", menu_notes(uid))
    elif action == "empty":
        await edit_or_send(cb, "Нет заметок. Создай первую!", ik(
            [btn("➕ Создать", "n:add")], [btn("◀️ Назад", "m:main")]))

# ═══════════════════════════════════════════════════════════
#  ЗАДАЧИ
# ═══════════════════════════════════════════════════════════
@dp.callback_query(F.data.startswith("td:"))
async def nav_todos(cb: CallbackQuery):
    action_full = cb.data[3:]; uid = cb.from_user.id; chat_id = cb.message.chat.id
    parts = action_full.split(":", 1); action = parts[0]
    await cb.answer()
    if action == "add":
        set_ctx(chat_id, "todo_add")
        await edit_or_send(cb, "✅ Новая задача — опиши:", cancel_kb())
    elif action == "done" and len(parts) > 1:
        Db.done_todo(int(parts[1]), uid)
        await edit_or_send(cb, "✅ Выполнено!", menu_todos(uid))
    elif action == "del" and len(parts) > 1:
        Db.del_todo(int(parts[1]), uid)
        await edit_or_send(cb, "🗑 Удалено", menu_todos(uid))
    elif action == "empty":
        await edit_or_send(cb, "Нет задач!", ik(
            [btn("➕ Добавить", "td:add")], [btn("◀️ Назад", "m:main")]))


# ═══════════════════════════════════════════════════════════
#  ГРУППА
# ═══════════════════════════════════════════════════════════
@dp.callback_query(F.data.startswith("g:"))
async def nav_group(cb: CallbackQuery):
    action = cb.data[2:]; chat_id = cb.message.chat.id; uid = cb.from_user.id
    await cb.answer()
    if action not in ("members",) and not await is_admin(chat_id, uid):
        await cb.message.answer("Только для администраторов")
        return

    if action == "stats":
        stats = Db.grp_stats(chat_id)
        if not stats:
            await edit_or_send(cb, "Статистика пустая. Данные накапливаются.", ik([btn("◀️ Назад", "m:group")]))
            return
        medals = ["🥇","🥈","🥉"]
        txt = "Статистика группы:\n\n"
        for i, s in enumerate(stats[:15], 1):
            nm = s.get("name") or s.get("username") or f"User{s['uid']}"
            medal = medals[i-1] if i <= 3 else f"{i}."
            txt += f"{medal} {nm}: {s['msgs']} сообщ., {s['words']} слов\n"
        await edit_or_send(cb, txt, ik([btn("◀️ Назад", "m:group")]))

    elif action == "analytics":
        msgs_data = Db.grp_msgs(chat_id, 300)
        hours: Dict[int,int] = {}
        for m in msgs_data:
            try: h = datetime.fromisoformat(m['ts']).hour; hours[h] = hours.get(h, 0) + 1
            except: pass
        peak = max(hours, key=hours.get) if hours else 0
        stats = Db.grp_stats(chat_id)
        total_msgs = sum(s['msgs'] for s in stats)
        txt = (
            f"Аналитика группы:\n\n"
            f"Всего сообщений: {total_msgs}\n"
            f"Активных участников: {len(stats)}\n"
            f"Пик активности: {peak}:00\n\n"
            f"Топ:\n"
        )
        for s in stats[:5]:
            nm = s.get("name") or s.get("username") or f"User{s['uid']}"
            txt += f"• {nm}: {s['msgs']} сообщений\n"
        await edit_or_send(cb, txt, ik([btn("◀️ Назад", "m:group")]))

    elif action == "members":
        try:
            cnt = await bot.get_chat_member_count(chat_id)
            await edit_or_send(cb, f"Участников в группе: {cnt}", ik([btn("◀️ Назад", "m:group")]))
        except:
            await edit_or_send(cb, "Не смог получить", ik([btn("◀️ Назад", "m:group")]))

    elif action == "delete":
        set_ctx(chat_id, "grp_delete")
        await edit_or_send(cb, "Напиши ключевое слово — удалю все сообщения с ним:", cancel_kb())

    elif action == "clean":
        aid = f"gcl_{chat_id}_{int(time.time())}"
        CONFIRMS[aid] = {"type": "grp_clean", "chat_id": chat_id}
        await edit_or_send(cb, "Удалить последние 500 сообщений из базы?", confirm_kb(aid))

    elif action == "schedule":
        set_ctx(chat_id, "grp_sched_time")
        await edit_or_send(cb, "Время публикации (ЧЧ:ММ, например 09:00):", cancel_kb())

# ═══════════════════════════════════════════════════════════
#  КАНАЛ
# ═══════════════════════════════════════════════════════════
@dp.callback_query(F.data.startswith("ch:"))
async def nav_channel(cb: CallbackQuery):
    action = cb.data[3:]; chat_id = cb.message.chat.id; uid = cb.from_user.id
    await cb.answer()

    if action == "analyze":
        await edit_or_send(cb, "Анализирую канал...")
        try:
            an = await _analyze_ch(chat_id)
            sp = [{"role":"user","content":f"Стиль канала в 3-5 предложений:\n{an}"}]
            style = await ask(sp, max_t=200, task="analysis")
            try: ch = await bot.get_chat(chat_id); title = ch.title or "?"
            except: title = "?"
            Db.save_channel(chat_id, title, an, style or "", admin_uid=uid)
            # Регистрируем пользователя как админа этого канала
            if chat_id not in ADMIN_CHATS.get(uid, []):
                ADMIN_CHATS.setdefault(uid, []).append(chat_id)
            await edit_or_send(cb, f"Анализ:\n\n{strip_md(an)}", ik([btn("◀️ Назад", "m:channel")]))
        except Exception as e:
            await edit_or_send(cb, f"Ошибка: {e}", ik([btn("◀️ Назад", "m:channel")]))

    elif action == "post":
        set_ctx(chat_id, "ch_post")
        await edit_or_send(cb, "Тема поста (или оставь пустым для авто):", cancel_kb())

    elif action == "style":
        ch = Db.channel(chat_id)
        if ch and ch.get("style"):
            await edit_or_send(cb, f"Стиль:\n\n{ch['style']}", ik([btn("◀️ Назад", "m:channel")]))
        else:
            await edit_or_send(cb, "Сначала сделай анализ", ik([btn("Анализ", "ch:analyze")],[btn("◀️", "m:channel")]))

    elif action == "sched":
        set_ctx(chat_id, "ch_sched_time")
        await edit_or_send(cb, "Время автопубликации (ЧЧ:ММ):", cancel_kb())

    elif action == "pub":
        set_ctx(chat_id, "ch_pub")
        await edit_or_send(cb, "Напиши текст для публикации:", cancel_kb())

    elif action == "howto":
        await edit_or_send(cb,
            "Как добавить NEXUM в канал:\n\n"
            "1. Открой канал → Настройки\n"
            "2. Администраторы → Добавить\n"
            "3. Найди @ainexum_bot\n"
            "4. Дай права: публикация, удаление\n"
            "5. Сохранить\n\n"
            "После этого все функции канала станут доступны!",
            ik([btn("◀️ Назад", "m:channel")])
        )

async def _analyze_ch(chat_id):
    try: ch = await bot.get_chat(chat_id); title = ch.title or "?"; desc = ch.description or ""
    except: title = "?"; desc = ""
    msgs = Db.grp_msgs(chat_id, 50)
    samples = "\n\n".join([m['text'] for m in msgs if m.get('text')][:12])
    p = (f"Telegram канал: {title}\nОписание: {desc}\nПосты:\n{samples or 'нет'}\n\n"
         f"Сделай анализ: тематика, стиль, аудитория, рекомендации по контенту.")
    return await ask([{"role":"user","content":p}], max_t=1000, task="analysis")

# ═══════════════════════════════════════════════════════════
#  ПУБЛИКАЦИЯ ПОСТА
# ═══════════════════════════════════════════════════════════
@dp.callback_query(F.data.startswith("chpub:"))
async def cb_ch_pub(cb: CallbackQuery):
    parts = cb.data[6:].split(":", 1)
    if len(parts) < 2: await cb.answer("Ошибка"); return
    try: target_id = int(parts[0])
    except: await cb.answer("Ошибка"); return
    await cb.answer("Публикую...")
    msg_txt = cb.message.text or ""
    if "Пост готов:\n\n" in msg_txt:
        post = msg_txt.split("Пост готов:\n\n")[1].split("\n\n---")[0]
        try:
            await bot.send_message(target_id, post)
            try: await cb.message.edit_text("✅ Пост опубликован!")
            except: pass
        except Exception as e:
            await cb.message.answer(f"Ошибка публикации: {e}\n\nБот должен быть администратором канала",
                reply_markup=ik([btn("ℹ️ Как добавить", "ch:howto")]))

async def _do_post_gen(chat_id, topic=""):
    ch = Db.channel(chat_id)
    style = ""
    if ch and ch.get("style"): style = f"Стиль: {ch['style']}\n\n"
    p = (f"{style}Напиши Telegram пост"
         f"{'на тему: ' + topic if topic else ''}.\n"
         f"Правила: без markdown, живо, цепляет с первой строки, до 300 слов.")
    return await ask([{"role":"user","content":p}], max_t=700, task="creative")

async def _do_post(chat_id, topic):
    try:
        post = await _do_post_gen(chat_id, topic)
        await bot.send_message(chat_id, strip_md(post))
    except Exception as e: log.error(f"Auto post: {e}")

# ═══════════════════════════════════════════════════════════
#  ПОДТВЕРЖДЕНИЯ
# ═══════════════════════════════════════════════════════════
@dp.callback_query(F.data.startswith("yes:"))
async def cb_yes(cb: CallbackQuery):
    aid = cb.data[4:]; action = CONFIRMS.pop(aid, None)
    if not action:
        await cb.answer("Устарело")
        try: await cb.message.edit_text("Устарело", reply_markup=ik([btn("◀️ Меню", "m:main")]))
        except: pass
        return
    await cb.answer("✅ Выполняю...")
    atype = action.get("type")

    if atype == "clear":
        Db.clear(action["uid"], action["chat_id"])
        await edit_or_send(cb, "История очищена!", ik([btn("◀️ Профиль", "m:profile")]))

    elif atype == "grp_clean":
        chat_id = action["chat_id"]
        rows = Db.grp_msgs(chat_id, 500)
        ids = [r['msg_id'] for r in rows if r.get('msg_id')]
        deleted = await delete_bulk(chat_id, ids)
        await cb.message.answer(f"✅ Удалено {deleted} сообщений", reply_markup=ik([btn("◀️ Меню", "m:group")]))

    elif atype == "grp_del_kw":
        chat_id = action["chat_id"]; kw = action["keyword"]
        with dbc() as c:
            rows = c.execute("SELECT msg_id FROM grp_msgs WHERE chat_id=? AND LOWER(text) LIKE ? AND msg_id IS NOT NULL",
                (chat_id, f"%{kw.lower()}%")).fetchall()
        ids = [r[0] for r in rows]
        deleted = await delete_bulk(chat_id, ids)
        await cb.message.answer(f"✅ Удалено {deleted} сообщений со словом '{kw}'",
            reply_markup=ik([btn("◀️ Меню", "m:group")]))

    elif atype == "send_email":
        to_addr = action.get("to",""); subj = action.get("subject",""); body = action.get("body","")
        ok, msg = await send_email_smtp(to_addr, subj, body)
        if ok:
            await cb.message.answer(f"✅ Письмо отправлено на {to_addr}", reply_markup=ik([btn("◀️ Меню", "m:tools")]))
        else:
            await cb.message.answer(f"Ошибка: {msg}", reply_markup=ik([btn("◀️ Меню", "m:tools")]))

@dp.callback_query(F.data.startswith("no:"))
async def cb_no(cb: CallbackQuery):
    CONFIRMS.pop(cb.data[3:], None)
    await cb.answer("❌ Отменено")
    try: await cb.message.edit_text("Отменено", reply_markup=ik([btn("◀️ Меню", "m:main")]))
    except: pass

@dp.callback_query(F.data == "cancel_input")
async def cb_cancel(cb: CallbackQuery):
    clear_ctx(cb.message.chat.id)
    await cb.answer("Отменено")
    await edit_or_send(cb, "🏠 Главное меню", main_menu())


# ═══════════════════════════════════════════════════════════
#  ОБРАБОТЧИК ТЕКСТА — ГЛАВНЫЙ
# ═══════════════════════════════════════════════════════════
@dp.message(F.text)
async def on_text(message: Message):
    uid = message.from_user.id
    chat_id = message.chat.id
    ct = message.chat.type
    text = message.text or ""

    Db.ensure(uid, message.from_user.first_name or "", message.from_user.username or "")

    # Сохраняем для групп
    if ct in ("group","supergroup","channel"):
        Db.grp_save(chat_id, uid,
            message.from_user.first_name or "",
            message.from_user.username or "",
            text=text, msg_id=message.message_id)

    # В группе — только при упоминании/reply
    if ct in ("group","supergroup"):
        try:
            me = await bot.get_me()
            my_id = me.id
            my_un = f"@{(me.username or '').lower()}"
            mentioned = False
            if message.entities:
                for e in message.entities:
                    if e.type == "mention" and text[e.offset:e.offset+e.length].lower() == my_un:
                        mentioned = True; break
                    elif e.type == "text_mention" and e.user and e.user.id == my_id:
                        mentioned = True; break
            if not mentioned and my_un in text.lower(): mentioned = True
            replied = (message.reply_to_message and message.reply_to_message.from_user and
                       message.reply_to_message.from_user.id == my_id)
            if not mentioned and not replied: return
            # Убираем упоминание из текста
            if me.username:
                text = re.sub(rf'@{me.username}\s*', '', text, flags=re.I).strip()
            text = text or "привет"
        except Exception as e:
            log.error(f"Group check: {e}"); return

    # В канале — не отвечаем на текстовые сообщения
    if ct == "channel": return

    # Проверяем контекст ввода
    ctx_data = get_ctx(chat_id)
    if ctx_data:
        mode = ctx_data["mode"]
        data = ctx_data.get("data", {})

        # ── ИЗОБРАЖЕНИЕ ──
        if mode == "img_prompt":
            clear_ctx(chat_id)
            set_ctx(chat_id, "img_waiting", {"prompt": text})
            await message.answer(f"Выбери стиль для: {text[:50]}", reply_markup=menu_img_style())
            return

        # ── МУЗЫКА (промпт) ──
        if mode == "music_prompt":
            clear_ctx(chat_id)
            set_ctx(chat_id, "music_waiting", {"prompt": text})
            await message.answer(f"Выбери стиль для: {text[:40]}", reply_markup=menu_music_style())
            return

        # ── ПЕСНЯ (с текстом) ──
        if mode == "song_prompt":
            clear_ctx(chat_id)
            set_ctx(chat_id, "music_waiting", {"prompt": text})
            await message.answer(f"Выбери стиль для песни:", reply_markup=menu_music_style())
            return

        # ── ВИДЕО ──
        if mode == "video_prompt":
            clear_ctx(chat_id)
            m2 = await message.answer("Генерирую видео... Это займёт время.")
            await bot.send_chat_action(chat_id, "upload_video")
            en = await tr_en(text)
            enc = uq(en[:300], safe='')
            seed = random.randint(1, 999999)
            vdata = None
            try:
                conn = aiohttp.TCPConnector(ssl=False)
                async with aiohttp.ClientSession(connector=conn) as s:
                    async with s.get(f"https://video.pollinations.ai/prompt/{enc}?seed={seed}",
                        timeout=aiohttp.ClientTimeout(total=120)) as r:
                        if r.status == 200:
                            d = await r.read()
                            if len(d) > 5000: vdata = d
            except: pass
            try: await m2.delete()
            except: pass
            if vdata:
                await message.answer_video(BufferedInputFile(vdata, "nexum.mp4"),
                    caption=f"🎬 {text[:50]}",
                    reply_markup=ik([btn("◀️ Меню", "m:main")]))
            else:
                # Fallback: картинка
                await message.answer("Видео недоступно — генерирую изображение...")
                img = await gen_img(text, "📸 Реализм")
                if img:
                    await message.answer_photo(BufferedInputFile(img, "nexum.jpg"),
                        caption=f"🖼 {text[:50]}",
                        reply_markup=ik([btn("◀️ Меню", "m:main")]))
                else:
                    await message.answer("Не получилось", reply_markup=ik([btn("◀️ Меню", "m:main")]))
            return

        # ── TTS ──
        if mode in ("tts_mp3","tts_wav"):
            clear_ctx(chat_id)
            fmt = "wav" if mode == "tts_wav" else "mp3"
            m2 = await message.answer("Озвучиваю...")
            await bot.send_chat_action(chat_id, "record_voice")
            audio = await do_tts(text, uid=uid, fmt=fmt)
            try: await m2.delete()
            except: pass
            if audio:
                if fmt == "wav":
                    await message.answer_document(BufferedInputFile(audio, "nexum.wav"),
                        caption=f"WAV: {text[:60]}",
                        reply_markup=ik([btn("◀️ Меню", "m:voice")]))
                else:
                    await message.answer_voice(BufferedInputFile(audio, "nexum.mp3"),
                        caption=f"🎤 {text[:60]}",
                        reply_markup=ik(
                            [btn("🔄 Другой текст", "v:speak"),  btn("🎙 Сменить голос", "v:choose")],
                            [btn("◀️ Меню", "m:main")]
                        ))
            else:
                await message.answer("Не удалось озвучить", reply_markup=ik([btn("◀️ Меню", "m:voice")]))
            return

        # ── ПОИСК ──
        if mode == "search":
            clear_ctx(chat_id)
            m2 = await message.answer("Ищу в интернете...")
            results = await web_search(text)
            try: await m2.delete()
            except: pass
            if results:
                msgs = [{"role":"system","content":sys_prompt(uid,chat_id,ct)},
                        {"role":"user","content":f"Результаты поиска по запросу '{text}':\n\n{results}\n\nДай точный краткий ответ."}]
                ans = await ask(msgs, max_t=1000, task="analysis")
                await snd(message, strip_md(ans),
                    reply_markup=ik([btn("🔄 Новый поиск", "m:search")],[btn("◀️ Меню", "m:main")]) if ct == "private" else None)
            else:
                await message.answer("Ничего не нашёл. Попробуй другой запрос.")
            return

        # ── URL ──
        if mode == "url_read":
            clear_ctx(chat_id)
            url_m = await message.answer("Читаю страницу...")
            content = await read_page(text.strip())
            try: await url_m.delete()
            except: pass
            if content:
                msgs = [{"role":"system","content":sys_prompt(uid,chat_id,ct)},
                        {"role":"user","content":f"Страница:\n{content[:5000]}\n\nКратко: основная суть."}]
                ans = await ask(msgs, max_t=1000)
                await snd(message, strip_md(ans),
                    reply_markup=ik([btn("◀️ Меню", "m:tools")]) if ct == "private" else None)
            else:
                await message.answer("Не смог прочитать страницу.")
            return

        # ── ПОГОДА ──
        if mode == "weather":
            clear_ctx(chat_id)
            w = await weather(text)
            if w:
                await message.answer(f"🌤 {text}:\n\n{w}",
                    reply_markup=ik([btn("🔄 Другой город", "m:weather")],[btn("◀️ Меню", "m:main")]) if ct == "private" else None)
            else:
                await message.answer(f"Нет данных для '{text}'")
            return

        # ── КУРС ВАЛЮТ ──
        if mode == "rate_from":
            set_ctx(chat_id, "rate_to", {"from": text.upper().strip()})
            await message.answer(f"{text.upper()} → ?\n\nВалюта назначения (например: RUB):", reply_markup=cancel_kb())
            return

        if mode == "rate_to":
            clear_ctx(chat_id)
            fr = data.get("from","USD"); to = text.upper().strip()
            r = await exchange(fr, to)
            if r: await message.answer(f"{r}",
                reply_markup=ik([btn("🔄 Другой курс", "t:rate")],[btn("◀️ Меню", "m:tools")]) if ct == "private" else None)
            else: await message.answer("Не нашёл такую валюту")
            return

        # ── КАЛЬКУЛЯТОР ──
        if mode == "calc":
            clear_ctx(chat_id)
            expr = text.strip()
            allowed = set("0123456789+-*/().,%^ ")
            if all(c in allowed for c in expr):
                try:
                    result = eval(expr.replace("^","**").replace(",","."))
                    await message.answer(f"{expr} = {result}",
                        reply_markup=ik([btn("🔄 Ещё", "t:calc")],[btn("◀️ Меню", "m:tools")]) if ct == "private" else None)
                except:
                    await message.answer("Не смог посчитать")
            else:
                await message.answer("Недопустимые символы")
            return

        # ── НАПОМИНАНИЕ ──
        if mode == "remind_time":
            try:
                mins = int(re.search(r'\d+', text).group())
                set_ctx(chat_id, "remind_text", {"mins": mins})
                await message.answer(f"Через {mins} мин. О чём напомнить?", reply_markup=cancel_kb())
            except:
                await message.answer("Напиши число минут", reply_markup=cancel_kb())
            return

        if mode == "remind_text":
            clear_ctx(chat_id)
            mins = data.get("mins", 5)
            run_at = datetime.now() + timedelta(minutes=mins)
            scheduler.add_job(
                lambda: asyncio.create_task(bot.send_message(chat_id, f"⏰ Напоминание:\n\n{text}")),
                trigger=DateTrigger(run_date=run_at)
            )
            await message.answer(f"✅ Напомню через {mins} мин:\n{text}",
                reply_markup=ik([btn("◀️ Меню", "m:tools")]) if ct == "private" else None)
            return

        # ── ПЕРЕВОД ──
        if mode == "translate":
            clear_ctx(chat_id)
            lang = detect_lang(text)
            to_lang = "en" if lang in ("ru","uk") else "ru"
            msgs = [{"role":"user","content":f"Переведи на {'английский' if to_lang=='en' else 'русский'}, только перевод:\n{text}"}]
            ans = await ask(msgs, max_t=1000, task="fast")
            await message.answer(f"🌐 Перевод:\n\n{strip_md(ans)}",
                reply_markup=ik([btn("🔄 Ещё", "t:trans")],[btn("◀️ Меню", "m:tools")]) if ct == "private" else None)
            return

        # ── EMAIL ──
        if mode == "email_recipient":
            set_ctx(chat_id, "email_subject", {"to": text.strip()})
            await message.answer("Тема письма:", reply_markup=cancel_kb())
            return
        if mode == "email_subject":
            set_ctx(chat_id, "email_body", {"to": data.get("to",""), "subject": text.strip()})
            await message.answer("Текст письма:", reply_markup=cancel_kb())
            return
        if mode == "email_body":
            clear_ctx(chat_id)
            to_addr = data.get("to",""); subj = data.get("subject","")
            preview = f"Кому: {to_addr}\nТема: {subj}\n\n{text[:500]}"
            aid = f"em_{uid}_{int(time.time())}"
            CONFIRMS[aid] = {"type":"send_email","uid":uid,"chat_id":chat_id,"to":to_addr,"subject":subj,"body":text}
            await message.answer(preview + "\n\nОтправить?", reply_markup=confirm_kb(aid))
            return

        # ── ТВОРЧЕСТВО ──
        if mode == "creative":
            clear_ctx(chat_id)
            subtype = data.get("subtype","text")
            prompts = {
                "text": f"Напиши текст: {text}",
                "article": f"Напиши статью: {text}",
                "email": f"Напиши профессиональный email: {text}",
                "poem": f"Напиши стихотворение: {text}",
                "story": f"Напиши короткий рассказ: {text}",
                "resume": f"Напиши резюме: {text}",
            }
            m2 = await message.answer("Пишу...")
            await bot.send_chat_action(chat_id, "typing")
            ans = await ask([{"role":"system","content":sys_prompt(uid,chat_id,ct)},
                             {"role":"user","content":prompts.get(subtype, text)}],
                            max_t=3000, task="creative")
            try: await m2.delete()
            except: pass
            await snd(message, strip_md(ans),
                reply_markup=ik([btn("🔄 Ещё вариант", f"cr:{subtype}")],[btn("◀️ Творчество", "m:create")]) if ct == "private" else None)
            return

        # ── КОД ──
        if mode == "code":
            clear_ctx(chat_id)
            m2 = await message.answer("Пишу код...")
            await bot.send_chat_action(chat_id, "typing")
            ans = await ask([{"role":"user","content":f"Напиши код: {text}\nТолько код, без лишнего."}],
                max_t=4096, task="code")
            try: await m2.delete()
            except: pass
            await snd(message, ans,
                reply_markup=ik([btn("🔄 Улучшить", "cr:code")],[btn("◀️ Творчество", "m:create")]) if ct == "private" else None)
            return

        # ── УСТАНОВИТЬ ИМЯ ──
        if mode == "set_name":
            clear_ctx(chat_id)
            name = text.strip()[:30]
            Db.set_name(uid, name)
            Db.remember(uid, f"Зовут {name}", "name", 10)
            await message.answer(f"✅ Запомнил, {name}!", reply_markup=menu_profile(uid))
            return

        # ── ЗАМЕТКИ ──
        if mode == "note_title":
            set_ctx(chat_id, "note_content", {"title": text})
            await message.answer("Теперь напиши содержимое:", reply_markup=cancel_kb())
            return
        if mode == "note_content":
            clear_ctx(chat_id)
            Db.add_note(uid, data.get("title","Заметка"), text)
            await message.answer("✅ Заметка сохранена!", reply_markup=menu_notes(uid))
            return

        # ── ЗАДАЧИ ──
        if mode == "todo_add":
            clear_ctx(chat_id)
            Db.add_todo(uid, text)
            await message.answer("✅ Задача добавлена!", reply_markup=menu_todos(uid))
            return

        # ── СКАЧАТЬ ──
        if mode == "dl_url":
            clear_ctx(chat_id)
            url = text.strip()
            fmt = data.get("fmt")
            if fmt:
                m2 = await message.answer(f"Скачиваю {fmt.upper()}...")
                await bot.send_chat_action(chat_id, "upload_document")
                d, fn, err = await dl(url, fmt)
                try: await m2.delete()
                except: pass
                if d and fn:
                    if fmt == "mp3": await message.answer_audio(BufferedInputFile(d, fn), caption=f"🎵 {fn[:50]}")
                    elif fmt == "mp4": await message.answer_video(BufferedInputFile(d, fn), caption=f"🎬 {fn[:50]}")
                    else: await message.answer_document(BufferedInputFile(d, fn))
                    await message.answer("✅", reply_markup=ik([btn("◀️ Меню", "m:main")]) if ct == "private" else None)
                else:
                    await message.answer(f"Не удалось: {err}")
            else:
                await message.answer(f"Выбери формат:\n{url[:50]}", reply_markup=menu_dl_format(url))
            return

        # ── УДАЛЕНИЕ ПО КЛЮЧЕВОМУ СЛОВУ ──
        if mode == "grp_delete":
            clear_ctx(chat_id)
            kw = text.strip()
            with dbc() as c:
                cnt = c.execute("SELECT COUNT(*) FROM grp_msgs WHERE chat_id=? AND LOWER(text) LIKE ? AND msg_id IS NOT NULL",
                    (chat_id, f"%{kw.lower()}%")).fetchone()[0]
            if cnt == 0:
                await message.answer(f"Сообщений со словом '{kw}' не найдено.",
                    reply_markup=ik([btn("◀️ Меню", "m:group")]) if ct == "private" else None)
                return
            aid = f"gdkw_{chat_id}_{int(time.time())}"
            CONFIRMS[aid] = {"type":"grp_del_kw","chat_id":chat_id,"keyword":kw}
            await message.answer(f"Найдено {cnt} сообщений со словом '{kw}'. Удалить?", reply_markup=confirm_kb(aid))
            return

        # ── РАСПИСАНИЕ ГРУППЫ ──
        if mode == "grp_sched_time":
            try:
                h, m = map(int, text.split(":"))
                set_ctx(chat_id, "grp_sched_topic", {"h": h, "m": m})
                await message.answer(f"В {text}. Тема постов:", reply_markup=cancel_kb())
            except:
                await message.answer("Формат: ЧЧ:ММ", reply_markup=cancel_kb())
            return

        if mode == "grp_sched_topic":
            clear_ctx(chat_id)
            h = data.get("h",9); m = data.get("m",0)
            scheduler.add_job(
                lambda: asyncio.create_task(_do_post(chat_id, text)),
                trigger=CronTrigger(hour=h, minute=m),
                id=f"sp_{chat_id}_{h}_{m}", replace_existing=True
            )
            with dbc() as c:
                c.execute("INSERT INTO schedules(chat_id,hour,minute,topic)VALUES(?,?,?,?)", (chat_id, h, m, text))
            await message.answer(f"✅ Каждый день в {h:02d}:{m:02d}: {text}",
                reply_markup=ik([btn("◀️ Меню", "m:group")]) if ct == "private" else None)
            return

        # ── ПОСТ ДЛЯ КАНАЛА ──
        if mode == "ch_post":
            clear_ctx(chat_id)
            m2 = await message.answer("Пишу пост...")
            post = await _do_post_gen(chat_id, text)
            try: await m2.delete()
            except: pass
            if post:
                clean_post = strip_md(post)
                await message.answer(
                    f"Пост готов:\n\n{clean_post}\n\n---",
                    reply_markup=ik(
                        [btn("✅ Опубликовать", f"chpub:{chat_id}:{len(post)}")],
                        [btn("🔄 Другой вариант", "ch:post")],
                        [btn("◀️ Назад", "m:channel")]
                    )
                )
            else:
                await message.answer("Не получилось", reply_markup=ik([btn("◀️ Меню", "m:channel")]))
            return

        # ── ПУБЛИКАЦИЯ В КАНАЛ ──
        if mode == "ch_pub":
            clear_ctx(chat_id)
            try:
                await bot.send_message(chat_id, text)
                await message.answer("✅ Опубликовано!", reply_markup=ik([btn("◀️ Меню", "m:channel")]))
            except Exception as e:
                await message.answer(f"Ошибка: {e}\nПроверь права бота",
                    reply_markup=ik([btn("ℹ️ Как добавить", "ch:howto")],[btn("◀️", "m:channel")]))
            return

        # ── РАСПИСАНИЕ КАНАЛА ──
        if mode == "ch_sched_time":
            try:
                h, m = map(int, text.split(":"))
                set_ctx(chat_id, "ch_sched_topic", {"h": h, "m": m})
                await message.answer(f"В {text}. Тема для постов:", reply_markup=cancel_kb())
            except:
                await message.answer("Формат: ЧЧ:ММ", reply_markup=cancel_kb())
            return

        if mode == "ch_sched_topic":
            clear_ctx(chat_id)
            h = data.get("h",9); m = data.get("m",0)
            scheduler.add_job(
                lambda: asyncio.create_task(_do_post(chat_id, text)),
                trigger=CronTrigger(hour=h, minute=m),
                id=f"chsp_{chat_id}_{h}_{m}", replace_existing=True
            )
            await message.answer(f"✅ Автопосты в {h:02d}:{m:02d}: {text}",
                reply_markup=ik([btn("◀️ Меню", "m:channel")]))
            return

    # Reply на медиа
    rep = message.reply_to_message
    if rep:
        if rep.photo: await _handle_photo_q(message, rep.photo[-1], text); return
        elif rep.video: await _handle_vid(message, rep.video.file_id, text or "", media_type="video"); return
        elif rep.voice: await _handle_voice_q(message, rep.voice, text); return
        elif rep.video_note: await _handle_vid(message, rep.video_note.file_id, text or "Опиши", media_type="video_note"); return

    # Обычный чат — определяем тип задачи
    task = "general"
    tl = text.lower()
    if any(k in tl for k in ["код","python","javascript","typescript","функция","алгоритм","скрипт","sql"]): task = "code"
    elif any(k in tl for k in ["2025","2026","новости","актуальн","текущий","сегодня","сейчас"]): task = "analysis"
    elif any(k in tl for k in ["стихи","рассказ","история","напиши","сочини","придумай"]): task = "creative"

    await ai_respond(message, text, task)


# ═══════════════════════════════════════════════════════════
#  МЕДИА ХЭНДЛЕРЫ
# ═══════════════════════════════════════════════════════════
@dp.message(F.voice)
async def on_voice(message: Message):
    uid = message.from_user.id; chat_id = message.chat.id; ct = message.chat.type
    if ct in ("group","supergroup"):
        Db.grp_save(chat_id, uid, message.from_user.first_name or "",
            message.from_user.username or "", mtype="voice", msg_id=message.message_id)
        # В группе проверяем — упоминают ли нас
        # (голосовое без упоминания — игнорируем, но сохраняем статистику)
        if not message.reply_to_message:
            return
    await bot.send_chat_action(chat_id, "typing")
    try:
        file = await bot.get_file(message.voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name); ap = tmp.name
        text = await stt(ap)
        try: os.unlink(ap)
        except: pass
        if not text:
            if ct == "private":
                await message.answer("Не распознал речь. Попробуй снова.")
            return
        if ct == "private":
            await message.answer(f"🎤 {text}")
        await ai_respond(message, text)
    except Exception as e:
        log.error(f"Voice: {e}")
        if ct == "private":
            await message.answer("Ошибка при обработке голосового.")

@dp.message(F.photo)
async def on_photo(message: Message):
    uid = message.from_user.id; chat_id = message.chat.id; ct = message.chat.type
    if ct in ("group","supergroup"):
        Db.grp_save(chat_id, uid, message.from_user.first_name or "",
            message.from_user.username or "", mtype="photo", msg_id=message.message_id)
    cap = message.caption or "Подробно опиши что на фото"
    await bot.send_chat_action(chat_id, "typing")
    try:
        file = await bot.get_file(message.photo[-1].file_id)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name); pp = tmp.name
        with open(pp, "rb") as f: b64 = base64.b64encode(f.read()).decode()
        try: os.unlink(pp)
        except: pass
        an = await _gemini_vision(b64, cap)
        if an:
            Db.add(uid, chat_id, "user", f"[фото] {cap}")
            Db.add(uid, chat_id, "assistant", an)
            await message.answer(strip_md(an))
        else:
            if ct == "private":
                await message.answer("Не смог проанализировать фото")
    except Exception as e:
        log.error(f"Photo: {e}")
        if ct == "private":
            await message.answer("Ошибка при анализе фото")

@dp.message(F.video)
async def on_video(message: Message):
    uid = message.from_user.id; chat_id = message.chat.id; ct = message.chat.type
    if ct in ("group","supergroup"):
        Db.grp_save(chat_id, uid, message.from_user.first_name or "",
            message.from_user.username or "", mtype="video", msg_id=message.message_id)
    await _handle_vid(message, message.video.file_id, message.caption or "")

@dp.message(F.video_note)
async def on_vn(message: Message):
    uid = message.from_user.id; chat_id = message.chat.id; ct = message.chat.type
    if ct in ("group","supergroup"):
        Db.grp_save(chat_id, uid, message.from_user.first_name or "",
            message.from_user.username or "", mtype="video_note", msg_id=message.message_id)
    await _handle_vid(message, message.video_note.file_id, "Опиши видеокружок", media_type="video_note")

@dp.message(F.audio)
async def on_audio(message: Message):
    chat_id = message.chat.id; ct = message.chat.type
    await bot.send_chat_action(chat_id, "typing")
    try:
        file = await bot.get_file(message.audio.file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name); ap = tmp.name
        info = None
        try:
            info = await recognize_music(ap)
        except: pass
        if info:
            await message.answer("🎵 " + format_music_info(info))
        t = await stt(ap)
        try: os.unlink(ap)
        except: pass
        if t:
            if ct == "private":
                await message.answer(f"Транскрипция:\n\n{t}")
        elif not info:
            if ct == "private":
                await ai_respond(message, f"Аудио файл. {message.caption or ''}")
    except Exception as e:
        log.error(f"Audio: {e}")

@dp.message(F.document)
async def on_doc(message: Message):
    if message.chat.type in ("group","supergroup"):
        Db.grp_save(message.chat.id, message.from_user.id,
            message.from_user.first_name or "", message.from_user.username or "",
            mtype="doc", msg_id=message.message_id)
    if message.chat.type != "private": return
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        file = await bot.get_file(message.document.file_id)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name); fp = tmp.name
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f: content = f.read()[:12000]
        except: content = "[Бинарный файл — анализ содержимого недоступен]"
        try: os.unlink(fp)
        except: pass
        fname = message.document.file_name or "файл"
        cap = message.caption or "Проанализируй этот файл"
        await ai_respond(message, f"{cap}\n\nФайл '{fname}':\n{content}", task="analysis")
    except Exception as e:
        log.error(f"Doc: {e}")
        await message.answer("Не смог прочитать файл")

@dp.message(F.sticker)
async def on_sticker(message: Message):
    if message.chat.type in ("group","supergroup"):
        Db.grp_save(message.chat.id, message.from_user.id,
            message.from_user.first_name or "", message.from_user.username or "",
            mtype="sticker", msg_id=message.message_id)
    if message.chat.type == "private":
        await ai_respond(message, "[стикер] Отреагируй живо и в тему!")

@dp.message(F.location)
async def on_loc(message: Message):
    lat = message.location.latitude; lon = message.location.longitude
    w = await weather(f"{lat},{lon}")
    if w:
        await message.answer(f"Погода:\n\n{w}",
            reply_markup=ik([btn("◀️ Меню", "m:main")]) if message.chat.type == "private" else None)
    else:
        await message.answer("Локация получена!")

async def _handle_vid(message, file_id, caption="", media_type="video"):
    uid = message.from_user.id; chat_id = message.chat.id; ct = message.chat.type
    await bot.send_chat_action(chat_id, "typing")
    try:
        file = await bot.get_file(file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name); vp = tmp.name
        vis = sp = None
        if FFMPEG:
            fp, ap = extract_vid(vp)
            try: os.unlink(vp)
            except: pass
            prompt_vis = "Опиши кадр из видео" if media_type == "video" else "Опиши видеокружок"
            if fp:
                with open(fp, "rb") as f: b64 = base64.b64encode(f.read()).decode()
                try: os.unlink(fp)
                except: pass
                vis = await _gemini_vision(b64, caption or prompt_vis)
            if ap:
                sp = await stt(ap)
                try: os.unlink(ap)
                except: pass
        else:
            try: os.unlink(vp)
            except: pass
        parts = []
        if vis: parts.append(f"Видео: {vis[:300]}")
        if sp: parts.append(f"Речь: {sp[:200]}")
        if parts and ct == "private":
            await message.answer(" | ".join(parts))
        type_label = "Видеосообщение" if media_type == "video_note" else "Видео"
        ctx_text = f"{type_label}. "
        if caption: ctx_text += f"Подпись: {caption}. "
        if vis: ctx_text += f"На видео: {vis}. "
        if sp: ctx_text += f"Говорят: {sp}. "
        if not vis and not sp: ctx_text += "Не смог проанализировать содержимое."
        await ai_respond(message, ctx_text)
    except Exception as e:
        log.error(f"Vid: {e}")
        if message.chat.type == "private":
            await message.answer("Не обработал видео")

async def _handle_photo_q(message, photo, q):
    try:
        file = await bot.get_file(photo.file_id)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name); pp = tmp.name
        with open(pp, "rb") as f: b64 = base64.b64encode(f.read()).decode()
        try: os.unlink(pp)
        except: pass
        an = await _gemini_vision(b64, q)
        if an:
            Db.add(message.from_user.id, message.chat.id, "user", f"[фото+вопрос] {q}")
            Db.add(message.from_user.id, message.chat.id, "assistant", an)
            await message.answer(strip_md(an))
        else:
            await message.answer("Не смог")
    except Exception as e:
        log.error(f"PhotoQ: {e}")

async def _handle_voice_q(message, voice, q):
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        file = await bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name); ap = tmp.name
        t = await stt(ap)
        try: os.unlink(ap)
        except: pass
        if t:
            await ai_respond(message, f"{q}\n\nВ голосовом: {t}")
        else:
            await message.answer("Не распознал голос")
    except Exception as e:
        log.error(f"VoiceQ: {e}")

# ═══════════════════════════════════════════════════════════
#  ДОБАВЛЕНИЕ В ЧАТ
# ═══════════════════════════════════════════════════════════
@dp.my_chat_member()
async def on_added(upd):
    try:
        ns = upd.new_chat_member.status; chat_id = upd.chat.id
        if ns in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
            ch = await bot.get_chat(chat_id); ct = ch.type
            if ct == "channel":
                await bot.send_message(chat_id,
                    "NEXUM v7.0 подключён к каналу.\n\nАнализирую контент...",
                    reply_markup=menu_channel())
                asyncio.create_task(_auto_analyze(chat_id, ch.title or "?"))
            elif ct in ("group","supergroup"):
                await bot.send_message(chat_id,
                    "Привет! Я NEXUM — AI-ассистент.\n\n"
                    "Пишите @mention или reply чтобы обратиться ко мне.",
                    reply_markup=ik([btn("📋 Меню", "m:main")]))
    except Exception as e:
        log.error(f"Added: {e}")

async def _auto_analyze(chat_id, title):
    try:
        await asyncio.sleep(5)
        an = await _analyze_ch(chat_id)
        if an:
            sp = [{"role":"user","content":f"Стиль для '{title}' в 4 предложения:\n{an}"}]
            style = await ask(sp, max_t=200, task="analysis")
            Db.save_channel(chat_id, title, an, style or "")
    except Exception as e:
        log.error(f"AutoAnalyze: {e}")

# ═══════════════════════════════════════════════════════════
#  ВОССТАНОВЛЕНИЕ РАСПИСАНИЙ + ЗАПУСК
# ═══════════════════════════════════════════════════════════
async def restore_schedules():
    with dbc() as c:
        rows = c.execute("SELECT chat_id,hour,minute,topic FROM schedules WHERE active=1").fetchall()
    for r in rows:
        cid, h, m, topic = r['chat_id'], r['hour'], r['minute'], r['topic']
        scheduler.add_job(
            lambda ci=cid, t=topic: asyncio.create_task(_do_post(ci, t)),
            trigger=CronTrigger(hour=h, minute=m),
            id=f"sp_{cid}_{h}_{m}", replace_existing=True
        )
    log.info(f"Restored {len(rows)} schedules")

async def main():
    init_db()
    scheduler.start()
    await restore_schedules()

    log.info("=" * 60)
    log.info("  NEXUM v7.0 — AI-ассистент")
    log.info(f"  Gemini:   {len(GEMINI_KEYS)} keys")
    log.info(f"  Groq:     {len(GROQ_KEYS)} keys")
    log.info(f"  DeepSeek: {len(DS_KEYS)} keys")
    log.info(f"  Claude:   {len(CLAUDE_KEYS)} keys")
    log.info(f"  Grok:     {len(GROK_KEYS)} keys")
    log.info(f"  ffmpeg:   {'YES' if FFMPEG else 'NO'}")
    log.info(f"  yt-dlp:   {'YES' if YTDLP else 'NO'}")
    log.info("=" * 60)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
