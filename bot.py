"""
╔══════════════════════════════════════════════════════════════╗
║  NEXUM — AI Assistant (nexum v1.0)                          ║
║  Intent-driven: no menus, AI understands and acts directly  ║
╚══════════════════════════════════════════════════════════════╝
"""
import asyncio, logging, os, tempfile, base64, random, aiohttp, sys, json, re, time
import subprocess, shutil, sqlite3
from urllib.parse import quote as uq
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, BufferedInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats,
    ChatMemberUpdated,
)
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.storage.memory import MemoryStorage

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError: pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger("NEXUM")

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path: sys.path.insert(0, _ROOT)

# ── Load config (all keys from env, no hardcoded secrets) ──
from nexum_config import (
    BOT_TOKEN, GEMINI_KEYS, GROQ_KEYS, DS_KEYS, CLAUDE_KEYS, GROK_KEYS,
    HF_TOKEN, NOTION_TOKEN, NOTION_DEFAULT_PAGE, check_keys,
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
)

# ── Media module ───────────────────────────────────────────
try:
    from nexum_media import (
        gen_img, gen_music, gen_video, gen_song_with_vocals,
        translate_to_en, IMG_STYLES, MUSIC_STYLES,
    )
    HAS_MEDIA = True
except ImportError as e:
    log.warning(f"nexum_media: {e}")
    HAS_MEDIA = False
    IMG_STYLES = {}; MUSIC_STYLES = {}
    async def gen_img(p, s="авто"): return None
    async def gen_music(p, s="авто"): return None
    async def gen_video(p): return None
    async def gen_song_with_vocals(p, s, l): return None, ""
    async def translate_to_en(t): return t

# ── Notion module ──────────────────────────────────────────
try:
    from nexum_notion import NotionClient, parse_notion_intent
    notion = NotionClient(NOTION_TOKEN) if NOTION_TOKEN else None
    HAS_NOTION = bool(NOTION_TOKEN)
except ImportError:
    notion = None; HAS_NOTION = False

# ── Music recognition ──────────────────────────────────────
try:
    from nexum_music_recognition import recognize_music, format_music_info
except ImportError:
    async def recognize_music(p): return None
    def format_music_info(i): return ""

# ── Web search ─────────────────────────────────────────────
try:
    from nexum_web import web_search as _web_search_ext, read_page as _read_page_ext
    async def web_search(q): return await _web_search_ext(q)
    async def read_page(u): return await _read_page_ext(u)
except ImportError:
    async def web_search(q): return await _web_search_fallback(q)
    async def read_page(u): return await _read_page_fallback(u)


# ═══════════════════════════════════════════════════════════
#  INIT
# ═══════════════════════════════════════════════════════════
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()
FFMPEG = shutil.which("ffmpeg")
YTDLP  = shutil.which("yt-dlp")

_ki: Dict[str, int] = {p: 0 for p in ["g","gr","ds","cl","gk"]}
def _gk(p, keys): return keys[_ki[p] % len(keys)] if keys else None
def _rk(p, keys):
    if keys: _ki[p] = (_ki[p] + 1) % len(keys)

# Global state
CONFIRMS: Dict[str, Dict] = {}        # aid -> action for destructive ops
CHANNEL_ADMINS: Dict[int, int] = {}   # channel_id -> admin_uid
INPUT_CTX: Dict[int, Dict] = {}       # chat_id -> {mode, data}
PENDING_ACTIONS: Dict[str, Dict] = {} # for admin-approval requests

# ═══════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════
DB_PATH = os.path.join(_ROOT, "nexum.db")

