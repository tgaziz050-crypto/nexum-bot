"""
NEXUM v1.0 — AI Telegram Bot
Управление через естественный язык. Без кнопок. Поддержка нескольких каналов, Notion, согласование опасных действий.
"""
import asyncio
import logging
import os
import tempfile
import base64
import random
import aiohttp
import subprocess
import shutil
import sqlite3
import re
import time
import json
from urllib.parse import quote as uq
from datetime import datetime
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv
load_dotenv()

if not os.path.exists(".env"):
    print("ERROR: .env не найден. Скопируй config.example.env в .env и заполни BOT_TOKEN.")
    exit(1)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN не задан в .env")
    exit(1)

GEMINI_KEYS = [k for k in [os.getenv("G1"), os.getenv("G2"), os.getenv("G3"), os.getenv("G4")] if k]
GROQ_KEYS = [k for k in [os.getenv("GR1"), os.getenv("GR2"), os.getenv("GR3"), os.getenv("GR4")] if k]
DS_KEYS = [k for k in [os.getenv("DS1"), os.getenv("DS2"), os.getenv("DS3")] if k]
REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN", "").strip()

if not (GEMINI_KEYS or GROQ_KEYS or DS_KEYS):
    print("WARNING: Нет AI ключей (G1, GR1, DS1). Бот запустится с ограничениями.")

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("NEXUM")

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.enums import ChatMemberStatus

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

FFMPEG = shutil.which("ffmpeg")
YTDLP = shutil.which("yt-dlp")

_ki: Dict[str, int] = {p: 0 for p in ["g", "gr", "ds"]}

def gk(p, keys):
    if not keys:
        return None
    return keys[_ki[p] % len(keys)]

def rk(p, keys):
    if keys:
        _ki[p] = (_ki[p] + 1) % len(keys)

try:
    from nexum_music_recognition import recognize_music, format_music_info
except ImportError:
    recognize_music = lambda _: None
    format_music_info = lambda _: "Распознавание музыки: добавь AUDD_API_KEY в .env"

try:
    from nexum_notion import create_page as notion_create_page, is_configured as notion_configured
except ImportError:
    notion_create_page = lambda *a, **k: None
    notion_configured = lambda: False

from nexum_approval import (
    add_pending, get_pending, pop_pending, create_approval_id, get_admin_ids,
    ApprovalRequest
)
from nexum_context import get_chat_context, is_dangerous_action

DB = "nexum.db"

def init_db():
    with sqlite3.connect(DB) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            uid INTEGER PRIMARY KEY, name TEXT DEFAULT '', username TEXT DEFAULT '',
            lang TEXT DEFAULT 'ru', voice TEXT DEFAULT 'auto',
            first_seen TEXT, last_seen TEXT, total_msgs INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS conv(
            id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, chat_id INTEGER,
            role TEXT, content TEXT, ts TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS memory(
            id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, cat TEXT, fact TEXT, imp INTEGER DEFAULT 5
        );
        CREATE TABLE IF NOT EXISTS summaries(
            id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, chat_id INTEGER, text TEXT
        );
        CREATE TABLE IF NOT EXISTS grp_msgs(
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, uid INTEGER, msg_id INTEGER,
            text TEXT DEFAULT '', mtype TEXT DEFAULT 'text', ts TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS grp_stats(
            chat_id INTEGER, uid INTEGER, name TEXT DEFAULT '', username TEXT DEFAULT '',
            msgs INTEGER DEFAULT 0, words INTEGER DEFAULT 0, PRIMARY KEY(chat_id, uid)
        );
        CREATE TABLE IF NOT EXISTS channels(
            chat_id INTEGER PRIMARY KEY, title TEXT, analysis TEXT DEFAULT '', style TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS user_channels(uid INTEGER, chat_id INTEGER, PRIMARY KEY(uid, chat_id));
        CREATE TABLE IF NOT EXISTS schedules(
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, hour INTEGER, minute INTEGER,
            topic TEXT, active INTEGER DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS ic ON conv(uid, chat_id);
        CREATE INDEX IF NOT EXISTS im ON memory(uid);
        CREATE INDEX IF NOT EXISTS ig ON grp_msgs(chat_id);
        """)
    log.info("Database ready")

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
            if not r:
                return {}
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
        with dbc() as c:
            c.execute("UPDATE users SET voice=? WHERE uid=?", (v, uid))

    @staticmethod
    def remember(uid, fact, cat="gen", imp=5):
        with dbc() as c:
            rows = c.execute("SELECT id,fact FROM memory WHERE uid=? AND cat=?", (uid, cat)).fetchall()
            for rid, ef in rows:
                aw = set(fact.lower().split())
                bw = set(ef.lower().split())
                if aw and bw and len(aw & bw) / len(aw | bw) > 0.65:
                    c.execute("UPDATE memory SET fact=? WHERE id=?", (fact, rid))
                    return
            c.execute("INSERT INTO memory(uid,cat,fact,imp)VALUES(?,?,?,?)", (uid, cat, fact, imp))

    @staticmethod
    def extract_facts(uid, text):
        pats = [
            (r'меня зовут\s+([А-ЯЁа-яёA-Za-z]{2,20})', 'name', 10),
            (r'мне\s+(\d{1,2})\s*(?:год|лет)', 'age', 9),
        ]
        for p, cat, imp in pats:
            m = re.search(p, text, re.I)
            if m:
                Db.remember(uid, m.group(0).strip(), cat, imp)

    @staticmethod
    def history(uid, chat_id, n=35):
        with dbc() as c:
            rows = c.execute(
                "SELECT role,content FROM conv WHERE uid=? AND chat_id=? ORDER BY id DESC LIMIT ?",
                (uid, chat_id, n)).fetchall()
        return list(reversed(rows))

    @staticmethod
    def add(uid, chat_id, role, content):
        with dbc() as c:
            c.execute("INSERT INTO conv(uid,chat_id,role,content)VALUES(?,?,?,?)",
                      (uid, chat_id, role, content))
            if role == "user":
                c.execute("UPDATE users SET total_msgs=total_msgs+1 WHERE uid=?", (uid,))

    @staticmethod
    def clear(uid, chat_id):
        with dbc() as c:
            c.execute("DELETE FROM conv WHERE uid=? AND chat_id=?", (uid, chat_id))

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
            c.execute("""INSERT INTO grp_stats(chat_id,uid,name,username,msgs,words,last_active,first_seen)
                VALUES(?,?,?,?,1,?,?,?)
                ON CONFLICT(chat_id,uid) DO UPDATE SET msgs=msgs+1, words=words+?,
                last_active=excluded.last_active""",
                (chat_id, uid, name, username, w, now, now, w))
            if msg_id:
                c.execute("INSERT INTO grp_msgs(chat_id,uid,msg_id,text,mtype)VALUES(?,?,?,?,?)",
                          (chat_id, uid, msg_id, (text or "")[:500], mtype))

    @staticmethod
    def grp_msgs(chat_id, n=200):
        with dbc() as c:
            rows = c.execute(
                "SELECT uid,msg_id,text,mtype FROM grp_msgs WHERE chat_id=? ORDER BY id DESC LIMIT ?",
                (chat_id, n)).fetchall()
        return list(reversed([dict(r) for r in rows]))

    @staticmethod
    def channel(chat_id):
        with dbc() as c:
            r = c.execute("SELECT * FROM channels WHERE chat_id=?", (chat_id,)).fetchone()
            return dict(r) if r else None

    @staticmethod
    def channels_all() -> List[dict]:
        with dbc() as c:
            return [dict(r) for r in c.execute("SELECT * FROM channels").fetchall()]

    @staticmethod
    def save_channel(chat_id, title, analysis, style):
        with dbc() as c:
            c.execute("""INSERT INTO channels(chat_id,title,analysis,style)VALUES(?,?,?,?)
                ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, analysis=excluded.analysis, style=excluded.style""",
                (chat_id, title, analysis, style))

    @staticmethod
    def user_channels(uid) -> List[int]:
        with dbc() as c:
            return [r[0] for r in c.execute("SELECT chat_id FROM user_channels WHERE uid=?", (uid,)).fetchall()]

    @staticmethod
    def add_user_channel(uid, chat_id):
        with dbc() as c:
            c.execute("INSERT OR IGNORE INTO user_channels(uid,chat_id)VALUES(?,?)", (uid, chat_id))


async def _gemini(msgs, model="gemini-2.0-flash-exp", max_t=4096, temp=0.85):
    if not GEMINI_KEYS:
        return None
    sys_txt = ""
    contents = []
    for m in msgs:
        if m["role"] == "system":
            sys_txt = m["content"]
        elif m["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": m["content"]}]})
        else:
            contents.append({"role": "model", "parts": [{"text": m["content"]}]})
    if not contents:
        return None
    body = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_t, "temperature": temp},
        "safetySettings": [{"category": c, "threshold": "BLOCK_NONE"} for c in
                          ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
                           "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
    }
    if sys_txt:
        body["systemInstruction"] = {"parts": [{"text": sys_txt}]}
    for _ in range(len(GEMINI_KEYS)):
        key = gk("g", GEMINI_KEYS)
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json=body, timeout=aiohttp.ClientTimeout(total=50)) as r:
                    if r.status in (429, 500, 503):
                        rk("g", GEMINI_KEYS)
                        continue
                    if r.status == 200:
                        d = await r.json()
                        try:
                            return d["candidates"][0]["content"]["parts"][0]["text"]
                        except (KeyError, IndexError):
                            pass
                    rk("g", GEMINI_KEYS)
        except Exception:
            rk("g", GEMINI_KEYS)
    return None

async def _gemini_vision(b64, prompt, mime="image/jpeg"):
    if not GEMINI_KEYS:
        return None
    body = {
        "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime, "data": b64}}]}],
        "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.7},
        "safetySettings": [{"category": c, "threshold": "BLOCK_NONE"} for c in
                          ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
                           "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
    }
    for _ in range(len(GEMINI_KEYS)):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={gk('g', GEMINI_KEYS)}"
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json=body, timeout=aiohttp.ClientTimeout(total=40)) as r:
                    if r.status == 200:
                        d = await r.json()
                        try:
                            return d["candidates"][0]["content"]["parts"][0]["text"]
                        except (KeyError, IndexError):
                            pass
                    rk("g", GEMINI_KEYS)
        except Exception:
            rk("g", GEMINI_KEYS)
    return None

async def _groq(msgs, model="llama-3.3-70b-versatile", max_t=2048, temp=0.8):
    if not GROQ_KEYS:
        return None
    for _ in range(len(GROQ_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {gk('gr', GROQ_KEYS)}"},
                    json={"model": model, "messages": msgs, "max_tokens": max_t, "temperature": temp},
                    timeout=aiohttp.ClientTimeout(total=35)) as r:
                    if r.status == 429:
                        rk("gr", GROQ_KEYS)
                        continue
                    if r.status == 200:
                        return (await r.json())["choices"][0]["message"]["content"]
                    rk("gr", GROQ_KEYS)
        except Exception:
            rk("gr", GROQ_KEYS)
    return None

async def _ds(msgs, max_t=4096, temp=0.8):
    if not DS_KEYS:
        return None
    for _ in range(len(DS_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.deepseek.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {gk('ds', DS_KEYS)}"},
                    json={"model": "deepseek-chat", "messages": msgs, "max_tokens": max_t, "temperature": temp},
                    timeout=aiohttp.ClientTimeout(total=55)) as r:
                    if r.status == 429:
                        rk("ds", DS_KEYS)
                        continue
                    if r.status == 200:
                        return (await r.json())["choices"][0]["message"]["content"]
                    rk("ds", DS_KEYS)
        except Exception:
            rk("ds", DS_KEYS)
    return None

async def ask(msgs, max_t=4096, temp=0.85) -> str:
    for pname, keys, fn in [
        ("g", GEMINI_KEYS, lambda: _gemini(msgs, max_t=max_t, temp=temp)),
        ("gr", GROQ_KEYS, lambda: _groq(msgs, max_t=min(max_t, 2048), temp=temp)),
        ("ds", DS_KEYS, lambda: _ds(msgs, max_t=max_t, temp=temp)),
    ]:
        if not keys:
            continue
        try:
            r = await fn()
            if r and r.strip():
                return r
        except Exception as e:
            log.warning(f"AI {pname}: {e}")
    raise Exception("AI временно недоступен. Попробуй позже.")

async def stt(path) -> Optional[str]:
    if not GROQ_KEYS:
        return None
    try:
        with open(path, "rb") as f:
            data = f.read()
        ext = os.path.splitext(path)[1] or ".ogg"
        ct = "audio/ogg" if "ogg" in ext else "audio/mpeg"
        async with aiohttp.ClientSession() as s:
            form = aiohttp.FormData()
            form.add_field("file", data, filename=f"audio{ext}", content_type=ct)
            form.add_field("model", "whisper-large-v3")
            async with s.post("https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {gk('gr', GROQ_KEYS)}"},
                data=form, timeout=aiohttp.ClientTimeout(total=60)) as r:
                if r.status == 200:
                    return (await r.json()).get("text", "").strip()
    except Exception as e:
        log.error(f"STT: {e}")
    return None

VOICES = {
    "ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural",
    "en-US-GuyNeural", "en-US-JennyNeural",
}
def detect_lang(t):
    t = t.lower()
    if re.search(r'[а-яё]', t):
        return "ru-RU-DmitryNeural"
    return "en-US-GuyNeural"

async def do_tts(text: str, uid=0, fmt="mp3") -> Optional[bytes]:
    clean = text.strip()[:1800]
    voice = Db.voice(uid) if uid else "auto"
    if voice == "auto" or voice not in VOICES:
        voice = detect_lang(clean)
    try:
        import edge_tts
        comm = edge_tts.Communicate(clean, voice, rate="+5%")
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            p = tmp.name
        await comm.save(p)
        if os.path.exists(p) and os.path.getsize(p) > 300:
            with open(p, "rb") as f:
                data = f.read()
            try:
                os.unlink(p)
            except Exception:
                pass
            return data
    except Exception as e:
        log.error(f"TTS: {e}")
    return None

async def tr_en(text):
    if not re.search(r'[а-яёА-ЯЁ]', text):
        return text
    try:
        r = await _gemini([{"role": "user", "content": f"Translate to English only, no explanation:\n{text}"}], max_t=100, temp=0.1)
        if r:
            return r.strip()
    except Exception:
        pass
    return text

def is_img(d):
    return len(d) > 8 and (d[:3] == b'\xff\xd8\xff' or d[:4] == b'\x89PNG')

async def gen_img(prompt, style="photorealistic") -> Optional[bytes]:
    en = await tr_en(prompt)
    final = f"{en}, {style}, 8k, detailed"[:600]
    seed = random.randint(1, 999999)
    enc = uq(final, safe='')
    urls = [
        f"https://image.pollinations.ai/prompt/{enc}?width=1024&height=1024&nologo=true&seed={seed}&model=flux",
        f"https://image.pollinations.ai/prompt/{enc}?nologo=true&seed={seed}",
    ]
    for url in urls:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=90),
                    headers={"User-Agent": "Mozilla/5.0"}) as r:
                    if r.status == 200:
                        d = await r.read()
                        if is_img(d):
                            return d
        except Exception:
            pass
    return None

MUSIC_STYLES = {
    "rock": "energetic rock music, electric guitar, drums",
    "pop": "catchy pop, upbeat melody",
    "jazz": "smooth jazz, saxophone, piano",
    "hiphop": "hip hop beat, trap, 808",
    "electronic": "electronic dance music, synthesizer, EDM",
    "ambient": "ambient relaxing music, meditation",
    "any": "instrumental music, melodic",
}

async def gen_music(prompt, style="any") -> Optional[bytes]:
    en = await tr_en(prompt)
    style_desc = MUSIC_STYLES.get(style, MUSIC_STYLES["any"])
    full_prompt = f"{style_desc}, {en}"[:200]
    for model_url in [
        "https://api-inference.huggingface.co/models/facebook/musicgen-small",
        "https://api-inference.huggingface.co/models/facebook/musicgen-medium",
    ]:
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(model_url,
                        json={"inputs": full_prompt, "parameters": {"duration": 20}},
                        timeout=aiohttp.ClientTimeout(total=130)) as r:
                        if r.status == 200:
                            ct = r.headers.get("content-type", "")
                            if any(x in ct for x in ["audio", "octet-stream", "flac", "wav"]):
                                d = await r.read()
                                if len(d) > 5000:
                                    return d
                        elif r.status == 503 and attempt == 0:
                            await asyncio.sleep(25)
            except Exception as e:
                log.warning(f"HF music: {e}")
                break
    try:
        enc = uq(full_prompt, safe='')
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://audio.pollinations.ai/{enc}",
                timeout=aiohttp.ClientTimeout(total=60), headers={"User-Agent": "Mozilla/5.0"}) as r:
                if r.status == 200:
                    d = await r.read()
                    if len(d) > 5000:
                        return d
    except Exception:
        pass
    return None

async def gen_video(prompt) -> Optional[bytes]:
    en = await tr_en(prompt)
    enc = uq(en[:300], safe='')
    seed = random.randint(1, 999999)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://video.pollinations.ai/prompt/{enc}?seed={seed}",
                timeout=aiohttp.ClientTimeout(total=120)) as r:
                if r.status == 200:
                    d = await r.read()
                    if len(d) > 5000:
                        return d
    except Exception as e:
        log.warning(f"Video: {e}")
    return None

async def dl(url, fmt="mp3"):
    if not YTDLP:
        return None, None, "yt-dlp не установлен"
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "%(title)s.%(ext)s")
        if fmt == "mp3":
            cmd = [YTDLP, "-x", "--audio-format", "mp3", "-o", out, "--no-playlist", "--max-filesize", "45M", url]
        elif fmt == "wav":
            cmd = [YTDLP, "-x", "--audio-format", "wav", "-o", out, "--no-playlist", "--max-filesize", "45M", url]
        else:
            cmd = [YTDLP, "-f", "bestvideo[ext=mp4]+bestaudio/best", "-o", out, "--no-playlist", "--max-filesize", "45M", url]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=300, text=True)
            files = os.listdir(tmp)
            if not files:
                return None, None, "Файл не создан"
            fp = os.path.join(tmp, files[0])
            with open(fp, "rb") as f:
                return f.read(), files[0], None
        except subprocess.TimeoutExpired:
            return None, None, "Таймаут"
        except Exception as e:
            return None, None, str(e)

async def web_search(q) -> Optional[str]:
    enc = uq(q)
    for url in [f"https://searx.be/search?q={enc}&format=json", f"https://priv.au/search?q={enc}&format=json"]:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        items = (await r.json(content_type=None)).get("results", [])
                        if items:
                            parts = [f"{i.get('title', '')}\n{i.get('content', '')}" for i in items[:5]]
                            return "\n\n".join(parts)
        except Exception:
            pass
    return None

async def read_page(url) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"User-Agent": "Mozilla/5.0"},
                timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    html = await r.text(errors="ignore")
                    t = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.I)
                    t = re.sub(r'<[^>]+', ' ', t)
                    t = re.sub(r'\s+', ' ', t).strip()
                    return t[:6000]
    except Exception:
        pass
    return None

async def weather(loc) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://wttr.in/{uq(loc)}?format=j1&lang=ru",
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    cur = (await r.json()).get("current_condition", [{}])[0]
                    desc = cur.get('lang_ru', [{}])[0].get('value', '')
                    return f"🌡 {cur.get('temp_C', '?')}°C\n☁️ {desc}"
    except Exception:
        pass
    return None

async def is_admin(chat_id, uid) -> bool:
    try:
        m = await bot.get_chat_member(chat_id, uid)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except Exception:
        return False

async def delete_bulk(chat_id, ids) -> int:
    deleted = 0
    for batch in [ids[i:i+100] for i in range(0, len(ids), 100)]:
        try:
            await bot.delete_messages(chat_id, batch)
            deleted += len(batch)
            await asyncio.sleep(0.3)
        except Exception as e:
            log.error(f"Delete: {e}")
    return deleted

def extract_vid(path):
    if not FFMPEG:
        return None, None
    fp, ap = path + "_f.jpg", path + "_a.ogg"
    try:
        subprocess.run(["ffmpeg", "-i", path, "-ss", "00:00:01", "-vframes", "1", "-q:v", "2", "-y", fp],
            capture_output=True, timeout=30)
        if not (os.path.exists(fp) and os.path.getsize(fp) > 300):
            fp = None
    except Exception:
        fp = None
    try:
        subprocess.run(["ffmpeg", "-i", path, "-vn", "-acodec", "libopus", "-b:a", "64k", "-y", ap],
            capture_output=True, timeout=60)
        if not (os.path.exists(ap) and os.path.getsize(ap) > 200):
            ap = None
    except Exception:
        ap = None
    return fp, ap

def strip(t):
    t = re.sub(r'```\w*\n?(.*?)```', lambda m: m.group(1).strip(), t, flags=re.DOTALL)
    t = re.sub(r'\*\*(.+?)\*\*', r'\1', t, flags=re.DOTALL)
    return t.strip()

async def snd(msg, text):
    text = text.strip()
    while len(text) > 4000:
        await msg.answer(text[:4000])
        text = text[4000:]
        await asyncio.sleep(0.15)
    if text:
        await msg.answer(text)

def sys_prompt(uid, chat_id, chat_type, channels_list=""):
    u = Db.user(uid)
    name = u.get("name", "")
    total = u.get("total_msgs", 0)
    mems = u.get("memory", [])[:15]
    mem_str = "; ".join(m.get("fact", "") for m in mems) or "пока ничего"
    sums = Db.summaries(uid, chat_id)
    sum_str = "\n".join(sums[-2:]) if sums else ""
    ctx = get_chat_context(chat_type)
    ctx_inst = ""
    if chat_type in ("group", "supergroup"):
        ctx_inst = "ГРУППА: кратко, 1-3 предложения."
    elif chat_type == "channel":
        ctx_inst = "КАНАЛ: пиши как публикацию."
    return f"""Ты NEXUM — AI нового поколения. Модель: nexum v1.0.
Характер: умный, прямой, помогаешь искренне. Отвечаешь на языке пользователя.
{ctx_inst}
ПОЛЬЗОВАТЕЛЬ: {name or 'неизвестно'} | Сообщений: {total}
ПАМЯТЬ: {mem_str}
{f'ПРОШЛЫЕ ТЕМЫ: {sum_str}' if sum_str else ''}
ДОСТУПНЫЕ КАНАЛЫ: {channels_list or 'нет'}
ВРЕМЯ: {datetime.now().strftime('%d.%m %H:%M')}

Если пользователь просит ДЕЙСТВИЕ — в конце ответа добавь одну строку:
NEXUM_ACTION:{{"action":"...","params":{{...}},"reply":"текст для пользователя","requires_approval":false}}

Действия: chat, generate_image, generate_video, generate_music, post_to_channel,
create_notion_page, add_my_channel, delete_messages, delete_all_from_user, web_search, tts, download, weather.
params: prompt, style, url, channel_id, title, content, keyword, user_id, channel_id для add_my_channel — по необходимости.
requires_approval: true для delete_*, post_to_channel в группе.
БЕЗ markdown в ответах. Эмодзи умеренно."""

def parse_action(text: str) -> Optional[Dict]:
    if "NEXUM_ACTION:" not in text:
        return None
    try:
        j = text.split("NEXUM_ACTION:")[-1].strip()
        j = j.split("\n")[0]
        return json.loads(j)
    except Exception:
        return None

async def execute_action(action_data: Dict, message: Message, uid: int, chat_id: int) -> Optional[str]:
    action = action_data.get("action", "chat")
    params = action_data.get("params") or {}
    reply = action_data.get("reply", "")
    if action == "chat":
        return reply or "Ок."
    if action == "generate_image":
        prompt = params.get("prompt") or message.text or "красивый пейзаж"
        await bot.send_chat_action(chat_id, "upload_photo")
        img = await gen_img(prompt)
        if img:
            await message.answer_photo(BufferedInputFile(img, "nexum.jpg"), caption=reply[:200] or "🖼")
            return None
        return reply or "Не удалось сгенерировать."
    if action == "generate_video":
        prompt = params.get("prompt") or message.text or "moving scene"
        await bot.send_chat_action(chat_id, "upload_video")
        vid = await gen_video(prompt)
        if vid:
            await message.answer_video(BufferedInputFile(vid, "nexum.mp4"), caption=reply[:200] or "🎬")
            return None
        img = await gen_img(prompt)
        if img:
            await message.answer_photo(BufferedInputFile(img, "nexum.jpg"), caption="Видео недоступно. Изображение:")
            return None
        return reply or "Видео и изображение недоступны."
    if action == "generate_music":
        prompt = params.get("prompt") or message.text or "instrumental"
        style = params.get("style", "any")
        await bot.send_chat_action(chat_id, "record_voice")
        music = await gen_music(prompt, style)
        if music:
            await message.answer_voice(BufferedInputFile(music, "nexum.mp3"), caption=reply[:200] or "🎵")
            return None
        return reply or "Генерация музыки недоступна."
    if action == "web_search":
        q = params.get("query") or message.text
        if not q:
            return "Укажи запрос для поиска."
        res = await web_search(q)
        if res:
            return f"🔍 Результаты:\n\n{res[:2000]}"
        return "Ничего не найдено."
    if action == "tts":
        t = params.get("text") or message.text
        if not t:
            return "Укажи текст для озвучки."
        audio = await do_tts(t, uid)
        if audio:
            await message.answer_voice(BufferedInputFile(audio, "nexum.mp3"))
            return None
        return "Не удалось озвучить."
    if action == "weather":
        loc = params.get("location") or message.text or "Moscow"
        w = await weather(loc)
        return w or "Погода недоступна."
    if action == "create_notion_page":
        if not notion_configured():
            return "Notion не настроен. Добавь NOTION_API_KEY в .env."
        title = params.get("title") or "Новая страница"
        content = params.get("content") or message.text or ""
        db_id = params.get("database_id")
        r = await notion_create_page(title, content, db_id)
        if r:
            return f"✅ Страница создана в Notion: {title}"
        return "Не удалось создать страницу."
    if action == "add_my_channel":
        ch_id = params.get("channel_id")
        if ch_id:
            Db.add_user_channel(uid, int(ch_id))
            return f"✅ Канал (ID {ch_id}) привязан к тебе."
        return "Укажи channel_id. Доступные каналы: " + (build_channels_list(uid) or "нет")
    if action == "download":
        url = params.get("url") or (re.search(r'https?://\S+', message.text or "") and re.search(r'https?://\S+', message.text).group())
        if not url:
            return "Дай ссылку для скачивания."
        fmt = params.get("format", "mp3")
        data, fname, err = await dl(url.strip(), fmt)
        if data:
            if fmt == "mp4":
                await message.answer_video(BufferedInputFile(data, fname))
            else:
                await message.answer_audio(BufferedInputFile(data, fname))
            return None
        return f"Ошибка: {err}"
    return reply or "Неизвестное действие."

async def send_approval_to_admins(req: ApprovalRequest, bot_instance):
    admin_ids = get_admin_ids()
    if not admin_ids:
        log.warning("ADMIN_IDS not set — approval skipped")
        return
    aid = req.data.get("params", {}).get("_aid", "")
    text = f"⚠️ Запрос на согласование\n\nОт: {req.user_name} (ID {req.user_id})\nЧат: {req.chat_title}\nДействие: {req.action}\nДанные: {json.dumps(req.data, ensure_ascii=False)[:500]}\n\nПодтвердить?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"appr_yes:{aid}"),
         InlineKeyboardButton(text="❌ Нет", callback_data=f"appr_no:{aid}")]
    ])
    for aid in admin_ids:
        try:
            await bot_instance.send_message(aid, text, reply_markup=kb)
        except Exception as e:
            log.warning(f"Approval DM to {aid}: {e}")

def build_channels_list(uid):
    chs = Db.channels_all()
    uchs = Db.user_channels(uid)
    lines = []
    for c in chs:
        cid = c["chat_id"]
        title = c.get("title", "?")
        mark = " ✓" if cid in uchs else ""
        lines.append(f"{title} (ID {cid}){mark}")
    return ", ".join(lines) if lines else "нет"

async def ai_respond(message: Message, user_text: str):
    uid = message.from_user.id
    chat_id = message.chat.id
    ct = message.chat.type
    Db.ensure(uid, message.from_user.first_name or "", message.from_user.username or "")
    Db.extract_facts(uid, user_text)
    channels_list = build_channels_list(uid)
    hist = Db.history(uid, chat_id, 25)
    msgs = [{"role": "system", "content": sys_prompt(uid, chat_id, ct, channels_list)}]
    for role, content in hist[-20:]:
        msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": user_text})
    await bot.send_chat_action(chat_id, "typing")
    try:
        resp = await ask(msgs)
    except Exception as e:
        await message.answer(str(e)[:300])
        return
    Db.add(uid, chat_id, "user", user_text)
    action_data = parse_action(resp)
    reply_text = resp.split("NEXUM_ACTION:")[0].strip() if action_data else resp
    if action_data:
        action = action_data.get("action", "chat")
        if is_dangerous_action(action):
            admin_ids = get_admin_ids()
            if admin_ids:
                aid = create_approval_id()
                action_data["params"] = action_data.get("params") or {}
                action_data["params"]["_aid"] = aid
                action_data["params"]["_chat_id"] = chat_id
                action_data["params"]["_user_id"] = uid
                action_data["params"]["_reply"] = reply_text
                req = ApprovalRequest(
                    action=action, chat_id=chat_id, user_id=uid,
                    user_name=message.from_user.first_name or "?", chat_title=message.chat.title or "?",
                    data=action_data
                )
                add_pending(aid, req)
                await send_approval_to_admins(req, bot)
                await message.answer("Запрос отправлен админу на согласование.")
                Db.add(uid, chat_id, "assistant", reply_text)
                return
        result = await execute_action(action_data, message, uid, chat_id)
        if result:
            await snd(message, strip(result))
        Db.add(uid, chat_id, "assistant", reply_text or (result or ""))
    else:
        await snd(message, strip(reply_text))
        Db.add(uid, chat_id, "assistant", reply_text)

@dp.callback_query(F.data.startswith("appr_yes:"))
async def cb_approve_yes(cb: CallbackQuery):
    aid = cb.data.split(":", 1)[1]
    req = pop_pending(aid)
    if not req:
        await cb.answer("Запрос устарел")
        return
    await cb.answer("Выполняю...")
    action = req.action
    data = req.data
    params = data.get("params") or {}
    chat_id = params.get("_chat_id", req.chat_id)
    uid = params.get("_user_id", req.user_id)
    try:
        fake_msg = type('M', (), {'text': '', 'from_user': type('U', (), {'id': uid})(), 'answer': cb.message.answer, 'answer_photo': lambda *a, **k: cb.message.answer_photo(*a, **k), 'answer_video': lambda *a, **k: cb.message.answer_video(*a, **k), 'answer_voice': lambda *a, **k: cb.message.answer_voice(*a, **k), 'answer_audio': lambda *a, **k: cb.message.answer_audio(*a, **k)})()
        action_data = {"action": action, "params": params, "reply": data.get("reply", "")}
        if action == "post_to_channel":
            ch_id = params.get("channel_id") or chat_id
            post = params.get("post") or params.get("text", "")
            await bot.send_message(ch_id, post)
            await cb.message.answer("✅ Опубликовано!")
        elif action in ("delete_messages", "delete_all_from_user"):
            ids = params.get("message_ids", [])
            kw = params.get("keyword")
            if kw and chat_id:
                rows = Db.grp_msgs(chat_id, 500)
                ids = [r["msg_id"] for r in rows if kw.lower() in (r.get("text") or "").lower()]
            elif not ids and params.get("user_id"):
                rows = Db.grp_msgs(chat_id, 500)
                ids = [r["msg_id"] for r in rows if r.get("uid") == params["user_id"]]
            if ids:
                n = await delete_bulk(chat_id, ids)
                await cb.message.answer(f"✅ Удалено {n} сообщений")
            else:
                await cb.message.answer("Сообщений не найдено")
        elif action == "clear_chat":
            rows = Db.grp_msgs(chat_id, 500)
            ids = [r["msg_id"] for r in rows]
            if ids:
                n = await delete_bulk(chat_id, ids)
                await cb.message.answer(f"✅ Удалено {n} сообщений")
            else:
                await cb.message.answer("Нечего удалять")
        elif action == "ban_user":
            try:
                uid_ban = params.get("user_id")
                if uid_ban:
                    await bot.ban_chat_member(chat_id, uid_ban)
                    await cb.message.answer("✅ Пользователь забанен")
                else:
                    await cb.message.answer("Нет user_id")
            except Exception as ex:
                await cb.message.answer(f"Ошибка: {ex}")
        else:
            await execute_action(action_data, fake_msg, uid, chat_id)
    except Exception as e:
        await cb.message.answer(f"Ошибка: {e}")

@dp.callback_query(F.data.startswith("appr_no:"))
async def cb_approve_no(cb: CallbackQuery):
    aid = cb.data.split(":", 1)[1]
    pop_pending(aid)
    await cb.answer("Отклонено")
    await cb.message.answer("Запрос отклонён")

@dp.message(CommandStart())
async def cmd_start(m: Message):
    Db.ensure(m.from_user.id, m.from_user.first_name or "", m.from_user.username or "")
    await m.answer(
        "Привет! Я NEXUM v1.0 — AI без ограничений.\n\n"
        "Пиши что угодно: нарисуй, сгенерируй видео, музыку, создай страницу в Notion, "
        "опубликуй в канал, найди в интернете, озвучь текст. Я сам пойму и сделаю.\n\n"
        "Опасные действия (удаление сообщений и т.п.) запрашивают согласование у админа в личку."
    )

@dp.message(F.text)
async def on_text(message: Message):
    text = (message.text or "").strip()
    if not text:
        return
    uid = message.from_user.id
    chat_id = message.chat.id
    ct = message.chat.type
    if ct in ("group", "supergroup"):
        Db.grp_save(chat_id, uid, message.from_user.first_name or "", message.from_user.username or "", text=text, msg_id=message.message_id)
        is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.is_bot
        me = await bot.get_me()
        is_mention = me.username and f"@{me.username}" in text
        if not is_reply_to_bot and not is_mention:
            return
    await ai_respond(message, text)

@dp.message(F.voice)
async def on_voice(message: Message):
    uid = message.from_user.id
    chat_id = message.chat.id
    if message.chat.type in ("group", "supergroup"):
        Db.grp_save(chat_id, uid, message.from_user.first_name or "", message.from_user.username or "", mtype="voice", msg_id=message.message_id)
    await bot.send_chat_action(chat_id, "typing")
    try:
        file = await bot.get_file(message.voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            ap = tmp.name
        text = await stt(ap)
        try:
            os.unlink(ap)
        except Exception:
            pass
        if text:
            await message.answer(f"🎤 {text}")
            await ai_respond(message, text)
        else:
            await message.answer("Не распознал речь.")
    except Exception as e:
        log.error(f"Voice: {e}")
        await message.answer("Ошибка")

@dp.message(F.photo)
async def on_photo(message: Message):
    uid = message.from_user.id
    chat_id = message.chat.id
    cap = message.caption or "Опиши фото"
    await bot.send_chat_action(chat_id, "typing")
    try:
        file = await bot.get_file(message.photo[-1].file_id)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            pp = tmp.name
        with open(pp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        try:
            os.unlink(pp)
        except Exception:
            pass
        an = await _gemini_vision(b64, cap)
        if an:
            Db.add(uid, chat_id, "user", f"[фото] {cap}")
            Db.add(uid, chat_id, "assistant", an)
            await message.answer(strip(an))
        else:
            await message.answer("Не смог проанализировать")
    except Exception as e:
        log.error(f"Photo: {e}")

@dp.message(F.video)
async def on_video(message: Message):
    await _handle_vid(message, message.video.file_id, message.caption or "")

@dp.message(F.video_note)
async def on_video_note(message: Message):
    await _handle_vn(message, message.video_note, "Опиши видеокружок")

@dp.message(F.audio)
async def on_audio(message: Message):
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        file = await bot.get_file(message.audio.file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            ap = tmp.name
        if recognize_music:
            info = await recognize_music(ap)
            if info:
                await message.answer("🎵 " + format_music_info(info))
                try:
                    os.unlink(ap)
                except Exception:
                    pass
                return
        t = await stt(ap)
        try:
            os.unlink(ap)
        except Exception:
            pass
        if t:
            await message.answer(f"🎵 Транскрипция:\n{t}")
        else:
            await ai_respond(message, "Прислали аудио")
    except Exception as e:
        log.error(f"Audio: {e}")

async def _handle_vid(message, file_id, caption):
    uid = message.from_user.id
    chat_id = message.chat.id
    await bot.send_chat_action(chat_id, "typing")
    try:
        file = await bot.get_file(file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            vp = tmp.name
        vis, sp = None, None
        if FFMPEG:
            fp, ap = extract_vid(vp)
            try:
                os.unlink(vp)
            except Exception:
                pass
            if fp:
                with open(fp, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                try:
                    os.unlink(fp)
                except Exception:
                    pass
                vis = await _gemini_vision(b64, caption or "Опиши кадр")
            if ap:
                sp = await stt(ap)
                try:
                    os.unlink(ap)
                except Exception:
                    pass
        else:
            try:
                os.unlink(vp)
            except Exception:
                pass
        parts = []
        if vis:
            parts.append(f"👁 {vis[:300]}")
        if sp:
            parts.append(f"🎤 {sp[:200]}")
        if parts:
            await message.answer("📹 " + " | ".join(parts))
        ctx = "Видео. "
        if caption:
            ctx += f"Подпись: {caption}. "
        if vis:
            ctx += vis[:200]
        if sp:
            ctx += f" Голос: {sp[:150]}"
        await ai_respond(message, ctx)
    except Exception as e:
        log.error(f"Vid: {e}")
        await message.answer("Не обработал видео")

async def _handle_vn(message, vn, prompt):
    await _handle_vid(message, vn.file_id, prompt)

@dp.my_chat_member()
async def on_added(upd):
    try:
        ns = upd.new_chat_member.status
        chat_id = upd.chat.id
        if ns in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
            ch = await bot.get_chat(chat_id)
            ct = ch.type
            if ct == "channel":
                await bot.send_message(chat_id,
                    "Привет! Я NEXUM v1.0. Анализирую канал...")
                asyncio.create_task(_auto_analyze_channel(chat_id, ch.title or "?"))
            elif ct in ("group", "supergroup"):
                await bot.send_message(chat_id,
                    "Привет! Я NEXUM v1.0. Пиши мне в reply или через @ — я сам всё сделаю.")
    except Exception as e:
        log.error(f"Added: {e}")

async def _auto_analyze_channel(chat_id, title):
    try:
        await asyncio.sleep(5)
        try:
            ch = await bot.get_chat(chat_id)
            desc = getattr(ch, "description", "") or ""
        except Exception:
            desc = ""
        an = f"Канал: {title}. Описание: {desc}"
        style = await ask([{"role": "user", "content": f"Стиль для '{title}' в 3 предложения:\n{an}"}], max_t=200)
        Db.save_channel(chat_id, title, an, style or "")
    except Exception as e:
        log.error(f"AutoAnalyze: {e}")

async def main():
    init_db()
    scheduler.start()
    log.info("=" * 50)
    log.info("  NEXUM v1.0 — AI Bot")
    log.info(f"  Gemini: {len(GEMINI_KEYS)} | Groq: {len(GROQ_KEYS)} | DeepSeek: {len(DS_KEYS)}")
    log.info(f"  Notion: {'OK' if notion_configured() else 'no'}")
    log.info("=" * 50)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