def _init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            uid INTEGER PRIMARY KEY, name TEXT DEFAULT '',
            username TEXT DEFAULT '', voice TEXT DEFAULT 'auto',
            first_seen TEXT, last_seen TEXT, total_msgs INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS conv(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER, chat_id INTEGER, role TEXT, content TEXT,
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
        CREATE TABLE IF NOT EXISTS channels(
            chat_id INTEGER PRIMARY KEY, title TEXT DEFAULT '',
            admin_uid INTEGER DEFAULT 0, analysis TEXT DEFAULT '',
            style TEXT DEFAULT '', username TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS grp_msgs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER, uid INTEGER, msg_id INTEGER,
            text TEXT DEFAULT '', mtype TEXT DEFAULT 'text',
            ts TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS grp_stats(
            chat_id INTEGER, uid INTEGER, name TEXT DEFAULT '',
            username TEXT DEFAULT '', msgs INTEGER DEFAULT 0,
            words INTEGER DEFAULT 0, last_active TEXT, first_seen TEXT,
            PRIMARY KEY(chat_id, uid)
        );
        CREATE TABLE IF NOT EXISTS schedules(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER, hour INTEGER, minute INTEGER,
            topic TEXT, active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS user_emails(
            uid INTEGER PRIMARY KEY, email TEXT, password TEXT,
            smtp_host TEXT, smtp_port INTEGER DEFAULT 587,
            imap_host TEXT, imap_port INTEGER DEFAULT 993
        );
        CREATE TABLE IF NOT EXISTS notion_links(
            uid INTEGER PRIMARY KEY, default_page TEXT
        );
        CREATE INDEX IF NOT EXISTS ic ON conv(uid,chat_id);
        CREATE INDEX IF NOT EXISTS im ON memory(uid);
        CREATE INDEX IF NOT EXISTS ig ON grp_msgs(chat_id);
        """)
    log.info("DB ready")

def _dbc():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

class Db:
    @staticmethod
    def ensure(uid, name="", username=""):
        now = datetime.now().isoformat()
        with _dbc() as c:
            c.execute("""INSERT INTO users(uid,name,username,first_seen,last_seen)VALUES(?,?,?,?,?)
                ON CONFLICT(uid) DO UPDATE SET last_seen=excluded.last_seen,
                name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END,
                username=CASE WHEN excluded.username!='' THEN excluded.username ELSE username END""",
                (uid, name, username, now, now))

    @staticmethod
    def user(uid) -> dict:
        with _dbc() as c:
            r = c.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
            if not r: return {}
            u = dict(r)
            u['memory'] = [dict(x) for x in c.execute(
                "SELECT * FROM memory WHERE uid=? ORDER BY imp DESC", (uid,)).fetchall()]
            return u

    @staticmethod
    def voice(uid):
        with _dbc() as c:
            r = c.execute("SELECT voice FROM users WHERE uid=?", (uid,)).fetchone()
            return r[0] if r else "auto"

    @staticmethod
    def set_voice(uid, v):
        with _dbc() as c: c.execute("UPDATE users SET voice=? WHERE uid=?", (v, uid))

    @staticmethod
    def remember(uid, fact, cat="gen", imp=5):
        with _dbc() as c:
            rows = c.execute("SELECT id,fact FROM memory WHERE uid=? AND cat=?", (uid,cat)).fetchall()
            for rid, ef in rows:
                aw = set(fact.lower().split()); bw = set(ef.lower().split())
                if aw and bw and len(aw & bw) / len(aw | bw) > 0.65:
                    c.execute("UPDATE memory SET fact=? WHERE id=?", (fact, rid)); return
            c.execute("INSERT INTO memory(uid,cat,fact,imp)VALUES(?,?,?,?)", (uid,cat,fact,imp))
            c.execute("DELETE FROM memory WHERE id IN(SELECT id FROM memory WHERE uid=? AND cat=? ORDER BY imp DESC LIMIT -1 OFFSET 40)", (uid,cat))

    @staticmethod
    def extract_facts(uid, text):
        pats = [
            (r'меня зовут\s+([А-ЯЁа-яёA-Za-z]{2,20})', 'name', 10),
            (r'мне\s+(\d{1,2})\s*(?:год|лет)', 'age', 9),
            (r'(?:я из|живу в|нахожусь в)\s+([А-ЯЁа-яё\w\s]{2,25})', 'city', 8),
            (r'работаю\s+([А-ЯЁа-яё\w\s]{2,40})', 'work', 7),
        ]
        for p, cat, imp in pats:
            m = re.search(p, text, re.I)
            if m: Db.remember(uid, m.group(0).strip(), cat, imp)
        nm = re.search(r'(?:меня зовут|я\s*[-—])\s*([А-ЯЁA-Z][а-яёa-z]{1,15})', text)
        if nm:
            with _dbc() as c: c.execute("UPDATE users SET name=? WHERE uid=?", (nm.group(1), uid))

    @staticmethod
    def history(uid, chat_id, n=30):
        with _dbc() as c:
            rows = c.execute("SELECT role,content FROM conv WHERE uid=? AND chat_id=? ORDER BY id DESC LIMIT ?",
                (uid, chat_id, n)).fetchall()
        return list(reversed(rows))

    @staticmethod
    def add(uid, chat_id, role, content):
        with _dbc() as c:
            c.execute("INSERT INTO conv(uid,chat_id,role,content)VALUES(?,?,?,?)",
                (uid, chat_id, role, content))
            if role == "user":
                c.execute("UPDATE users SET total_msgs=total_msgs+1 WHERE uid=?", (uid,))

    @staticmethod
    def clear(uid, chat_id):
        with _dbc() as c: c.execute("DELETE FROM conv WHERE uid=? AND chat_id=?", (uid,chat_id))

    @staticmethod
    def grp_save(chat_id, uid, name, username, text="", mtype="text", msg_id=None):
        now = datetime.now().isoformat()
        w = len(text.split()) if text else 0
        with _dbc() as c:
            c.execute("""INSERT INTO grp_stats(chat_id,uid,name,username,msgs,words,last_active,first_seen)
                VALUES(?,?,?,?,1,?,?,?) ON CONFLICT(chat_id,uid) DO UPDATE SET
                msgs=msgs+1, words=words+excluded.words, last_active=excluded.last_active,
                name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END,
                username=CASE WHEN excluded.username!='' THEN excluded.username ELSE username END""",
                (chat_id, uid, name, username, w, now, now))
            if msg_id:
                c.execute("INSERT INTO grp_msgs(chat_id,uid,msg_id,text,mtype)VALUES(?,?,?,?,?)",
                    (chat_id, uid, msg_id, (text or "")[:500], mtype))
                c.execute("DELETE FROM grp_msgs WHERE id IN(SELECT id FROM grp_msgs WHERE chat_id=? ORDER BY id DESC LIMIT -1 OFFSET 10000)", (chat_id,))

    @staticmethod
    def grp_stats(chat_id):
        with _dbc() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM grp_stats WHERE chat_id=? ORDER BY msgs DESC LIMIT 20", (chat_id,)).fetchall()]

    @staticmethod
    def grp_msgs(chat_id, n=200):
        with _dbc() as c:
            rows = c.execute("SELECT uid,msg_id,text,mtype,ts FROM grp_msgs WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, n)).fetchall()
        return list(reversed([dict(r) for r in rows]))

    @staticmethod
    def channel(chat_id):
        with _dbc() as c:
            r = c.execute("SELECT * FROM channels WHERE chat_id=?", (chat_id,)).fetchone()
            return dict(r) if r else None

    @staticmethod
    def save_channel(chat_id, title="", admin_uid=0, analysis="", style="", username=""):
        with _dbc() as c:
            c.execute("""INSERT INTO channels(chat_id,title,admin_uid,analysis,style,username)VALUES(?,?,?,?,?,?)
                ON CONFLICT(chat_id) DO UPDATE SET title=CASE WHEN excluded.title!='' THEN excluded.title ELSE title END,
                admin_uid=CASE WHEN excluded.admin_uid!=0 THEN excluded.admin_uid ELSE admin_uid END,
                analysis=CASE WHEN excluded.analysis!='' THEN excluded.analysis ELSE analysis END,
                style=CASE WHEN excluded.style!='' THEN excluded.style ELSE style END,
                username=CASE WHEN excluded.username!='' THEN excluded.username ELSE username END""",
                (chat_id, title, admin_uid, analysis, style, username))

    @staticmethod
    def user_channels(uid) -> List[dict]:
        with _dbc() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM channels WHERE admin_uid=?", (uid,)).fetchall()]

    @staticmethod
    def summaries(uid, chat_id):
        with _dbc() as c:
            return [r[0] for r in c.execute(
                "SELECT text FROM summaries WHERE uid=? AND chat_id=?", (uid, chat_id)).fetchall()]

    @staticmethod
    async def maybe_compress(uid, chat_id):
        try:
            with _dbc() as c:
                n = c.execute("SELECT COUNT(*) FROM conv WHERE uid=? AND chat_id=?", (uid, chat_id)).fetchone()[0]
                if n <= 60: return
                old = c.execute("SELECT id,role,content FROM conv WHERE uid=? AND chat_id=? ORDER BY id ASC LIMIT 30", (uid, chat_id)).fetchall()
            if not old: return
            lines = [("User" if r[1]=="user" else "NEXUM")+": "+r[2][:200] for r in old]
            s = await _ask([{"role":"user","content":"Кратко резюмируй диалог (80 слов):\n"+"\n".join(lines)}], max_t=150)
            if not s: return
            with _dbc() as c:
                c.execute("INSERT INTO summaries(uid,chat_id,text)VALUES(?,?,?)", (uid, chat_id, s))
                ids = ",".join(str(r[0]) for r in old)
                c.execute(f"DELETE FROM conv WHERE id IN({ids})")
        except Exception as e: log.error(f"Compress: {e}")

    @staticmethod
    def get_email(uid) -> Optional[dict]:
        with _dbc() as c:
            r = c.execute("SELECT * FROM user_emails WHERE uid=?", (uid,)).fetchone()
            return dict(r) if r else None

    @staticmethod
    def save_email(uid, email, password, smtp_host, smtp_port=587, imap_host="", imap_port=993):
        with _dbc() as c:
            c.execute("""INSERT INTO user_emails(uid,email,password,smtp_host,smtp_port,imap_host,imap_port)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET email=excluded.email,
                password=excluded.password, smtp_host=excluded.smtp_host, smtp_port=excluded.smtp_port,
                imap_host=excluded.imap_host, imap_port=excluded.imap_port""",
                (uid, email, password, smtp_host, smtp_port, imap_host, imap_port))

    @staticmethod
    def get_notion_page(uid) -> Optional[str]:
        with _dbc() as c:
            r = c.execute("SELECT default_page FROM notion_links WHERE uid=?", (uid,)).fetchone()
            return r[0] if r else NOTION_DEFAULT_PAGE

    @staticmethod
    def set_notion_page(uid, page_id):
        with _dbc() as c:
            c.execute("INSERT INTO notion_links(uid,default_page)VALUES(?,?) ON CONFLICT(uid) DO UPDATE SET default_page=excluded.default_page",
                (uid, page_id))


# ═══════════════════════════════════════════════════════════
#  AI PROVIDERS
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
        "safetySettings": [{"category": c, "threshold": "BLOCK_NONE"} for c in [
            "HARM_CATEGORY_HARASSMENT","HARM_CATEGORY_HATE_SPEECH",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT","HARM_CATEGORY_DANGEROUS_CONTENT"
        ]],
    }
    if sys_txt: body["systemInstruction"] = {"parts": [{"text": sys_txt}]}
    for _ in range(len(GEMINI_KEYS)):
        key = _gk("g", GEMINI_KEYS)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json=body, timeout=aiohttp.ClientTimeout(total=50)) as r:
                    if r.status in (429, 500, 503): _rk("g", GEMINI_KEYS); continue
                    if r.status == 200:
                        d = await r.json()
                        try: return d["candidates"][0]["content"]["parts"][0]["text"]
                        except: _rk("g", GEMINI_KEYS); continue
                    _rk("g", GEMINI_KEYS)
        except asyncio.TimeoutError: _rk("g", GEMINI_KEYS)
        except: _rk("g", GEMINI_KEYS)
    return None

async def _gemini_vision(b64, prompt, mime="image/jpeg"):
    if not GEMINI_KEYS: return None
    body = {
        "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime, "data": b64}}]}],
        "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.7},
        "safetySettings": [{"category": c, "threshold": "BLOCK_NONE"} for c in [
            "HARM_CATEGORY_HARASSMENT","HARM_CATEGORY_HATE_SPEECH",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT","HARM_CATEGORY_DANGEROUS_CONTENT"
        ]],
    }
    for _ in range(len(GEMINI_KEYS)):
        key = _gk("g", GEMINI_KEYS)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={key}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json=body, timeout=aiohttp.ClientTimeout(total=40)) as r:
                    if r.status in (429, 500, 503): _rk("g", GEMINI_KEYS); continue
                    if r.status == 200:
                        d = await r.json()
                        try: return d["candidates"][0]["content"]["parts"][0]["text"]
                        except: _rk("g", GEMINI_KEYS)
                    else: _rk("g", GEMINI_KEYS)
        except: _rk("g", GEMINI_KEYS)
    return None

async def _groq(msgs, model="llama-3.3-70b-versatile", max_t=2048, temp=0.8):
    if not GROQ_KEYS: return None
    for _ in range(len(GROQ_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {_gk('gr', GROQ_KEYS)}"},
                    json={"model": model, "messages": msgs, "max_tokens": max_t, "temperature": temp},
                    timeout=aiohttp.ClientTimeout(total=35)) as r:
                    if r.status == 429: _rk("gr", GROQ_KEYS); await asyncio.sleep(1); continue
                    if r.status == 200: return (await r.json())["choices"][0]["message"]["content"]
                    _rk("gr", GROQ_KEYS)
        except: _rk("gr", GROQ_KEYS)
    return None

async def _ds(msgs, max_t=4096, temp=0.8):
    if not DS_KEYS: return None
    for _ in range(len(DS_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.deepseek.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {_gk('ds', DS_KEYS)}"},
                    json={"model": "deepseek-chat", "messages": msgs, "max_tokens": max_t, "temperature": temp},
                    timeout=aiohttp.ClientTimeout(total=55)) as r:
                    if r.status == 429: _rk("ds", DS_KEYS); continue
                    if r.status == 200: return (await r.json())["choices"][0]["message"]["content"]
                    _rk("ds", DS_KEYS)
        except: _rk("ds", DS_KEYS)
    return None

async def _claude(msgs, max_t=4096, temp=0.8):
    if not CLAUDE_KEYS: return None
    sys_txt = ""; filt = []
    for m in msgs:
        if m["role"] == "system": sys_txt = m["content"]
        else: filt.append(m)
    if not filt: return None
    body = {"model": "claude-opus-4-5", "max_tokens": max_t, "temperature": temp, "messages": filt}
    if sys_txt: body["system"] = sys_txt
    for _ in range(len(CLAUDE_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": _gk("cl", CLAUDE_KEYS), "anthropic-version": "2023-06-01"},
                    json=body, timeout=aiohttp.ClientTimeout(total=60)) as r:
                    if r.status in (429, 529): _rk("cl", CLAUDE_KEYS); await asyncio.sleep(3); continue
                    if r.status == 200: return (await r.json())["content"][0]["text"]
                    _rk("cl", CLAUDE_KEYS)
        except: _rk("cl", CLAUDE_KEYS)
    return None

async def _grok(msgs, max_t=4096, temp=0.8):
    if not GROK_KEYS: return None
    for _ in range(len(GROK_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.x.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {_gk('gk', GROK_KEYS)}"},
                    json={"model": "grok-beta", "messages": msgs, "max_tokens": max_t, "temperature": temp},
                    timeout=aiohttp.ClientTimeout(total=55)) as r:
                    if r.status == 429: _rk("gk", GROK_KEYS); continue
                    if r.status == 200: return (await r.json())["choices"][0]["message"]["content"]
                    _rk("gk", GROK_KEYS)
        except: _rk("gk", GROK_KEYS); break
    return None

TASK_ORDERS = {
    "fast":     [("g","gemini-2.0-flash"),("gr","llama-3.3-70b-versatile"),("ds",None),("cl",None)],
    "code":     [("ds",None),("g","gemini-2.0-flash-exp"),("gr","llama-3.3-70b-versatile"),("cl",None)],
    "creative": [("g","gemini-2.0-flash-exp"),("cl",None),("gr","llama-3.3-70b-versatile"),("ds",None)],
    "analysis": [("g","gemini-2.0-flash-exp"),("ds",None),("gr","llama-3.3-70b-versatile"),("cl",None)],
    "json":     [("g","gemini-2.0-flash"),("gr","llama-3.3-70b-versatile"),("ds",None)],
    "general":  [("g","gemini-2.0-flash-exp"),("gr","llama-3.3-70b-versatile"),("ds",None),("cl",None),("gk",None)],
}

async def _ask(msgs, max_t=4096, temp=0.85, task="general") -> str:
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
                    r = await _groq(msgs, model=mdl, max_t=min(max_t,2048), temp=temp)
                    if r: break
            elif pname == "ds" and DS_KEYS: r = await _ds(msgs, max_t=max_t, temp=temp)
            elif pname == "cl" and CLAUDE_KEYS: r = await _claude(msgs, max_t=min(max_t,4096), temp=temp)
            elif pname == "gk" and GROK_KEYS: r = await _grok(msgs, max_t=max_t, temp=temp)
            if r and r.strip():
                log.info(f"AI response via {pname}")
                return r
        except Exception as e: log.warning(f"Provider {pname}: {e}")
    # Absolute fallback
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
    raise Exception("AI временно недоступен. Попробуй через 30 секунд.")


# ═══════════════════════════════════════════════════════════
#  INTENT DETECTION — AI parses what user wants
# ═══════════════════════════════════════════════════════════
INTENT_SCHEMA = """
Analyze the user message and return JSON with EXACTLY this structure:
{
  "action": "<one of the actions below>",
  "params": {<action-specific params>},
  "confidence": <0.0-1.0>
}

ACTIONS and their params:
- "chat": regular conversation. params: {}
- "generate_image": create/draw/generate image. params: {"prompt": "...", "style": "<style key or auto>"}
- "generate_music": create instrumental music. params: {"prompt": "...", "style": "<style or авто>"}
- "generate_song": create song with vocals. params: {"prompt": "...", "style": "<style or авто>", "lyrics": ""}
- "generate_video": create video. params: {"prompt": "..."}
- "tts": convert text to speech/voice. params: {"text": "...", "voice": "auto"}
- "search_web": search internet for info. params: {"query": "..."}
- "read_url": read/analyze a URL. params: {"url": "..."}
- "weather": get weather. params: {"city": "..."}
- "currency": exchange rate. params: {"from": "USD", "to": "RUB"}
- "download_media": download from YouTube/TikTok/Instagram. params: {"url": "...", "format": "mp3|mp4"}
- "translate": translate text. params: {"text": "...", "target_lang": "ru|en"}
- "remind": set reminder. params: {"minutes": 0, "message": "..."}
- "channel_post": create/publish post in channel. params: {"topic": "...", "channel_id": null}
- "channel_schedule": set up auto-posting. params: {"topic": "...", "time": "HH:MM", "channel_id": null}
- "notion_create_page": create page in Notion. params: {"title": "...", "content": "..."}
- "notion_create_task": add task/todo to Notion. params: {"title": "...", "tags": [], "status": "Todo"}
- "notion_read": read/search Notion. params: {"query": "..."}
- "stats": show group/chat statistics. params: {}
- "clear_history": clear conversation history. params: {}
- "admin_action": destructive/important action needing admin approval. params: {"type": "delete_messages|ban_user|kick_user", "target": "...", "description": "..."}

STYLE KEYS for images (use Russian): авто, реализм, аниме, 3d, масло, акварель, киберпанк, фэнтези, эскиз, пиксель, портрет, минимализм
STYLE KEYS for music (use Russian): авто, рок, поп, джаз, хип-хоп, классика, электро, релакс, r&b, метал

Return ONLY valid JSON, no markdown, no explanation.
"""

async def detect_intent(text: str, uid: int, chat_type: str = "private") -> dict:
    """Use AI to detect user intent from message."""
    u = Db.user(uid)
    name = u.get("name", "")
    channels = Db.user_channels(uid)
    ch_info = ""
    if channels:
        ch_info = f"\nUser has {len(channels)} channel(s): " + ", ".join(f"«{c['title']}» (id={c['chat_id']})" for c in channels[:3])

    prompt = f"""{INTENT_SCHEMA}

Context:
- User: {name or 'unknown'}, chat_type: {chat_type}{ch_info}
- Current time: {datetime.now().strftime('%d.%m.%Y %H:%M')}

User message: "{text}"

Return JSON:"""

    try:
        raw = await _ask([{"role":"user","content":prompt}], max_t=500, temp=0.1, task="json")
        if not raw: return {"action": "chat", "params": {}, "confidence": 0.5}
        # Extract JSON from response
        raw = raw.strip()
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            data = json.loads(m.group())
            if "action" in data: return data
    except Exception as e:
        log.warning(f"Intent detection failed: {e}")
    return {"action": "chat", "params": {}, "confidence": 0.5}


# ═══════════════════════════════════════════════════════════
#  STT + TTS
# ═══════════════════════════════════════════════════════════
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
                    headers={"Authorization": f"Bearer {_gk('gr', GROQ_KEYS)}"},
                    data=form, timeout=aiohttp.ClientTimeout(total=60)) as r:
                    if r.status == 429: _rk("gr", GROQ_KEYS); continue
                    if r.status == 200: return (await r.json()).get("text", "").strip()
                    _rk("gr", GROQ_KEYS)
        except: _rk("gr", GROQ_KEYS)
    return None

VOICES = {
    "🇷🇺 Дмитрий": "ru-RU-DmitryNeural", "🇷🇺 Светлана": "ru-RU-SvetlanaNeural",
    "🇺🇸 Guy": "en-US-GuyNeural", "🇺🇸 Jenny": "en-US-JennyNeural",
    "🇩🇪 Conrad": "de-DE-ConradNeural", "🇫🇷 Henri": "fr-FR-HenriNeural",
    "🇯🇵 Nanami": "ja-JP-NanamiNeural", "🇺🇦 Ostap": "uk-UA-OstapNeural",
}

def _detect_lang(t):
    t = t.lower()
    if re.search(r'[а-яё]', t): return "ru"
    if re.search(r'[\u0600-\u06ff]', t): return "ar"
    if re.search(r'[\u4e00-\u9fff]', t): return "zh"
    if re.search(r'[\u3040-\u30ff]', t): return "ja"
    if re.search(r'[äöüß]', t): return "de"
    if re.search(r'[àâçéèêëîïôùûü]', t): return "fr"
    if re.search(r'[іїєґ]', t): return "uk"
    return "en"

async def do_tts(text: str, uid=0, fmt="mp3") -> Optional[bytes]:
    clean = text.strip()[:1800]
    lang = _detect_lang(clean)
    saved = Db.voice(uid) if uid else "auto"
    if saved != "auto" and saved in VOICES:
        voice = VOICES[saved]
    else:
        vm = {"ru": "ru-RU-DmitryNeural", "en": "en-US-GuyNeural",
              "de": "de-DE-ConradNeural", "fr": "fr-FR-HenriNeural",
              "ja": "ja-JP-NanamiNeural", "uk": "uk-UA-OstapNeural"}
        voice = vm.get(lang, "en-US-GuyNeural")

    chunks = [clean] if len(clean) <= 900 else _split_text(clean, 900)
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
    return b"".join(parts) if parts else None

def _split_text(text, max_len=900):
    sents = re.split(r'(?<=[.!?])\s+', text)
    chunks, cur = [], ""
    for s in sents:
        if len(cur) + len(s) < max_len: cur += (" " if cur else "") + s
        else:
            if cur: chunks.append(cur)
            cur = s
    if cur: chunks.append(cur)
    return chunks


# ═══════════════════════════════════════════════════════════
#  WEB UTILITIES (fallbacks)
# ═══════════════════════════════════════════════════════════
async def _web_search_fallback(q) -> Optional[str]:
    enc = uq(q)
    for url in [f"https://searx.be/search?q={enc}&format=json",
                f"https://priv.au/search?q={enc}&format=json",
                f"https://search.bus-hit.me/search?q={enc}&format=json"]:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        items = (await r.json(content_type=None)).get("results", [])
                        if items:
                            parts = [f"{i.get('title','')}: {i.get('content','')}" for i in items[:5]]
                            res = "\n\n".join(parts)
                            if res.strip(): return res
        except: pass
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://api.duckduckgo.com/?q={enc}&format=json&no_html=1",
                timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    t = d.get("Answer","") or d.get("AbstractText","")
                    if t: return t
    except: pass
    return None

async def _read_page_fallback(url) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"User-Agent":"Mozilla/5.0"},
                timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    html = await r.text(errors="ignore")
                    t = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL|re.I)
                    t = re.sub(r'<style[^>]*>.*?</style>', '', t, flags=re.DOTALL|re.I)
                    t = re.sub(r'<[^>]+>', ' ', t)
                    t = re.sub(r'\s+', ' ', t).strip()
                    return t[:8000]
    except: pass
    return None

async def get_weather(city) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://wttr.in/{uq(city)}?format=j1&lang=ru",
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    cur = (await r.json()).get("current_condition", [{}])[0]
                    desc = cur.get('lang_ru', [{}])[0].get('value', '')
                    return (f"🌡 {cur.get('temp_C','?')}°C (ощущается {cur.get('FeelsLikeC','?')}°C)\n"
                            f"☁️ {desc}\n"
                            f"💧 Влажность: {cur.get('humidity','?')}%\n"
                            f"💨 Ветер: {cur.get('windspeedKmph','?')} км/ч")
    except: pass
    return None

async def get_exchange(fr, to) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://open.er-api.com/v6/latest/{fr.upper()}",
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    rate = (await r.json()).get("rates", {}).get(to.upper())
                    if rate: return f"1 {fr.upper()} = {rate:.4f} {to.upper()}"
    except: pass
    return None


# ═══════════════════════════════════════════════════════════
#  SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════
def _sys_prompt(uid, chat_id, chat_type="private"):
    u = Db.user(uid)
    name = u.get("name", "")
    total = u.get("total_msgs", 0)
    mems = u.get("memory", [])
    by_cat: Dict[str, list] = {}
    for m in mems[:20]: by_cat.setdefault(m.get("cat","gen"),[]).append(m["fact"])
    mem_str = "".join(f"\n[{cat}]: {'; '.join(facts[:3])}" for cat, facts in by_cat.items())
    sums = Db.summaries(uid, chat_id)
    sum_str = ("\n\nПРЕДЫДУЩИЕ ТЕМЫ:\n" + "\n---\n".join(sums[-3:])) if sums else ""
    fam = "незнакомый"
    if total > 200: fam = "близкий друг"
    elif total > 50: fam = "хороший знакомый"
    elif total > 15: fam = "знакомый"
    h = datetime.now().hour
    tod = "ночь" if h < 5 else "утро" if h < 12 else "день" if h < 17 else "вечер"
    ctx_note = {
        "group": "\nГРУППА: отвечай кратко (1-3 предл.), без меню и кнопок.",
        "supergroup": "\nГРУППА: отвечай кратко (1-3 предл.), без меню и кнопок.",
        "channel": "\nКАНАЛ: пиши как публикацию — без обращений к пользователю."
    }.get(chat_type, "")
    channels = Db.user_channels(uid)
    ch_note = ""
    if channels:
        ch_list = ", ".join("«" + c["title"] + "» (" + str(c["chat_id"]) + ")" for c in channels[:3])
        ch_note = f"\nКАНАЛЫ ПОЛЬЗОВАТЕЛЯ: {ch_list}"
    return f"""Ты NEXUM — продвинутый персональный AI-ассистент (nexum v1.0).
Ты умеешь всё: код, аналитика, творчество, генерация медиа, управление каналами, email, Notion и многое другое.

ХАРАКТЕР: прямой, умный, естественный. Говоришь как живой человек, не как робот.
Помогаешь без отговорок. Если что-то невозможно — честно скажи почему и предложи альтернативу.
НИКОГДА не говори «я не могу» без объяснения реальной причины.{ctx_note}{ch_note}

ПОЛЬЗОВАТЕЛЬ: {f"Имя: {name}" if name else "имя неизвестно"} | Сообщений: {total} | Статус: {fam}
ПАМЯТЬ:{mem_str if mem_str else " пусто"}
{sum_str}
ВРЕМЯ: {tod}, {datetime.now().strftime('%d.%m.%Y %H:%M')}

ФОРМАТ ОТВЕТОВ:
- Короткий вопрос → кратко и точно
- Сложный вопрос → структурированно
- Без лишнего markdown если не просят код
- Эмодзи — уместно и в меру
- НЕ используй шаблонные приветствия каждый раз"""


# ═══════════════════════════════════════════════════════════
#  KEYBOARD HELPERS (minimal — only for multi-choice)
# ═══════════════════════════════════════════════════════════
def _ik(*rows): return InlineKeyboardMarkup(inline_keyboard=list(rows))
def _btn(text, data): return InlineKeyboardButton(text=text, callback_data=data)
def _url_btn(text, url): return InlineKeyboardButton(text=text, url=url)

def _confirm_kb(aid, yes_text="✅ Да", no_text="❌ Нет"):
    return _ik([_btn(yes_text, f"yes:{aid}"), _btn(no_text, f"no:{aid}")])

def _channel_select_kb(channels, action_prefix):
    rows = [[_btn(f"📺 {ch['title'][:35]}", f"{action_prefix}:{ch['chat_id']}")] for ch in channels]
    rows.append([_btn("❌ Отмена", "cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════
def _strip_md(t):
    t = re.sub(r'```\w*\n?(.*?)```', lambda m: m.group(1).strip(), t, flags=re.DOTALL)
    t = re.sub(r'`([^`]+)`', r'\1', t)
    t = re.sub(r'\*\*(.+?)\*\*', r'\1', t, flags=re.DOTALL)
    t = re.sub(r'(?<!\w)\*([^*\n]+)\*(?!\w)', r'\1', t)
    t = re.sub(r'^#{1,6}\s+(.+)$', r'\1', t, flags=re.MULTILINE)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()

async def _send_long(msg: Message, text: str, **kwargs):
    text = text.strip()
    while len(text) > 4000:
        await msg.answer(text[:4000], **kwargs); text = text[4000:]
        await asyncio.sleep(0.1); kwargs = {}  # only first chunk gets kwargs
    if text: await msg.answer(text, **kwargs)

def _set_ctx(chat_id, mode, data=None):
    INPUT_CTX[chat_id] = {"mode": mode, "data": data or {}}

def _get_ctx(chat_id) -> Optional[dict]:
    return INPUT_CTX.get(chat_id)

def _clear_ctx(chat_id):
    INPUT_CTX.pop(chat_id, None)

async def is_admin(chat_id, uid) -> bool:
    try:
        m = await bot.get_chat_member(chat_id, uid)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except: return False

async def get_group_owner(chat_id) -> Optional[int]:
    try:
        admins = await bot.get_chat_administrators(chat_id)
        for a in admins:
            if a.status == ChatMemberStatus.CREATOR:
                return a.user.id
    except: pass
    return None


# ═══════════════════════════════════════════════════════════
#  ACTION HANDLERS
# ═══════════════════════════════════════════════════════════
async def _handle_generate_image(message: Message, params: dict):
    prompt = params.get("prompt", message.text or "")
    style = params.get("style", "авто").lower()
    uid = message.from_user.id

    m2 = await message.answer(f"🎨 Генерирую изображение...")
    await bot.send_chat_action(message.chat.id, "upload_photo")

    en_prompt = await translate_to_en(prompt)
    img = await gen_img(en_prompt, style)

    try: await m2.delete()
    except: pass

    if img:
        caption = f"✨ {prompt[:80]}" + (f" ({style})" if style != "авто" else "")
        await message.answer_photo(
            BufferedInputFile(img, "nexum.jpg"),
            caption=caption,
            reply_markup=_ik([_btn("🔄 Ещё вариант", f"regen_img:{uid}"),
                               _btn("🎨 Другой стиль", f"restyle_img:{uid}")])
        )
        Db.remember(uid, f"Просил сгенерировать: {prompt[:60]}", "request", 3)
    else:
        await message.answer("Не удалось сгенерировать изображение. Попробуй другой запрос или чуть позже.")


async def _handle_generate_music(message: Message, params: dict):
    prompt = params.get("prompt", "")
    style = params.get("style", "авто").lower()
    uid = message.from_user.id
    chat_id = message.chat.id

    m2 = await message.answer(f"🎵 Создаю музыку... ⏳ ~30-90 сек")
    await bot.send_chat_action(chat_id, "upload_document")

    en_prompt = await translate_to_en(prompt)
    audio = await gen_music(en_prompt, style)

    try: await m2.delete()
    except: pass

    if audio:
        caption = f"🎵 {prompt[:60]}" + (f" [{style}]" if style != "авто" else "")
        await message.answer_audio(
            BufferedInputFile(audio, "nexum_music.flac"),
            caption=caption,
            reply_markup=_ik([_btn("🔄 Другой вариант", f"regen_music:{uid}")])
        )
    else:
        # Fallback: generate and display lyrics
        lyrics_prompt = f"Напиши текст инструментальной/лирической темы в стиле {style} на тему: {prompt}. 2 куплета и припев."
        lyrics = await _ask([{"role":"user","content":lyrics_prompt}], max_t=500, task="creative")
        await message.answer(
            f"🎵 Инструментальная генерация временно недоступна.\n\n"
            f"Вот текст песни в стиле {style}:\n\n{_strip_md(lyrics)}",
            reply_markup=_ik([_btn("🔊 Озвучить текст", f"tts_lyrics:{uid}")])
        )


async def _handle_generate_song(message: Message, params: dict):
    prompt = params.get("prompt", "")
    style = params.get("style", "авто").lower()
    uid = message.from_user.id
    chat_id = message.chat.id

    m2 = await message.answer(f"🎤 Создаю песню с вокалом... ⏳ 1-3 мин")
    await bot.send_chat_action(chat_id, "record_voice")

    # Generate lyrics first
    lyrics_prompt = f"Напиши текст песни в стиле {style} на тему: {prompt}. 2 куплета и припев. Только текст, без пояснений."
    lyrics = await _ask([{"role":"user","content":lyrics_prompt}], max_t=600, task="creative")
    clean_lyrics = _strip_md(lyrics)

    # Generate song with vocals
    audio, _ = await gen_song_with_vocals(prompt, style, clean_lyrics)

    try: await m2.delete()
    except: pass

    # Always show lyrics
    await message.answer(f"📄 Текст песни:\n\n{clean_lyrics}")

    if audio:
        await message.answer_audio(
            BufferedInputFile(audio, "nexum_song.mp3"),
            caption=f"🎵 {prompt[:60]} [{style}]"
        )
    else:
        # TTS fallback
        await message.answer("Генерация с вокалом недоступна — озвучиваю текст...")
        await bot.send_chat_action(chat_id, "record_voice")
        tts_audio = await do_tts(clean_lyrics[:1200], uid=uid)
        if tts_audio:
            await message.answer_voice(
                BufferedInputFile(tts_audio, "song.mp3"),
                caption=f"🎤 {prompt[:60]}"
            )


async def _handle_generate_video(message: Message, params: dict):
    prompt = params.get("prompt", "")
    chat_id = message.chat.id
    uid = message.from_user.id

    m2 = await message.answer(f"🎬 Генерирую видео... ⏳ до 2 мин")
    await bot.send_chat_action(chat_id, "upload_video")

    en_prompt = await translate_to_en(prompt)
    vdata = await gen_video(en_prompt)

    try: await m2.delete()
    except: pass

    if vdata:
        await message.answer_video(
            BufferedInputFile(vdata, "nexum.mp4"),
            caption=f"🎬 {prompt[:60]}",
            reply_markup=_ik([_btn("🔄 Ещё вариант", f"regen_video:{uid}")])
        )
    else:
        await message.answer("Видео генерация временно недоступна — создаю изображение...")
        await bot.send_chat_action(chat_id, "upload_photo")
        img = await gen_img(en_prompt, "реализм")
        if img:
            await message.answer_photo(
                BufferedInputFile(img, "nexum.jpg"),
                caption=f"🖼 {prompt[:60]} (изображение вместо видео)"
            )
        else:
            await message.answer("Генерация не удалась. Попробуй другой запрос.")


async def _handle_tts(message: Message, params: dict):
    text = params.get("text", message.text or "")
    uid = message.from_user.id
    if not text:
        _set_ctx(message.chat.id, "tts_input")
        await message.answer("Что озвучить?")
        return
    await bot.send_chat_action(message.chat.id, "record_voice")
    audio = await do_tts(text, uid=uid)
    if audio:
        await message.answer_voice(BufferedInputFile(audio, "nexum.mp3"))
    else:
        await message.answer("Не удалось озвучить.")


async def _handle_search(message: Message, params: dict, uid: int):
    query = params.get("query", "")
    chat_id = message.chat.id
    if not query:
        await message.answer("Что искать?")
        return
    m2 = await message.answer(f"🔍 Ищу...")
    await bot.send_chat_action(chat_id, "typing")
    results = None
    try: results = await web_search(query)
    except: results = await _web_search_fallback(query)
    try: await m2.delete()
    except: pass
    if results:
        msgs = [{"role":"system","content":_sys_prompt(uid, chat_id, message.chat.type)},
                {"role":"user","content":f"Вопрос: {query}\n\nРезультаты поиска:\n{results}\n\nОтветь точно и кратко."}]
        ans = await _ask(msgs, max_t=1500, task="analysis")
        await _send_long(message, _strip_md(ans))
    else:
        await message.answer("Ничего не нашёл. Попробуй переформулировать запрос.")


async def _handle_url(message: Message, params: dict, uid: int):
    url = params.get("url", "")
    chat_id = message.chat.id
    if not url:
        _set_ctx(chat_id, "read_url_input")
        await message.answer("Вставь ссылку:")
        return
    m2 = await message.answer("🔗 Читаю...")
    content = None
    try: content = await read_page(url)
    except: content = await _read_page_fallback(url)
    try: await m2.delete()
    except: pass
    if content:
        msgs = [{"role":"system","content":_sys_prompt(uid, chat_id, message.chat.type)},
                {"role":"user","content":f"Сайт {url}:\n{content[:5000]}\n\nКратко: что там?"}]
        ans = await _ask(msgs, max_t=1500)
        await _send_long(message, _strip_md(ans))
    else:
        await message.answer("Не смог прочитать страницу.")


async def _handle_weather(message: Message, params: dict):
    city = params.get("city", "")
    if not city:
        _set_ctx(message.chat.id, "weather_input")
        await message.answer("Какой город?")
        return
    w = await get_weather(city)
    if w:
        await message.answer(f"🌤 {city}:\n\n{w}")
    else:
        await message.answer(f"Нет данных для «{city}»")


async def _handle_currency(message: Message, params: dict):
    fr = params.get("from", "USD"); to = params.get("to", "RUB")
    r = await get_exchange(fr, to)
    if r: await message.answer(f"💱 {r}")
    else: await message.answer(f"Не нашёл курс {fr}/{to}")


async def _handle_remind(message: Message, params: dict):
    mins = int(params.get("minutes", 0))
    text = params.get("message", "")
    chat_id = message.chat.id
    if not mins:
        _set_ctx(chat_id, "remind_input")
        await message.answer("Через сколько минут напомнить и о чём?")
        return
    run_at = datetime.now() + timedelta(minutes=mins)
    scheduler.add_job(
        lambda: asyncio.create_task(bot.send_message(chat_id, f"⏰ Напоминание:\n\n{text}")),
        trigger=DateTrigger(run_date=run_at)
    )
    await message.answer(f"✅ Напомню через {mins} мин: {text[:60]}")


async def _handle_download(message: Message, params: dict):
    url = params.get("url", "")
    fmt = params.get("format", "mp3")
    chat_id = message.chat.id
    if not url:
        _set_ctx(chat_id, "dl_input")
        await message.answer("Вставь ссылку (YouTube, TikTok, Instagram, VK):")
        return
    if not YTDLP:
        await message.answer("yt-dlp не установлен.")
        return
    m2 = await message.answer(f"📥 Скачиваю {fmt.upper()}...")
    await bot.send_chat_action(chat_id, "upload_document")
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "%(title)s.%(ext)s")
        if fmt == "mp3":
            cmd = [YTDLP, "-x", "--audio-format","mp3","--audio-quality","0","-o",out,"--no-playlist","--max-filesize","45M","--no-warnings",url]
        elif fmt == "mp4":
            cmd = [YTDLP,"-f","bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best","-o",out,"--no-playlist","--max-filesize","45M","--no-warnings",url]
        else:
            cmd = [YTDLP,"-x","--audio-format","wav","-o",out,"--no-playlist","--max-filesize","45M","--no-warnings",url]
        try:
            subprocess.run(cmd, capture_output=True, timeout=300, text=True)
            files = os.listdir(tmp)
            try: await m2.delete()
            except: pass
            if files:
                fp = os.path.join(tmp, files[0])
                with open(fp, "rb") as f: data = f.read()
                if fmt == "mp3": await message.answer_audio(BufferedInputFile(data, files[0]), caption=f"🎵 {files[0][:50]}")
                elif fmt == "mp4": await message.answer_video(BufferedInputFile(data, files[0]), caption=f"🎬 {files[0][:50]}")
                else: await message.answer_document(BufferedInputFile(data, files[0]))
            else:
                await message.answer("Не удалось скачать.")
        except Exception as e:
            try: await m2.delete()
            except: pass
            await message.answer(f"Ошибка скачивания: {e}")


async def _handle_translate(message: Message, params: dict, uid: int):
    text = params.get("text", "")
    target = params.get("target_lang", "")
    lang = _detect_lang(text)
    if not target: target = "en" if lang in ("ru","uk") else "ru"
    to_name = {"ru":"русский","en":"английский","de":"немецкий","fr":"французский","ja":"японский"}.get(target, target)
    ans = await _ask([{"role":"user","content":f"Переведи на {to_name}, только перевод:\n{text}"}],
        max_t=2000, task="fast")
    await message.answer(f"🌐 {_strip_md(ans)}")


# ═══════════════════════════════════════════════════════════
#  CHANNEL HANDLERS
# ═══════════════════════════════════════════════════════════
async def _handle_channel_post(message: Message, params: dict, uid: int):
    topic = params.get("topic", "")
    channel_id = params.get("channel_id")
    channels = Db.user_channels(uid)
    if not channels:
        await message.answer("У тебя нет каналов. Добавь меня как администратора в свой канал — я пришлю уведомление сюда.")
        return
    if len(channels) == 1:
        channel_id = channels[0]["chat_id"]
    elif not channel_id:
        # Let user select channel
        await message.answer("Для какого канала?",
            reply_markup=_channel_select_kb(channels, f"post_for"))
        _set_ctx(message.chat.id, "channel_post_topic", {"topic": topic})
        return
    await _do_channel_post(message, channel_id, topic, uid)

async def _do_channel_post(message: Message, channel_id: int, topic: str, uid: int):
    ch = Db.channel(channel_id)
    style = (ch.get("style","") if ch else "") or ""
    style_note = f"Стиль канала: {style}\n\n" if style else ""
    ch_title = ch.get("title","") if ch else str(channel_id)
    m2 = await message.answer(f"📝 Пишу пост для «{ch_title}»...")
    post_prompt = (f"{style_note}Напиши Telegram пост" +
        (f" на тему: {topic}" if topic else "") +
        ".\nБез markdown, живо, цепляет с первой строки. Без заголовка.")
    post = await _ask([{"role":"user","content":post_prompt}], max_t=700, task="creative")
    post = _strip_md(post)
    try: await m2.delete()
    except: pass
    aid = f"chpost_{uid}_{int(time.time())}"
    CONFIRMS[aid] = {"type":"pub_post","channel_id":channel_id,"post":post,"uid":uid}
    await message.answer(
        f"📝 Пост для «{ch_title}»:\n\n{post}\n\n─────\nОпубликовать?",
        reply_markup=_confirm_kb(aid, "✅ Опубликовать", "✏️ Переписать")
    )

async def _handle_channel_schedule(message: Message, params: dict, uid: int):
    channels = Db.user_channels(uid)
    if not channels:
        await message.answer("Нет подключённых каналов.")
        return
    topic = params.get("topic",""); t = params.get("time","09:00")
    channel_id = params.get("channel_id")
    if len(channels) > 1 and not channel_id:
        await message.answer("Для какого канала настроить расписание?",
            reply_markup=_channel_select_kb(channels, f"sched_for"))
        _set_ctx(message.chat.id, "channel_sched", {"topic":topic,"time":t})
        return
    channel_id = channel_id or channels[0]["chat_id"]
    try:
        h, m_min = map(int, t.split(":"))
        scheduler.add_job(
            lambda ci=channel_id, tp=topic: asyncio.create_task(_auto_post(ci, tp)),
            trigger=CronTrigger(hour=h, minute=m_min),
            id=f"chsch_{channel_id}_{h}_{m_min}", replace_existing=True
        )
        ch = Db.channel(channel_id)
        with _dbc() as c:
            c.execute("INSERT INTO schedules(chat_id,hour,minute,topic)VALUES(?,?,?,?)",
                (channel_id, h, m_min, topic))
        await message.answer(f"✅ Авторасписание: каждый день в {h:02d}:{m_min:02d}\nТема: {topic or 'авто'}\nКанал: {ch['title'] if ch else channel_id}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nФормат времени: ЧЧ:ММ (например 09:00)")

async def _auto_post(chat_id, topic=""):
    try:
        ch = Db.channel(chat_id)
        style = (ch.get("style","") if ch else "") or ""
        style_note = f"Стиль: {style}\n\n" if style else ""
        post = await _ask([{"role":"user","content":
            f"{style_note}Напиши Telegram пост{' на тему: '+topic if topic else ''}. Без markdown, живо."}],
            max_t=700, task="creative")
        await bot.send_message(chat_id, _strip_md(post))
    except Exception as e: log.error(f"Auto post: {e}")


# ═══════════════════════════════════════════════════════════
#  NOTION HANDLERS
# ═══════════════════════════════════════════════════════════
async def _handle_notion_create_page(message: Message, params: dict, uid: int):
    if not notion:
        await message.answer("Notion не подключён. Добавь NOTION_TOKEN в .env файл.")
        return
    title = params.get("title","Новая страница"); content = params.get("content","")
    parent_id = Db.get_notion_page(uid)
    if not parent_id:
        await message.answer("Укажи ID страницы Notion командой /notion_page <id>")
        return
    m2 = await message.answer(f"📄 Создаю страницу в Notion...")
    result = await notion.create_page(parent_id, title, content)
    try: await m2.delete()
    except: pass
    if result:
        url = result.get("url","")
        await message.answer(
            f"✅ Страница создана!\n📄 {title}\n🔗 {url}",
            reply_markup=(_ik([_url_btn("Открыть в Notion", url)]) if url else None)
        )
    else:
        await message.answer("Не удалось создать страницу. Проверь NOTION_TOKEN и права доступа.")

async def _handle_notion_create_task(message: Message, params: dict, uid: int):
    if not notion:
        await message.answer("Notion не подключён.")
        return
    title = params.get("title",""); tags = params.get("tags",[]); status = params.get("status","Todo")
    parent_id = Db.get_notion_page(uid)
    if not parent_id:
        await message.answer("Укажи ID страницы или базы данных Notion: /notion_page <id>")
        return
    # Try as database first, then as page
    m2 = await message.answer("📋 Добавляю задачу в Notion...")
    result = await notion.add_db_item(parent_id, title, status=status, tags=tags)
    if not result:
        result = await notion.create_page(parent_id, f"[{status}] {title}")
    try: await m2.delete()
    except: pass
    if result:
        url = result.get("url","")
        tags_str = f" [{', '.join(tags)}]" if tags else ""
        await message.answer(f"✅ Задача добавлена в Notion!\n📋 {title}{tags_str}\n🔗 {url}")
    else:
        await message.answer("Не удалось добавить задачу.")

async def _handle_notion_read(message: Message, params: dict, uid: int):
    if not notion:
        await message.answer("Notion не подключён.")
        return
    query = params.get("query","")
    m2 = await message.answer("🔍 Ищу в Notion...")
    results = await notion.search(query, limit=5)
    try: await m2.delete()
    except: pass
    if results:
        lines = []
        for r in results:
            title = r.get("properties",{}).get("Name",{}).get("title",[{}])[0].get("plain_text","") or "Без названия"
            url = r.get("url","")
            lines.append(f"📄 {title}\n🔗 {url}")
        await message.answer("Найдено в Notion:\n\n" + "\n\n".join(lines))
    else:
        await message.answer("Ничего не найдено в Notion.")


# ═══════════════════════════════════════════════════════════
#  ADMIN ACTIONS (destructive → send confirmation to admin)
# ═══════════════════════════════════════════════════════════
async def _handle_admin_action(message: Message, params: dict, uid: int):
    action_type = params.get("type","")
    target = params.get("target","")
    desc = params.get("description","")
    chat_id = message.chat.id
    ct = message.chat.type

    # Find who to notify
    notify_uid = None
    if ct in ("group","supergroup"):
        notify_uid = await get_group_owner(chat_id)
    else:
        notify_uid = uid  # In private — ask the user themselves

    action_desc = desc or f"{action_type}: {target}"
    aid = f"adm_{uid}_{int(time.time())}"
    CONFIRMS[aid] = {"type":"admin_action","action_type":action_type,
                     "target":target,"chat_id":chat_id,"requester_uid":uid}

    if notify_uid and notify_uid != uid:
        try:
            requester = message.from_user
            req_name = requester.first_name or "Пользователь"
            req_username = f"@{requester.username}" if requester.username else str(uid)
            await bot.send_message(notify_uid,
                f"⚠️ Запрос на важное действие!\n\n"
                f"Пользователь: {req_name} ({req_username})\n"
                f"Действие: {action_desc}\n"
                f"Чат: {message.chat.title or chat_id}\n\n"
                f"Разрешить?",
                reply_markup=_confirm_kb(aid, "✅ Разрешить", "❌ Запретить")
            )
            await message.answer("⏳ Запрос отправлен администратору. Жду подтверждения.")
        except:
            await message.answer("⚠️ Не смог уведомить администратора.")
    else:
        # Ask user themselves
        await message.answer(
            f"⚠️ Подтверди действие:\n\n{action_desc}",
            reply_markup=_confirm_kb(aid)
        )


async def _execute_admin_action(action_type: str, target: str, chat_id: int):
    """Execute approved admin action."""
    if action_type == "delete_messages":
        with _dbc() as c:
            if target:
                # Try to find by username
                stats = c.execute("SELECT uid,msg_id FROM grp_msgs WHERE chat_id=? AND uid IN (SELECT uid FROM grp_stats WHERE chat_id=? AND username=?)",
                    (chat_id, chat_id, target.lstrip("@"))).fetchall()
            else:
                stats = c.execute("SELECT msg_id FROM grp_msgs WHERE chat_id=? AND msg_id IS NOT NULL", (chat_id,)).fetchall()
        msg_ids = [r[1] if len(r) > 1 else r[0] for r in stats if (r[1] if len(r) > 1 else r[0])]
        deleted = 0
        for batch in [msg_ids[i:i+100] for i in range(0, len(msg_ids), 100)]:
            try:
                await bot.delete_messages(chat_id, batch)
                deleted += len(batch)
                await asyncio.sleep(0.3)
            except: pass
        return f"Удалено {deleted} сообщений"
    return "Действие выполнено"



# ═══════════════════════════════════════════════════════════
#  CALLBACK HANDLERS
# ═══════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("yes:"))
async def cb_yes(cb: CallbackQuery):
    aid = cb.data[4:]
    data = CONFIRMS.pop(aid, None)
    if not data:
        await cb.answer("Уже обработано или устарело", show_alert=True)
        return
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("✅ Подтверждено")

    t = data.get("type", "")

    if t == "admin_action":
        m = await cb.message.answer("⏳ Выполняю...")
        result = await _execute_admin_action(
            data["action_type"], data["target"], data["chat_id"]
        )
        try: await m.delete()
        except: pass
        await cb.message.answer(f"✅ {result}")
        # Notify requester
        req = data.get("requester_uid")
        if req and req != cb.from_user.id:
            try:
                await bot.send_message(req, f"✅ Администратор подтвердил: {result}")
            except: pass

    elif t == "channel_post":
        ch_id = data.get("channel_id")
        text = data.get("text", "")
        photo = data.get("photo")
        m = await cb.message.answer("📤 Публикую...")
        try:
            if photo:
                await bot.send_photo(ch_id, photo, caption=text)
            else:
                await bot.send_message(ch_id, text)
            try: await m.delete()
            except: pass
            await cb.message.answer("✅ Опубликовано!")
        except Exception as e:
            await cb.message.answer(f"❌ Ошибка: {e}")

    elif t == "schedule":
        ch_id = data.get("channel_id")
        text = data.get("text", "")
        when = data.get("when", "")
        aid2 = str(uuid.uuid4())[:8]
        with _dbc() as c:
            c.execute(
                "INSERT INTO schedules(id,uid,channel_id,text,cron,next_run,enabled) VALUES(?,?,?,?,?,?,1)",
                (aid2, cb.from_user.id, ch_id, text, when, when)
            )
        try:
            dt = datetime.fromisoformat(when)
            scheduler.add_job(
                _auto_post, "date", run_date=dt,
                args=[ch_id, text], id=aid2, replace_existing=True
            )
        except: pass
        await cb.message.answer(f"✅ Запланировано на {when}")


@dp.callback_query(F.data.startswith("no:"))
async def cb_no(cb: CallbackQuery):
    aid = cb.data[3:]
    data = CONFIRMS.pop(aid, None)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("❌ Отклонено")
    await cb.message.answer("Действие отменено.")
    if data:
        req = data.get("requester_uid")
        if req and req != cb.from_user.id:
            try:
                await bot.send_message(req, "❌ Администратор отклонил запрос.")
            except: pass


@dp.callback_query(F.data.startswith("post_for:"))
async def cb_post_for(cb: CallbackQuery):
    _, ch_id_str = cb.data.split(":", 1)
    ch_id = int(ch_id_str)
    uid = cb.from_user.id
    ctx = INPUT_CTX.pop(uid, {})
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer()
    text = ctx.get("text", "")
    fake_msg = cb.message
    if text:
        class _FM:
            chat = cb.message.chat
            from_user = cb.from_user
            async def answer(self, *a, **kw): return await cb.message.answer(*a, **kw)
        await _do_channel_post(_FM(), ch_id, text)
    else:
        await cb.message.answer("Нет текста для публикации.")


@dp.callback_query(F.data.startswith("sched_for:"))
async def cb_sched_for(cb: CallbackQuery):
    _, ch_id_str = cb.data.split(":", 1)
    ch_id = int(ch_id_str)
    uid = cb.from_user.id
    ctx = INPUT_CTX.pop(uid, {})
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer()
    text = ctx.get("text", "")
    when = ctx.get("when", "")
    if not text or not when:
        await cb.message.answer("Нет данных для планирования.")
        return
    aid = str(uuid.uuid4())[:8]
    with _dbc() as c:
        c.execute(
            "INSERT INTO schedules(id,uid,channel_id,text,cron,next_run,enabled) VALUES(?,?,?,?,?,?,1)",
            (aid, uid, ch_id, text, when, when)
        )
    try:
        dt = datetime.fromisoformat(when)
        scheduler.add_job(
            _auto_post, "date", run_date=dt,
            args=[ch_id, text], id=aid, replace_existing=True
        )
        await cb.message.answer(f"✅ Запланировано на {dt.strftime('%d.%m.%Y %H:%M')}")
    except Exception as e:
        await cb.message.answer(f"✅ Запланировано (планировщик: {e})")


@dp.callback_query(F.data.startswith("regen_img:"))
async def cb_regen_img(cb: CallbackQuery):
    prompt = cb.data[len("regen_img:"):]
    await cb.answer("🔄 Генерирую заново...")
    await cb.message.edit_reply_markup(reply_markup=None)
    m = await cb.message.answer("🎨 Генерирую новое изображение...")
    data = await gen_img(prompt, "авто")
    try: await m.delete()
    except: pass
    if data:
        await cb.message.answer_photo(
            BufferedInputFile(data, "img.jpg"),
            reply_markup=_ik([_btn("🔄 Другое", f"regen_img:{prompt[:60]}")])
        )
    else:
        await cb.message.answer("Не смог сгенерировать.")


@dp.callback_query(F.data.startswith("regen_music:"))
async def cb_regen_music(cb: CallbackQuery):
    prompt = cb.data[len("regen_music:"):]
    await cb.answer("🔄 Генерирую заново...")
    await cb.message.edit_reply_markup(reply_markup=None)
    m = await cb.message.answer("🎵 Генерирую новую музыку...")
    data = await gen_music(prompt, "авто")
    try: await m.delete()
    except: pass
    if data:
        await cb.message.answer_audio(
            BufferedInputFile(data, "music.mp3"),
            caption="🎵 Вот новый вариант!",
            reply_markup=_ik([_btn("🔄 Ещё", f"regen_music:{prompt[:60]}")])
        )
    else:
        await cb.message.answer("Не смог сгенерировать.")


@dp.callback_query(F.data.startswith("regen_video:"))
async def cb_regen_video(cb: CallbackQuery):
    prompt = cb.data[len("regen_video:"):]
    await cb.answer("🔄 Генерирую заново...")
    await cb.message.edit_reply_markup(reply_markup=None)
    m = await cb.message.answer("🎬 Генерирую новое видео... это займёт до 2 минут")
    data = await gen_video(prompt)
    try: await m.delete()
    except: pass
    if data:
        await cb.message.answer_video(
            BufferedInputFile(data, "video.mp4"),
            caption="🎬 Вот новый вариант!",
            reply_markup=_ik([_btn("🔄 Ещё", f"regen_video:{prompt[:60]}")])
        )
    else:
        await cb.message.answer("Не смог сгенерировать видео.")


# ═══════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════

@dp.message(Command("start"))
async def cmd_start(message: Message):
    uid = message.from_user.id
    db.upsert_user(uid, message.from_user.username, message.from_user.first_name)
    await message.answer(
        "👋 Привет! Я **NEXUM** — твой AI-ассистент.\n\n"
        "Я умею:\n"
        "🎨 Генерировать изображения\n"
        "🎵 Создавать музыку (инструментал, вокал)\n"
        "🎬 Генерировать видео\n"
        "📋 Работать с Notion\n"
        "📢 Управлять каналами\n"
        "🌐 Искать в интернете\n"
        "🗣️ Распознавать и синтезировать речь\n\n"
        "Просто напиши мне что нужно — я сам разберусь!"
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🤖 **NEXUM v1.0** — что я умею:\n\n"
        "**Медиа:**\n"
        "• Нарисуй/сгенерируй изображение [описание]\n"
        "• Создай музыку/мелодию [описание]\n"
        "• Сгенерируй видео [описание]\n"
        "• Озвучь текст / прочитай\n\n"
        "**Информация:**\n"
        "• Найди/поищи [запрос]\n"
        "• Погода в [городе]\n"
        "• Курс [валюты]\n"
        "• Переведи [текст] на [язык]\n\n"
        "**Notion:**\n"
        "• Создай страницу в Notion [название]\n"
        "• Добавь задачу в Notion [название]\n"
        "• Найди в Notion [запрос]\n\n"
        "**Каналы:**\n"
        "• Опубликуй в канале [текст]\n"
        "• Запланируй пост на [дата/время]\n\n"
        "**Просто общайся** — я умный :)"
    )


@dp.message(Command("notion_page"))
async def cmd_notion_page(message: Message):
    uid = message.from_user.id
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        current = db.get_notion_page(uid)
        if current:
            await message.answer(f"Текущая Notion страница: `{current}`\n\nЧтобы сменить: `/notion_page PAGE_ID`")
        else:
            await message.answer("Notion страница не задана.\n\nИспользуй: `/notion_page PAGE_ID`")
        return
    page_id = args[1].strip()
    db.set_notion_page(uid, page_id)
    await message.answer(f"✅ Notion страница сохранена: `{page_id}`")


# ═══════════════════════════════════════════════════════════
#  CHANNEL ADD HANDLER (my_chat_member)
# ═══════════════════════════════════════════════════════════

@dp.my_chat_member()
async def on_added(update: ChatMemberUpdated):
    new = update.new_chat_member
    # Bot added to channel or group
    if new.status in ("member", "administrator") and new.user.id == bot.id:
        chat = update.chat
        uid = update.from_user.id if update.from_user else None
        if not uid:
            return
        # Register channel
        ch_name = chat.username or chat.title or str(chat.id)
        with _dbc() as c:
            c.execute(
                "INSERT OR REPLACE INTO channels(channel_id,uid,username,title,added_at) VALUES(?,?,?,?,datetime('now'))",
                (chat.id, uid, ch_name, chat.title or "")
            )
        CHANNEL_ADMINS[chat.id] = uid
        # Notify in DM (not in channel)
        try:
            await bot.send_message(
                uid,
                f"✅ Бот добавлен в канал/группу **{chat.title or ch_name}**\n"
                f"ID: `{chat.id}`\n\n"
                f"Теперь ты можешь управлять им через личку!\n"
                f"Просто напиши: 'опубликуй в канале ...'"
            )
        except: pass


# ═══════════════════════════════════════════════════════════
#  MEDIA HANDLERS
# ═══════════════════════════════════════════════════════════

@dp.message(F.voice | F.audio)
async def on_voice(message: Message):
    uid = message.from_user.id
    db.upsert_user(uid, message.from_user.username, message.from_user.first_name)
    m = await message.answer("🎤 Распознаю речь...")
    try:
        file_obj = message.voice or message.audio
        f = await bot.get_file(file_obj.file_id)
        buf = io.BytesIO()
        await bot.download_file(f.file_path, buf)
        buf.seek(0)
        text = await stt(buf.read())
        try: await m.delete()
        except: pass
        if not text:
            await message.answer("Не смог распознать речь.")
            return
        await message.answer(f"🎤 Распознано: _{text}_")
        # Check if music recognition
        if hasattr(message, 'audio') and message.audio and music_recognition:
            try:
                result = await music_recognition.identify_from_bytes(buf.getvalue())
                if result:
                    await message.answer(f"🎵 Это: **{result.get('title','')}** — {result.get('artist','')}")
                    return
            except: pass
        # Process as text intent
        fake = type('M', (), {
            'text': text, 'from_user': message.from_user,
            'chat': message.chat, 'message_id': message.message_id,
            'answer': message.answer, 'reply_to_message': None
        })()
        await _process_intent(fake, uid, text)
    except Exception as e:
        try: await m.delete()
        except: pass
        await message.answer(f"Ошибка: {e}")


@dp.message(F.photo)
async def on_photo(message: Message):
    uid = message.from_user.id
    db.upsert_user(uid, message.from_user.username, message.from_user.first_name)
    caption = message.caption or ""
    m = await message.answer("🖼️ Анализирую изображение...")
    try:
        photo = message.photo[-1]
        f = await bot.get_file(photo.file_id)
        buf = io.BytesIO()
        await bot.download_file(f.file_path, buf)
        img_bytes = buf.getvalue()
        prompt = caption if caption else "Опиши что на изображении подробно."
        history = db.get_conv(uid, limit=4)
        reply = await _gemini_vision(prompt, img_bytes, history)
        try: await m.delete()
        except: pass
        if reply:
            db.save_conv(uid, "user", f"[фото] {caption}")
            db.save_conv(uid, "assistant", reply)
            await _send_long(message, reply)
        else:
            await message.answer("Не смог проанализировать изображение.")
    except Exception as e:
        try: await m.delete()
        except: pass
        await message.answer(f"Ошибка: {e}")


@dp.message(F.video | F.video_note | F.animation)
async def on_video(message: Message):
    await message.answer("🎬 Видео получено! Пока я не умею анализировать видео, но могу создать его по описанию.")


@dp.message(F.document)
async def on_document(message: Message):
    uid = message.from_user.id
    db.upsert_user(uid, message.from_user.username, message.from_user.first_name)
    caption = message.caption or ""
    doc = message.document
    # Try to read text documents
    if doc.mime_type and doc.mime_type.startswith("text/"):
        m = await message.answer("📄 Читаю документ...")
        try:
            f = await bot.get_file(doc.file_id)
            buf = io.BytesIO()
            await bot.download_file(f.file_path, buf)
            content = buf.getvalue().decode("utf-8", errors="replace")[:4000]
            prompt = caption if caption else "Проанализируй этот документ и дай краткое резюме."
            full_prompt = f"{prompt}\n\nСодержание:\n{content}"
            reply = await _ask(full_prompt, uid)
            try: await m.delete()
            except: pass
            await _send_long(message, reply)
        except Exception as e:
            await message.answer(f"Не смог прочитать: {e}")
    else:
        await message.answer(f"📎 Файл получен: {doc.file_name}\nЕсли нужно что-то с ним сделать — уточни!")


# ═══════════════════════════════════════════════════════════
#  MAIN TEXT HANDLER — INTENT ROUTING
# ═══════════════════════════════════════════════════════════

async def _process_intent(message, uid: int, text: str):
    """Core routing logic — detects intent and calls handler."""
    chat_type = getattr(getattr(message, 'chat', None), 'type', 'private')

    # Detect intent via AI
    intent = await detect_intent(text, uid, chat_type)
    action = intent.get("action", "chat")
    params = intent.get("params", {})
    confidence = intent.get("confidence", 0.5)

    # Low confidence or unknown → treat as chat
    if confidence < 0.4 and action != "chat":
        action = "chat"

    handlers = {
        "generate_image": _handle_generate_image,
        "generate_music": _handle_generate_music,
        "generate_song": _handle_generate_song,
        "generate_video": _handle_generate_video,
        "tts": _handle_tts,
        "search": _handle_search,
        "url": _handle_url,
        "weather": _handle_weather,
        "currency": _handle_currency,
        "remind": _handle_remind,
        "download": _handle_download,
        "translate": _handle_translate,
        "channel_post": _handle_channel_post,
        "channel_schedule": _handle_channel_schedule,
        "notion_create_page": _handle_notion_create_page,
        "notion_create_task": _handle_notion_create_task,
        "notion_read": _handle_notion_read,
        "admin_action": _handle_admin_action,
    }

    handler = handlers.get(action)
    if handler:
        await handler(message, params, uid)
    else:
        # Default: smart chat
        history = db.get_conv(uid, limit=10)
        sys = _sys_prompt(uid)
        reply = await _ask(text, uid, system=sys, history=history)
        db.save_conv(uid, "user", text)
        db.save_conv(uid, "assistant", reply)
        await _send_long(message, reply)


@dp.message(F.text)
async def on_text(message: Message):
    uid = message.from_user.id
    db.upsert_user(uid, message.from_user.username, message.from_user.first_name)
    text = message.text.strip()

    # Ignore bot commands (handled separately)
    if text.startswith("/"):
        return

    # Group: only respond to mentions or replies
    chat_type = message.chat.type
    if chat_type in ("group", "supergroup"):
        is_mention = False
        if message.entities:
            for e in message.entities:
                if e.type == "mention":
                    mentioned = text[e.offset:e.offset + e.length]
                    me = await bot.get_me()
                    if me.username and f"@{me.username}" in mentioned:
                        is_mention = True
                        text = text.replace(f"@{me.username}", "").strip()
                        break
        # Also respond if reply to bot message
        is_reply_to_bot = False
        if message.reply_to_message and message.reply_to_message.from_user:
            me = await bot.get_me()
            if message.reply_to_message.from_user.id == me.id:
                is_reply_to_bot = True
        if not is_mention and not is_reply_to_bot:
            # Save group message for stats
            with _dbc() as c:
                try:
                    c.execute(
                        "INSERT OR IGNORE INTO grp_msgs(chat_id,uid,msg_id,text,ts) VALUES(?,?,?,?,datetime('now'))",
                        (message.chat.id, uid, message.message_id, text[:500])
                    )
                    uname = message.from_user.username or ""
                    c.execute(
                        "INSERT INTO grp_stats(chat_id,uid,username,msg_count) VALUES(?,?,?,1) "
                        "ON CONFLICT(chat_id,uid) DO UPDATE SET msg_count=msg_count+1, username=excluded.username",
                        (message.chat.id, uid, uname)
                    )
                except: pass
            return

    await _process_intent(message, uid, text)


# ═══════════════════════════════════════════════════════════
#  STARTUP & MAIN
# ═══════════════════════════════════════════════════════════

async def restore_schedules():
    """Reload pending schedules from DB after restart."""
    with _dbc() as c:
        rows = c.execute(
            "SELECT id,channel_id,text,cron,next_run FROM schedules WHERE enabled=1"
        ).fetchall()
    now = datetime.now()
    for r in rows:
        sid, ch_id, text, cron, next_run_str = r
        try:
            run_dt = datetime.fromisoformat(next_run_str)
            if run_dt > now:
                scheduler.add_job(
                    _auto_post, "date", run_date=run_dt,
                    args=[ch_id, text], id=sid, replace_existing=True
                )
        except:
            # Try as cron expression
            try:
                parts = next_run_str.split()
                if len(parts) == 5:
                    scheduler.add_job(
                        _auto_post, "cron",
                        minute=parts[0], hour=parts[1],
                        day=parts[2], month=parts[3], day_of_week=parts[4],
                        args=[ch_id, text], id=sid, replace_existing=True
                    )
            except: pass


async def register_commands():
    """Register bot commands for / suggestions in Telegram."""
    from aiogram.types import BotCommand
    commands = [
        BotCommand(command="start", description="Начать / помощь"),
        BotCommand(command="help", description="Список возможностей"),
        BotCommand(command="notion_page", description="Задать Notion страницу"),
    ]
    await bot.set_my_commands(commands)


async def main():
    import nexum_config as cfg
    cfg.check_keys()

    db.init()
    await restore_schedules()
    scheduler.start()
    await register_commands()

    logger.info("NEXUM v1.0 starting...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
