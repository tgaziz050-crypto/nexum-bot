"""
NEXUM v4.1 — AI БОТ БЕЗ ГРАНИЦ
Исправлены: удаление сообщений, генерация музыки, AI перегрузки, TTS.
"""
import asyncio, logging, os, tempfile, base64, random, aiohttp, subprocess, shutil, sqlite3, re, time
from urllib.parse import quote as url_quote
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════
# API КЛЮЧИ
# ══════════════════════════════════════════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "8758082038:AAH4UvCCmYPBnp-Hb9FrIX2OgqhnXj1ur5A")

GEMINI_KEYS = [k for k in [
    os.getenv("GEMINI_1","AIzaSyDf6nwIOu8zP_px0fol7e9tnMUVExJlVmc"),
    os.getenv("GEMINI_2","AIzaSyAXyKxHHs_x-10x7AzQvkzvcf3-dUlyFRw"),
    os.getenv("GEMINI_3","AIzaSyCQYq2EOS7ipG6CUyyLSoFc434lXWEAEzg"),
    os.getenv("GEMINI_4","AIzaSyDrhpSExtB60gqteY94zVqVt0a8IaAU7yQ"),
    os.getenv("GEMINI_5","AIzaSyClyTrxkcPcjP9JugkbwL7AqRS_kNZuHJ4"),
    os.getenv("GEMINI_6","AIzaSyBovsh5hKsZM1V3E551tvTl4tVyD7yvbSo"),
] if k]

GROQ_KEYS = [k for k in [
    os.getenv("GROQ_1","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"),
    os.getenv("GROQ_2","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"),
    os.getenv("GROQ_3","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"),
    os.getenv("GROQ_4","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"),
    os.getenv("GROQ_5","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"),
    os.getenv("GROQ_6","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"),
] if k]

DEEPSEEK_KEYS = [k for k in [
    os.getenv("DS_1","sk-09d35dbeb4a5430686f60bbd7411621e"),
    os.getenv("DS_2","sk-ad28ca8936ca4fa6a55847b532b9d956"),
    os.getenv("DS_3","sk-bae4ca5752974a5eb3edab30d0341439"),
    os.getenv("DS_4","sk-1262a6b483e54810a8d02adc6f06fe48"),
    os.getenv("DS_5","sk-22dad775c9f8465398a2e924ec4ae916"),
    os.getenv("DS_6","sk-bf18eb9208f14617b883a0aa4d05c5b0"),
] if k]

CLAUDE_KEYS = [k for k in [
    os.getenv("CLAUDE_1","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"),
] if k]

GROK_KEYS = [k for k in [
    os.getenv("GROK_1","sk-MXZl1hDZGmEN4slJhehF3OFWqarKHYlL4Y1MPo8rCtjlnrNf"),
    os.getenv("GROK_2","sk-KZ09Pva3G0Lq8hoYIIl6LP0ld5MR7wV05YQgK3RThxvGStwG"),
    os.getenv("GROK_3","sk-F9gQGwwdPQ3bn69ua29mCAv4B3LmUr0Bdsy4sTvwgxOwoCBY"),
] if k]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()
FFMPEG = shutil.which("ffmpeg")
YTDLP  = shutil.which("yt-dlp")

_idx: Dict[str,int] = {p:0 for p in ["gemini","groq","deepseek","claude","grok"]}
PENDING: Dict[str,Dict] = {}   # подтверждения действий

VOICES = {
    "ru_m":"ru-RU-DmitryNeural","ru_f":"ru-RU-SvetlanaNeural",
    "en_m":"en-US-GuyNeural","en_f":"en-US-JennyNeural",
    "en_m2":"en-US-EricNeural","en_f2":"en-US-AriaNeural",
    "de_m":"de-DE-ConradNeural","fr_m":"fr-FR-HenriNeural",
    "ja_f":"ja-JP-NanamiNeural","ko_f":"ko-KR-SunHiNeural",
    "ar_m":"ar-SA-HamedNeural","uk_m":"uk-UA-OstapNeural",
}

STYLES = {
    "realistic":"photorealistic, 8k uhd, professional photography, ultra detailed",
    "anime":"anime style, vibrant colors, studio ghibli quality",
    "3d":"3D render, octane render, volumetric lighting, ultra detailed",
    "oil":"oil painting, classical art, old masters style, museum quality",
    "watercolor":"watercolor painting, soft colors, artistic brushwork",
    "cyberpunk":"cyberpunk art, neon lights, futuristic city, dark atmosphere",
    "fantasy":"fantasy art, epic scene, magical illustration, artstation quality",
    "sketch":"pencil sketch, detailed drawing, graphite, professional illustration",
    "pixel":"pixel art, 16-bit, retro game style",
    "portrait":"portrait photography, studio lighting, 85mm lens, bokeh",
    "auto":"ultra detailed, high quality, professional",
}

def gk(p): 
    m={"gemini":GEMINI_KEYS,"groq":GROQ_KEYS,"deepseek":DEEPSEEK_KEYS,"claude":CLAUDE_KEYS,"grok":GROK_KEYS}
    k=m.get(p,[]); return k[_idx[p]%len(k)] if k else None

def rot(p):
    m={"gemini":GEMINI_KEYS,"groq":GROQ_KEYS,"deepseek":DEEPSEEK_KEYS,"claude":CLAUDE_KEYS,"grok":GROK_KEYS}
    k=m.get(p,[])
    if k: _idx[p]=(_idx[p]+1)%len(k)

def strip_md(t):
    t=re.sub(r'```\w*\n?(.*?)```',lambda m:m.group(1).strip(),t,flags=re.DOTALL)
    t=re.sub(r'`([^`]+)`',r'\1',t)
    t=re.sub(r'\*\*(.+?)\*\*',r'\1',t,flags=re.DOTALL)
    t=re.sub(r'(?<!\w)\*([^*\n]+)\*(?!\w)',r'\1',t)
    t=re.sub(r'^#{1,6}\s+(.+)$',r'\1',t,flags=re.MULTILINE)
    t=re.sub(r'\n{3,}','\n\n',t)
    return t.strip()

# ══════════════════════════════════════════════════════════════════════════
# БАЗА ДАННЫХ
# ══════════════════════════════════════════════════════════════════════════
DB_PATH = "nexum.db"

def db():
    return sqlite3.connect(DB_PATH)

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            uid INTEGER PRIMARY KEY, name TEXT DEFAULT '', username TEXT DEFAULT '',
            first_seen TEXT, last_seen TEXT, messages INTEGER DEFAULT 0,
            voice TEXT DEFAULT 'auto'
        );
        CREATE TABLE IF NOT EXISTS conv(
            id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, chat_id INTEGER,
            role TEXT, content TEXT, ts TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS memory(
            id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, cat TEXT, fact TEXT,
            imp INTEGER DEFAULT 5, ts TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS summaries(
            id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, chat_id INTEGER,
            summary TEXT, ts TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS group_msgs(
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, uid INTEGER,
            msg_id INTEGER, text TEXT DEFAULT '', type TEXT DEFAULT 'text',
            ts TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS group_stats(
            chat_id INTEGER, uid INTEGER, name TEXT DEFAULT '', username TEXT DEFAULT '',
            msgs INTEGER DEFAULT 0, words INTEGER DEFAULT 0, media INTEGER DEFAULT 0,
            voice_msgs INTEGER DEFAULT 0, stickers INTEGER DEFAULT 0,
            last_active TEXT, first_seen TEXT,
            PRIMARY KEY(chat_id, uid)
        );
        CREATE TABLE IF NOT EXISTS channels(
            chat_id INTEGER PRIMARY KEY, title TEXT, analysis TEXT DEFAULT '',
            style TEXT DEFAULT '', ts TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS schedules(
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER,
            hour INTEGER, minute INTEGER, topic TEXT, active INTEGER DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS i1 ON conv(uid,chat_id);
        CREATE INDEX IF NOT EXISTS i2 ON memory(uid);
        CREATE INDEX IF NOT EXISTS i3 ON group_msgs(chat_id,ts);
        CREATE INDEX IF NOT EXISTS i4 ON group_stats(chat_id);
        """)
    logger.info("DB ready")

class DB:
    @staticmethod
    def ensure_user(uid, name="", username=""):
        now = datetime.now().isoformat()
        with db() as c:
            c.execute("""INSERT INTO users(uid,name,username,first_seen,last_seen)VALUES(?,?,?,?,?)
                ON CONFLICT(uid) DO UPDATE SET last_seen=excluded.last_seen,
                name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END,
                username=CASE WHEN excluded.username!='' THEN excluded.username ELSE username END""",
                (uid,name,username,now,now))

    @staticmethod
    def get_user(uid):
        with db() as c:
            c.row_factory=sqlite3.Row
            r=c.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
            if not r: return {}
            u=dict(r)
            u['memory']=[dict(x) for x in c.execute(
                "SELECT * FROM memory WHERE uid=? ORDER BY imp DESC",(uid,)).fetchall()]
            return u

    @staticmethod
    def get_voice(uid):
        with db() as c:
            r=c.execute("SELECT voice FROM users WHERE uid=?",(uid,)).fetchone()
            return r[0] if r else "auto"

    @staticmethod
    def set_voice(uid, v):
        with db() as c:
            c.execute("UPDATE users SET voice=? WHERE uid=?",(v,uid))

    @staticmethod
    def set_name(uid, name):
        with db() as c:
            c.execute("UPDATE users SET name=? WHERE uid=?",(name,uid))

    @staticmethod
    def add_memory(uid, fact, cat="gen", imp=5):
        with db() as c:
            rows=c.execute("SELECT id,fact FROM memory WHERE uid=? AND cat=?",(uid,cat)).fetchall()
            for rid,ef in rows:
                aw=set(fact.lower().split()); bw=set(ef.lower().split())
                if aw and bw and len(aw&bw)/len(aw|bw)>0.7:
                    c.execute("UPDATE memory SET fact=? WHERE id=?",(fact,rid)); return
            c.execute("INSERT INTO memory(uid,cat,fact,imp)VALUES(?,?,?,?)",(uid,cat,fact,imp))
            c.execute("""DELETE FROM memory WHERE id IN(
                SELECT id FROM memory WHERE uid=? AND cat=? ORDER BY imp DESC LIMIT -1 OFFSET 25
            )""",(uid,cat))

    @staticmethod
    def extract_facts(uid, text):
        patterns=[
            (r'меня зовут\s+([А-ЯЁа-яёA-Za-z]{2,20})','identity',10),
            (r'мне\s+(\d{1,2})\s*(?:год|лет)','identity',9),
            (r'(?:я из|живу в)\s+([А-ЯЁа-яё\w\s]{2,25})','location',8),
            (r'работаю\s+([А-ЯЁа-яё\w\s]{2,40})','work',7),
            (r'люблю\s+([А-ЯЁа-яё\w\s,]{2,40})','interests',6),
        ]
        for pat,cat,imp in patterns:
            m=re.search(pat,text,re.IGNORECASE)
            if m: DB.add_memory(uid,m.group(0).strip(),cat,imp)
        nm=re.search(r'(?:меня зовут|я\s*[-—])\s*([А-ЯЁA-Z][а-яёa-z]{1,15})',text)
        if nm:
            n=nm.group(1)
            with db() as c: c.execute("UPDATE users SET name=? WHERE uid=?",(n,uid))
            DB.add_memory(uid,f"Зовут {n}",'identity',10)

    @staticmethod
    def get_history(uid, chat_id, limit=40):
        with db() as c:
            rows=c.execute("SELECT role,content FROM conv WHERE uid=? AND chat_id=? ORDER BY id DESC LIMIT ?",
                (uid,chat_id,limit)).fetchall()
        return list(reversed(rows))

    @staticmethod
    def add_msg(uid, chat_id, role, content):
        with db() as c:
            c.execute("INSERT INTO conv(uid,chat_id,role,content)VALUES(?,?,?,?)",(uid,chat_id,role,content))
            if role=="user": c.execute("UPDATE users SET messages=messages+1 WHERE uid=?",(uid,))

    @staticmethod
    def clear_history(uid, chat_id):
        with db() as c:
            c.execute("DELETE FROM conv WHERE uid=? AND chat_id=?",(uid,chat_id))

    @staticmethod
    def get_summaries(uid, chat_id):
        with db() as c:
            rows=c.execute("SELECT summary FROM summaries WHERE uid=? AND chat_id=? ORDER BY id ASC",(uid,chat_id)).fetchall()
        return [r[0] for r in rows]

    @staticmethod
    def update_group(chat_id, uid, name, username, text="", mtype="text", msg_id=None):
        now=datetime.now().isoformat()
        words=len(text.split()) if text else 0
        with db() as c:
            c.execute("""INSERT INTO group_stats(chat_id,uid,name,username,msgs,words,media,voice_msgs,stickers,last_active,first_seen)
                VALUES(?,?,?,?,1,?,?,?,?,?,?)
                ON CONFLICT(chat_id,uid) DO UPDATE SET
                msgs=msgs+1,words=words+excluded.words,
                media=media+CASE WHEN excluded.media THEN 1 ELSE 0 END,
                voice_msgs=voice_msgs+CASE WHEN excluded.voice_msgs THEN 1 ELSE 0 END,
                stickers=stickers+CASE WHEN excluded.stickers THEN 1 ELSE 0 END,
                last_active=excluded.last_active,
                name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END,
                username=CASE WHEN excluded.username!='' THEN excluded.username ELSE username END""",
                (chat_id,uid,name,username,words,
                 1 if mtype!="text" else 0,
                 1 if mtype=="voice" else 0,
                 1 if mtype=="sticker" else 0,
                 now,now))
            # ВСЕГДА сохраняем msg_id для возможности удаления
            if msg_id:
                c.execute("INSERT INTO group_msgs(chat_id,uid,msg_id,text,type)VALUES(?,?,?,?,?)",
                    (chat_id,uid,msg_id,(text or "")[:500],mtype))
                c.execute("""DELETE FROM group_msgs WHERE id IN(
                    SELECT id FROM group_msgs WHERE chat_id=? ORDER BY id DESC LIMIT -1 OFFSET 10000
                )""",(chat_id,))

    @staticmethod
    def get_stats(chat_id):
        with db() as c:
            c.row_factory=sqlite3.Row
            return [dict(r) for r in c.execute(
                "SELECT * FROM group_stats WHERE chat_id=? ORDER BY msgs DESC LIMIT 20",(chat_id,)).fetchall()]

    @staticmethod
    def get_msgs(chat_id, limit=300):
        with db() as c:
            rows=c.execute("SELECT uid,msg_id,text,type,ts FROM group_msgs WHERE chat_id=? ORDER BY id DESC LIMIT ?",
                (chat_id,limit)).fetchall()
        return list(reversed(rows))

    @staticmethod
    def get_channel(chat_id):
        with db() as c:
            c.row_factory=sqlite3.Row
            r=c.execute("SELECT * FROM channels WHERE chat_id=?",(chat_id,)).fetchone()
            return dict(r) if r else None

    @staticmethod
    def save_channel(chat_id, title, analysis, style):
        with db() as c:
            c.execute("""INSERT INTO channels(chat_id,title,analysis,style)VALUES(?,?,?,?)
                ON CONFLICT(chat_id) DO UPDATE SET analysis=excluded.analysis,style=excluded.style""",
                (chat_id,title,analysis,style))

    @staticmethod
    async def maybe_summarize(uid, chat_id):
        try:
            with db() as c:
                total=c.execute("SELECT COUNT(*) FROM conv WHERE uid=? AND chat_id=?",(uid,chat_id)).fetchone()[0]
                if total<=60: return
                old=c.execute("SELECT id,role,content FROM conv WHERE uid=? AND chat_id=? ORDER BY id ASC LIMIT 30",
                    (uid,chat_id)).fetchall()
            if not old: return
            lines=[("User" if r[1]=="user" else "NEXUM")+": "+r[2][:200] for r in old]
            s=await ai_gen([{"role":"user","content":"Кратко резюмируй диалог (100 слов):\n"+"\n".join(lines)}],max_tokens=200)
            if not s: return
            with db() as c:
                c.execute("INSERT INTO summaries(uid,chat_id,summary)VALUES(?,?,?)",(uid,chat_id,s))
                ids=",".join(str(r[0]) for r in old)
                c.execute(f"DELETE FROM conv WHERE id IN({ids})")
        except Exception as e: logger.error(f"Summarize: {e}")


# ══════════════════════════════════════════════════════════════════════════
# AI ПРОВАЙДЕРЫ
# ══════════════════════════════════════════════════════════════════════════

async def gemini(messages, model="gemini-2.0-flash-exp", max_tokens=4096, temp=0.85):
    if not GEMINI_KEYS: return None
    sys_txt=""; contents=[]
    for m in messages:
        if m["role"]=="system": sys_txt=m["content"]
        elif m["role"]=="user": contents.append({"role":"user","parts":[{"text":m["content"]}]})
        else: contents.append({"role":"model","parts":[{"text":m["content"]}]})
    if not contents: return None
    body={"contents":contents,
          "generationConfig":{"maxOutputTokens":max_tokens,"temperature":temp,"topP":0.95},
          "safetySettings":[{"category":c,"threshold":"BLOCK_NONE"} for c in
              ["HARM_CATEGORY_HARASSMENT","HARM_CATEGORY_HATE_SPEECH",
               "HARM_CATEGORY_SEXUALLY_EXPLICIT","HARM_CATEGORY_DANGEROUS_CONTENT"]]}
    if sys_txt: body["systemInstruction"]={"parts":[{"text":sys_txt}]}
    for _ in range(len(GEMINI_KEYS)):
        try:
            url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gk('gemini')}"
            async with aiohttp.ClientSession() as s:
                async with s.post(url,json=body,timeout=aiohttp.ClientTimeout(total=55)) as r:
                    if r.status in(429,503,500): rot("gemini"); continue
                    if r.status==200:
                        d=await r.json()
                        try: return d["candidates"][0]["content"]["parts"][0]["text"]
                        except: rot("gemini"); continue
                    rot("gemini")
        except asyncio.TimeoutError: rot("gemini")
        except Exception as e: logger.debug(f"Gemini {e}"); rot("gemini")
    return None

async def gemini_vision(b64, prompt, mime="image/jpeg"):
    if not GEMINI_KEYS: return None
    body={"contents":[{"parts":[{"text":prompt},{"inline_data":{"mime_type":mime,"data":b64}}]}],
          "generationConfig":{"maxOutputTokens":2048,"temperature":0.7},
          "safetySettings":[{"category":c,"threshold":"BLOCK_NONE"} for c in
              ["HARM_CATEGORY_HARASSMENT","HARM_CATEGORY_HATE_SPEECH",
               "HARM_CATEGORY_SEXUALLY_EXPLICIT","HARM_CATEGORY_DANGEROUS_CONTENT"]]}
    for _ in range(len(GEMINI_KEYS)):
        try:
            url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={gk('gemini')}"
            async with aiohttp.ClientSession() as s:
                async with s.post(url,json=body,timeout=aiohttp.ClientTimeout(total=40)) as r:
                    if r.status in(429,503,500): rot("gemini"); continue
                    if r.status==200:
                        d=await r.json()
                        try: return d["candidates"][0]["content"]["parts"][0]["text"]
                        except: rot("gemini"); continue
                    rot("gemini")
        except Exception as e: logger.debug(f"Vision {e}"); rot("gemini")
    return None

async def groq(messages, model="llama-3.3-70b-versatile", max_tokens=2048, temp=0.8):
    if not GROQ_KEYS: return None
    for _ in range(len(GROQ_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization":f"Bearer {gk('groq')}","Content-Type":"application/json"},
                    json={"model":model,"messages":messages,"max_tokens":max_tokens,"temperature":temp},
                    timeout=aiohttp.ClientTimeout(total=40)) as r:
                    if r.status==429: rot("groq"); await asyncio.sleep(1); continue
                    if r.status==200: return (await r.json())["choices"][0]["message"]["content"]
                    rot("groq")
        except Exception as e: logger.debug(f"Groq {e}"); rot("groq")
    return None

async def deepseek(messages, max_tokens=4096, temp=0.8):
    if not DEEPSEEK_KEYS: return None
    for _ in range(len(DEEPSEEK_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.deepseek.com/v1/chat/completions",
                    headers={"Authorization":f"Bearer {gk('deepseek')}","Content-Type":"application/json"},
                    json={"model":"deepseek-chat","messages":messages,"max_tokens":max_tokens,"temperature":temp},
                    timeout=aiohttp.ClientTimeout(total=55)) as r:
                    if r.status==429: rot("deepseek"); continue
                    if r.status==200: return (await r.json())["choices"][0]["message"]["content"]
                    rot("deepseek")
        except Exception as e: logger.debug(f"DS {e}"); rot("deepseek")
    return None

async def claude_api(messages, max_tokens=4096, temp=0.8):
    if not CLAUDE_KEYS: return None
    sys_txt=""; filtered=[]
    for m in messages:
        if m["role"]=="system": sys_txt=m["content"]
        else: filtered.append(m)
    if not filtered: return None
    body={"model":"claude-opus-4-5","max_tokens":max_tokens,"temperature":temp,"messages":filtered}
    if sys_txt: body["system"]=sys_txt
    for _ in range(len(CLAUDE_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.anthropic.com/v1/messages",
                    headers={"x-api-key":gk("claude"),"anthropic-version":"2023-06-01","Content-Type":"application/json"},
                    json=body,timeout=aiohttp.ClientTimeout(total=60)) as r:
                    if r.status in(429,529): rot("claude"); await asyncio.sleep(3); continue
                    if r.status==200: return (await r.json())["content"][0]["text"]
                    rot("claude")
        except Exception as e: logger.debug(f"Claude {e}"); rot("claude")
    return None

async def grok_api(messages, max_tokens=4096, temp=0.8):
    if not GROK_KEYS: return None
    for _ in range(len(GROK_KEYS)):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.x.ai/v1/chat/completions",
                    headers={"Authorization":f"Bearer {gk('grok')}","Content-Type":"application/json"},
                    json={"model":"grok-beta","messages":messages,"max_tokens":max_tokens,"temperature":temp},
                    timeout=aiohttp.ClientTimeout(total=55)) as r:
                    if r.status==429: rot("grok"); continue
                    if r.status==200: return (await r.json())["choices"][0]["message"]["content"]
                    rot("grok")
        except Exception as e: logger.debug(f"Grok {e}"); rot("grok"); break
    return None

async def stt(path):
    if not GROQ_KEYS: return None
    for _ in range(len(GROQ_KEYS)):
        try:
            with open(path,"rb") as f: data=f.read()
            async with aiohttp.ClientSession() as s:
                form=aiohttp.FormData()
                ext=os.path.splitext(path)[1] or ".ogg"
                ct="audio/ogg" if "ogg" in ext else "audio/mpeg"
                form.add_field("file",data,filename=f"audio{ext}",content_type=ct)
                form.add_field("model","whisper-large-v3")
                async with s.post("https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization":f"Bearer {gk('groq')}"},data=form,
                    timeout=aiohttp.ClientTimeout(total=60)) as r:
                    if r.status==429: rot("groq"); continue
                    if r.status==200: return (await r.json()).get("text","").strip()
                    rot("groq")
        except Exception as e: logger.debug(f"STT {e}"); rot("groq")
    return None

async def ai_gen(messages, max_tokens=4096, temp=0.85, task="general"):
    """Умная ротация провайдеров с fallback"""
    orders = {
        "fast":     ["gemini","groq","deepseek","claude","grok"],
        "code":     ["deepseek","gemini","groq","claude","grok"],
        "creative": ["gemini","claude","groq","deepseek","grok"],
        "analysis": ["gemini","deepseek","groq","claude","grok"],
        "general":  ["gemini","groq","deepseek","claude","grok"],
    }
    order = orders.get(task, orders["general"])
    
    for provider in order:
        try:
            result = None
            if provider=="gemini" and GEMINI_KEYS:
                for mdl in ["gemini-2.0-flash-exp","gemini-2.0-flash","gemini-1.5-flash-latest"]:
                    result = await gemini(messages, model=mdl, max_tokens=max_tokens, temp=temp)
                    if result: break
            elif provider=="groq" and GROQ_KEYS:
                for mdl in ["llama-3.3-70b-versatile","llama-3.1-70b-versatile","llama3-70b-8192"]:
                    result = await groq(messages, model=mdl, max_tokens=min(max_tokens,2048), temp=temp)
                    if result: break
            elif provider=="deepseek" and DEEPSEEK_KEYS:
                result = await deepseek(messages, max_tokens=max_tokens, temp=temp)
            elif provider=="claude" and CLAUDE_KEYS:
                result = await claude_api(messages, max_tokens=min(max_tokens,4096), temp=temp)
            elif provider=="grok" and GROK_KEYS:
                result = await grok_api(messages, max_tokens=max_tokens, temp=temp)
            
            if result and len(result.strip())>2:
                logger.info(f"✅ AI: {provider}")
                return result
        except Exception as e:
            logger.warning(f"❌ {provider}: {e}")
    
    # Последний шанс — быстрый groq с маленькой моделью
    if GROQ_KEYS:
        try:
            short_msgs = [m for m in messages if m["role"]!="system"][-4:]
            if not short_msgs: short_msgs = messages[-2:]
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization":f"Bearer {GROQ_KEYS[0]}"},
                    json={"model":"llama3-8b-8192","messages":short_msgs,"max_tokens":800,"temperature":0.7},
                    timeout=aiohttp.ClientTimeout(total=25)) as r:
                    if r.status==200:
                        t=(await r.json())["choices"][0]["message"]["content"]
                        if t: return t
        except: pass
    
    raise Exception("AI временно недоступен. Проверь интернет-соединение и попробуй снова.")


# ══════════════════════════════════════════════════════════════════════════
# TTS
# ══════════════════════════════════════════════════════════════════════════
def detect_lang(text):
    t=text.lower()
    if re.search(r'[а-яё]',t): return "ru"
    if re.search(r'[\u0600-\u06ff]',t): return "ar"
    if re.search(r'[\u4e00-\u9fff]',t): return "zh"
    if re.search(r'[\u3040-\u30ff]',t): return "ja"
    if re.search(r'[\uac00-\ud7af]',t): return "ko"
    if re.search(r'[äöüß]',t): return "de"
    if re.search(r'[àâçéèêëîïôùûü]',t): return "fr"
    if re.search(r'[іїєґ]',t): return "uk"
    return "en"

async def tts(text, uid=0, force_voice=None, fmt="mp3"):
    clean=text.strip()[:1500]
    lang=detect_lang(clean)
    
    if force_voice and force_voice in VOICES:
        voice=VOICES[force_voice]
    else:
        saved=DB.get_voice(uid) if uid else "auto"
        if saved!="auto" and saved in VOICES:
            voice=VOICES[saved]
        else:
            vm={"ru":["ru-RU-DmitryNeural","ru-RU-SvetlanaNeural"],
                "en":["en-US-GuyNeural","en-US-JennyNeural","en-US-AriaNeural"],
                "de":["de-DE-ConradNeural"],"fr":["fr-FR-HenriNeural"],
                "ar":["ar-SA-HamedNeural"],"ja":["ja-JP-NanamiNeural"],
                "ko":["ko-KR-SunHiNeural"],"uk":["uk-UA-OstapNeural"]}
            voice=random.choice(vm.get(lang,["en-US-GuyNeural"]))
    
    chunks=[]
    if len(clean)>900:
        sents=re.split(r'(?<=[.!?])\s+',clean)
        cur=""
        for s in sents:
            if len(cur)+len(s)<900: cur+=(" " if cur else "")+s
            else:
                if cur: chunks.append(cur)
                cur=s
        if cur: chunks.append(cur)
    else:
        chunks=[clean]
    
    parts=[]
    try:
        import edge_tts
        for chunk in chunks:
            comm=edge_tts.Communicate(chunk,voice,rate="+5%")
            with tempfile.NamedTemporaryFile(suffix=".mp3",delete=False) as tmp:
                p=tmp.name
            await comm.save(p)
            if os.path.exists(p) and os.path.getsize(p)>500:
                with open(p,"rb") as f: parts.append(f.read())
            try: os.unlink(p)
            except: pass
    except Exception as e:
        logger.error(f"TTS edge: {e}")
    
    if parts:
        combined=b"".join(parts)
        if fmt=="wav" and FFMPEG:
            try:
                with tempfile.NamedTemporaryFile(suffix=".mp3",delete=False) as fi:
                    fi.write(combined); inp=fi.name
                out=inp+".wav"
                subprocess.run(["ffmpeg","-i",inp,"-acodec","pcm_s16le","-ar","44100","-y",out],
                    capture_output=True,timeout=30)
                if os.path.exists(out):
                    with open(out,"rb") as f: w=f.read()
                    try: os.unlink(inp); os.unlink(out)
                    except: pass
                    return w
            except: pass
        return combined
    return None


# ══════════════════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ
# ══════════════════════════════════════════════════════════════════════════
async def translate_en(text):
    if not re.search(r'[а-яёА-ЯЁ]',text): return text
    try:
        r=await gemini([{"role":"user","content":f"Translate to English for image generation. Only translation:\n{text}"}],max_tokens=100,temp=0.1)
        if r: return r.strip()
    except: pass
    return text

def is_img(d): 
    return len(d)>8 and (d[:3]==b'\xff\xd8\xff' or d[:4]==b'\x89PNG' or d[:4]==b'RIFF')

async def gen_image(prompt, style="auto"):
    en=await translate_en(prompt)
    suf=STYLES.get(style,STYLES["auto"])
    final=f"{en}, {suf}"
    seed=random.randint(1,999999)
    enc=url_quote(final[:500],safe='')
    mdl_map={"anime":"flux-anime","3d":"flux-3d","realistic":"flux-realism","portrait":"flux-realism"}
    mdl=mdl_map.get(style,"flux")
    urls=[
        f"https://image.pollinations.ai/prompt/{enc}?width=1024&height=1024&nologo=true&seed={seed}&model={mdl}",
        f"https://image.pollinations.ai/prompt/{enc}?width=1024&height=1024&nologo=true&seed={seed}&model=flux",
        f"https://image.pollinations.ai/prompt/{enc}?nologo=true&seed={seed}",
    ]
    conn=aiohttp.TCPConnector(ssl=False)
    for url in urls:
        try:
            async with aiohttp.ClientSession(connector=conn) as s:
                async with s.get(url,timeout=aiohttp.ClientTimeout(total=90),
                    headers={"User-Agent":"Mozilla/5.0"},allow_redirects=True) as r:
                    if r.status==200:
                        d=await r.read()
                        if is_img(d): return d
        except: pass
    return None


# ══════════════════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ МУЗЫКИ — РЕАЛЬНАЯ
# ══════════════════════════════════════════════════════════════════════════
async def gen_music(prompt, style="pop"):
    en=await translate_en(prompt)
    style_map={
        "rock":f"energetic rock music with electric guitar and drums, {en}",
        "pop":f"catchy pop song, upbeat melody, {en}",
        "jazz":f"smooth jazz with saxophone and piano, {en}",
        "hiphop":f"hip hop beat with bass and trap elements, {en}",
        "classical":f"classical orchestra music, {en}",
        "electronic":f"electronic dance music with synthesizer, {en}",
        "auto":f"instrumental music, {en}",
    }
    music_prompt=style_map.get(style,f"{style} music, {en}")
    
    # 1. HuggingFace MusicGen (бесплатно, без ключа)
    hf_models=[
        "https://api-inference.huggingface.co/models/facebook/musicgen-small",
        "https://api-inference.huggingface.co/models/facebook/musicgen-medium",
    ]
    for hf_url in hf_models:
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(hf_url,
                        json={"inputs":music_prompt,"parameters":{"duration":20,"guidance_scale":3}},
                        headers={"Content-Type":"application/json"},
                        timeout=aiohttp.ClientTimeout(total=120)) as r:
                        logger.info(f"HF music: {r.status}")
                        if r.status==200:
                            ct=r.headers.get("content-type","")
                            if "audio" in ct or "octet-stream" in ct or "flac" in ct or "wav" in ct:
                                d=await r.read()
                                if len(d)>5000:
                                    logger.info(f"Music OK: {len(d)} bytes")
                                    return d
                        elif r.status==503 and attempt==0:
                            # Модель грузится, подождём
                            await asyncio.sleep(25)
                            continue
                        break
            except Exception as e:
                logger.error(f"HF music {hf_url}: {e}")
                break

    # 2. Pollinations audio
    try:
        enc=url_quote(music_prompt[:200],safe='')
        conn=aiohttp.TCPConnector(ssl=False)
        for au in [f"https://audio.pollinations.ai/{enc}",f"https://text-to-music.pollinations.ai/{enc}"]:
            try:
                async with aiohttp.ClientSession(connector=conn) as s:
                    async with s.get(au,timeout=aiohttp.ClientTimeout(total=60),
                        headers={"User-Agent":"Mozilla/5.0"}) as r:
                        if r.status==200:
                            ct=r.headers.get("content-type","")
                            if any(x in ct for x in ["audio","mpeg","wav","flac","ogg"]):
                                d=await r.read()
                                if len(d)>5000: return d
            except: pass
    except Exception as e: logger.error(f"Pollinations audio: {e}")
    
    return None


# ══════════════════════════════════════════════════════════════════════════
# СКАЧИВАНИЕ
# ══════════════════════════════════════════════════════════════════════════
async def download(url, fmt="mp3"):
    if not YTDLP: return None,None,"yt-dlp не установлен"
    with tempfile.TemporaryDirectory() as tmp:
        out=os.path.join(tmp,"%(title)s.%(ext)s")
        if fmt=="mp3":
            cmd=[YTDLP,"-x","--audio-format","mp3","--audio-quality","0","-o",out,
                 "--no-playlist","--max-filesize","50M","--no-warnings",url]
        elif fmt=="wav":
            cmd=[YTDLP,"-x","--audio-format","wav","-o",out,
                 "--no-playlist","--max-filesize","50M","--no-warnings",url]
        else:
            cmd=[YTDLP,"-f","bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best",
                 "-o",out,"--no-playlist","--max-filesize","50M","--no-warnings",url]
        try:
            r=subprocess.run(cmd,capture_output=True,timeout=300,text=True)
            files=os.listdir(tmp)
            if not files: return None,None,r.stderr[:200] if r.stderr else "Не скачалось"
            fp=os.path.join(tmp,files[0])
            with open(fp,"rb") as f: return f.read(),files[0],None
        except subprocess.TimeoutExpired: return None,None,"Таймаут"
        except Exception as e: return None,None,str(e)


# ══════════════════════════════════════════════════════════════════════════
# ВЕБ-ПОИСК + УТИЛИТЫ
# ══════════════════════════════════════════════════════════════════════════
async def web_search(q):
    enc=url_quote(q)
    for url in [f"https://searx.be/search?q={enc}&format=json",
                f"https://priv.au/search?q={enc}&format=json",
                f"https://search.bus-hit.me/search?q={enc}&format=json"]:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url,timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status==200:
                        items=(await r.json(content_type=None)).get("results",[])
                        if items:
                            parts=[f"{i.get('title','')}\n{i.get('content','')}\n{i.get('url','')}" for i in items[:5]]
                            res="\n\n".join(parts)
                            if res.strip(): return res
        except: pass
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://api.duckduckgo.com/?q={enc}&format=json&no_html=1",
                timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status==200:
                    d=await r.json(content_type=None)
                    t=d.get("Answer","") or d.get("AbstractText","")
                    if t: return t
    except: pass
    return None

async def read_url(url):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url,headers={"User-Agent":"Mozilla/5.0"},
                timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status==200:
                    html=await r.text(errors="ignore")
                    t=re.sub(r'<script[^>]*>.*?</script>','',html,flags=re.DOTALL|re.IGNORECASE)
                    t=re.sub(r'<style[^>]*>.*?</style>','',t,flags=re.DOTALL|re.IGNORECASE)
                    t=re.sub(r'<[^>]+',' ',t)
                    t=re.sub(r'\s+',' ',t).strip()
                    return t[:6000]
    except Exception as e: logger.error(f"URL: {e}")
    return None

async def get_weather(loc):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://wttr.in/{url_quote(loc)}?format=j1&lang=ru",
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status==200:
                    d=await r.json(); cur=d.get("current_condition",[{}])[0]
                    return (f"🌡 {cur.get('temp_C','?')}°C (ощущается {cur.get('FeelsLikeC','?')}°C)\n"
                            f"☁️ {cur.get('lang_ru',[{}])[0].get('value','')}\n"
                            f"💧 {cur.get('humidity','?')}% | 💨 {cur.get('windspeedKmph','?')} км/ч")
    except: pass
    return None

async def get_rate(fr,to):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://open.er-api.com/v6/latest/{fr.upper()}",
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status==200:
                    rate=(await r.json()).get("rates",{}).get(to.upper())
                    if rate: return f"1 {fr.upper()} = {rate:.4f} {to.upper()}"
    except: pass
    return None


# ══════════════════════════════════════════════════════════════════════════
# ГРУППА И КАНАЛ
# ══════════════════════════════════════════════════════════════════════════
async def is_admin(chat_id, uid):
    try:
        m=await bot.get_chat_member(chat_id,uid)
        return m.status in(ChatMemberStatus.ADMINISTRATOR,ChatMemberStatus.CREATOR)
    except: return False

async def delete_bulk(chat_id, ids):
    deleted=0
    for batch in [ids[i:i+100] for i in range(0,len(ids),100)]:
        try:
            await bot.delete_messages(chat_id,batch)
            deleted+=len(batch); await asyncio.sleep(0.3)
        except Exception as e: logger.error(f"Delete batch: {e}")
    return deleted

async def analyze_channel(chat_id):
    try: chat=await bot.get_chat(chat_id); title=chat.title or "?"; desc=chat.description or ""
    except: title="?"; desc=""
    msgs=DB.get_msgs(chat_id,50)
    samples="\n\n".join([m[2] for m in msgs if m[2]][:15])
    prompt=f"""Telegram канал: {title}
Описание: {desc}
Примеры постов:
{samples or 'нет постов'}

Анализируй:
1. Тематика и ниша
2. Стиль написания (тон, длина, эмодзи)
3. Целевая аудитория
4. Как писать посты в этом стиле (конкретно)"""
    return await ai_gen([{"role":"user","content":prompt}],max_tokens=1000,task="analysis")

async def gen_post(chat_id, topic=""):
    ch=DB.get_channel(chat_id)
    style=""
    if ch and ch.get("style"): style=f"Стиль канала: {ch['style']}\n"
    prompt=f"""{style}Напиши Telegram пост{'на тему: '+topic if topic else ''}.
Правила: без markdown, с эмодзи где уместно, живо, цепляет с первой строки."""
    return await ai_gen([{"role":"user","content":prompt}],max_tokens=700,task="creative")


# ══════════════════════════════════════════════════════════════════════════
# СИСТЕМНЫЙ ПРОМПТ
# ══════════════════════════════════════════════════════════════════════════
def build_sys(uid, chat_id, chat_type="private"):
    u=DB.get_user(uid)
    name=u.get("name","")
    total=u.get("messages",0)
    mems=u.get("memory",[])
    
    by_cat: Dict[str,List]={}
    for m in mems[:20]: by_cat.setdefault(m.get("cat","gen"),[]).append(m["fact"])
    mem_str=""
    for cat,facts in by_cat.items():
        mem_str+=f"\n[{cat.upper()}]: "+"; ".join(facts[:4])
    if not mem_str: mem_str="\nПока ничего"
    
    sums=DB.get_summaries(uid,chat_id)
    sum_str=""
    if sums: sum_str="\nПРЕДЫДУЩИЕ ТЕМЫ:\n"+"\n---\n".join(sums[-3:])
    
    fam="новый"
    if total>100: fam="близкий"
    elif total>30: fam="знакомый"
    elif total>10: fam="начинающий"
    
    grp_note=""
    if chat_type in("group","supergroup"): grp_note="\nГРУППА: отвечай коротко, с характером."
    elif chat_type=="channel": grp_note="\nКАНАЛ: пиши как для контент-публикации."
    
    h=datetime.now().hour
    tod="ночь" if h<5 else "утро" if h<12 else "день" if h<17 else "вечер"
    
    return f"""Ты NEXUM — AI нового поколения. Не GPT, не Claude, не Gemini. Ты NEXUM.

ЛИЧНОСТЬ: умный, прямой, с характером. Не заискиваешь. Можешь спорить. Говоришь прямо.
Отвечаешь на языке пользователя как носитель.
Никогда не говоришь "я не могу" — находишь решение.

ПОЛЬЗОВАТЕЛЬ: {f"Имя: {name}" if name else "имя неизвестно"} | Сообщений: {total} | Статус: {fam}
ЧТО ЗНАЮ:{mem_str}
{sum_str}
{grp_note}
ВРЕМЯ: {tod}, {datetime.now().strftime('%d.%m.%Y %H:%M')}

СТИЛЬ: коротко на простые вопросы. Структурно на сложные. БЕЗ **markdown**.

МАРКЕРЫ (один если нужен):
%%IMG%%описание на английском%% — нарисовать изображение
%%IMG%%описание%%STYLE:стиль%% — с выбором стиля
%%TTS%%текст%% — озвучить
%%MUSIC%%описание%% — создать музыку
%%VIDEO%%описание%% — видео
%%WEB%%запрос%% — поиск в интернете
%%URL%%ссылка%% — прочитать сайт  
%%WTR%%город%% — погода
%%DL%%ссылка%%формат%% — скачать mp3/mp4/wav
%%RATE%%USD%%RUB%% — курс валюты
%%CALC%%выражение%% — калькулятор
%%REMIND%%минуты%%текст%% — напоминание
%%REMEMBER%%факт%% — запомнить
%%GRP_STATS%% — статистика группы"""


# ══════════════════════════════════════════════════════════════════════════
# КЛАВИАТУРЫ
# ══════════════════════════════════════════════════════════════════════════
def kb_voice():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎙 Дмитрий (RU♂)",callback_data="voice_ru_m"),
         InlineKeyboardButton(text="🎙 Светлана (RU♀)",callback_data="voice_ru_f")],
        [InlineKeyboardButton(text="🎙 Guy (EN♂)",callback_data="voice_en_m"),
         InlineKeyboardButton(text="🎙 Jenny (EN♀)",callback_data="voice_en_f")],
        [InlineKeyboardButton(text="🎙 Eric (EN♂)",callback_data="voice_en_m2"),
         InlineKeyboardButton(text="🎙 Aria (EN♀)",callback_data="voice_en_f2")],
        [InlineKeyboardButton(text="🎙 Henri (FR)",callback_data="voice_fr_m"),
         InlineKeyboardButton(text="🎙 Conrad (DE)",callback_data="voice_de_m")],
        [InlineKeyboardButton(text="🎙 Nanami (JA)",callback_data="voice_ja_f"),
         InlineKeyboardButton(text="🎙 SunHi (KO)",callback_data="voice_ko_f")],
        [InlineKeyboardButton(text="🤖 Авто",callback_data="voice_auto")],
    ])

def kb_img(prompt):
    p=prompt[:40]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Реализм",callback_data=f"img_realistic_{p}"),
         InlineKeyboardButton(text="🎌 Аниме",callback_data=f"img_anime_{p}")],
        [InlineKeyboardButton(text="🌐 3D",callback_data=f"img_3d_{p}"),
         InlineKeyboardButton(text="🎨 Масло",callback_data=f"img_oil_{p}")],
        [InlineKeyboardButton(text="💧 Акварель",callback_data=f"img_watercolor_{p}"),
         InlineKeyboardButton(text="🌃 Киберпанк",callback_data=f"img_cyberpunk_{p}")],
        [InlineKeyboardButton(text="🐉 Фэнтези",callback_data=f"img_fantasy_{p}"),
         InlineKeyboardButton(text="✏️ Эскиз",callback_data=f"img_sketch_{p}")],
        [InlineKeyboardButton(text="🟦 Пиксель",callback_data=f"img_pixel_{p}"),
         InlineKeyboardButton(text="📷 Портрет",callback_data=f"img_portrait_{p}")],
        [InlineKeyboardButton(text="⚡ Авто",callback_data=f"img_auto_{p}")],
    ])

def kb_dl(url):
    u=url[:70]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 MP3",callback_data=f"dl_mp3_{u}"),
         InlineKeyboardButton(text="🎬 MP4",callback_data=f"dl_mp4_{u}")],
        [InlineKeyboardButton(text="🔊 WAV",callback_data=f"dl_wav_{u}")],
    ])

def kb_tts(text):
    t=text[:50]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗣 Дмитрий",callback_data=f"tts_ru_m_{t}"),
         InlineKeyboardButton(text="🗣 Светлана",callback_data=f"tts_ru_f_{t}")],
        [InlineKeyboardButton(text="🗣 Guy EN",callback_data=f"tts_en_m_{t}"),
         InlineKeyboardButton(text="🗣 Jenny EN",callback_data=f"tts_en_f_{t}")],
        [InlineKeyboardButton(text="💾 WAV",callback_data=f"tts_wav_{t}")],
    ])

def kb_music(prompt):
    p=prompt[:35]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎸 Рок",callback_data=f"music_rock_{p}"),
         InlineKeyboardButton(text="🎹 Поп",callback_data=f"music_pop_{p}")],
        [InlineKeyboardButton(text="🎷 Джаз",callback_data=f"music_jazz_{p}"),
         InlineKeyboardButton(text="🔥 Хип-хоп",callback_data=f"music_hiphop_{p}")],
        [InlineKeyboardButton(text="🎻 Классика",callback_data=f"music_classical_{p}"),
         InlineKeyboardButton(text="🌊 Электро",callback_data=f"music_electronic_{p}")],
        [InlineKeyboardButton(text="✨ Любой стиль",callback_data=f"music_auto_{p}")],
    ])

def kb_confirm(aid, label):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, удалить",callback_data=f"confirm_{aid}"),
        InlineKeyboardButton(text="❌ Отмена",callback_data=f"cancel_{aid}"),
    ]])

def kb_channel():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Анализ канала",callback_data="ch_analyze"),
         InlineKeyboardButton(text="📝 Написать пост",callback_data="ch_post")],
        [InlineKeyboardButton(text="⏰ Расписание",callback_data="ch_schedule"),
         InlineKeyboardButton(text="🎨 Стиль",callback_data="ch_style")],
    ])

def kb_group():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика",callback_data="grp_stats"),
         InlineKeyboardButton(text="📈 Аналитика",callback_data="grp_analytics")],
        [InlineKeyboardButton(text="👥 Участники",callback_data="grp_members"),
         InlineKeyboardButton(text="🗑 Очистить",callback_data="grp_clean")],
    ])


# ══════════════════════════════════════════════════════════════════════════
# ОБРАБОТКА ОТВЕТОВ AI
# ══════════════════════════════════════════════════════════════════════════
async def send_long(msg, text):
    text=text.strip()
    while len(text)>4000:
        await msg.answer(text[:4000]); text=text[4000:]; await asyncio.sleep(0.2)
    if text: await msg.answer(text)

async def remind_job(chat_id, text):
    try: await bot.send_message(chat_id,f"⏰ Напоминание:\n\n{text}")
    except Exception as e: logger.error(f"Remind: {e}")

async def sched_post_job(chat_id, topic):
    try:
        post=await gen_post(chat_id,topic)
        await bot.send_message(chat_id,strip_md(post))
    except Exception as e: logger.error(f"Sched post: {e}")

async def process_response(message, response, uid):
    chat_id=message.chat.id

    # ИЗОБРАЖЕНИЕ
    if "%%IMG%%" in response:
        raw=response.split("%%IMG%%")[1].split("%%")[0].strip()
        style="auto"
        if "STYLE:" in raw:
            pts=raw.split("STYLE:"); raw=pts[0].strip(); style=pts[1].strip().split()[0].lower()
        await message.answer("🎨 Выбери стиль:", reply_markup=kb_img(raw))
        return

    # ВИДЕО
    if "%%VIDEO%%" in response:
        prompt=response.split("%%VIDEO%%")[1].split("%%")[0].strip()
        m2=await message.answer("🎬 Генерирую видео...")
        await bot.send_chat_action(chat_id,"upload_video")
        en=await translate_en(prompt); enc=url_quote(en[:300],safe=''); seed=random.randint(1,999999)
        vdata=None
        try:
            conn=aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=conn) as s:
                async with s.get(f"https://video.pollinations.ai/prompt/{enc}?seed={seed}",
                    timeout=aiohttp.ClientTimeout(total=120)) as r:
                    if r.status==200:
                        ct=r.headers.get("content-type","")
                        if "video" in ct or "mp4" in ct:
                            d=await r.read()
                            if len(d)>5000: vdata=d
        except: pass
        try: await m2.delete()
        except: pass
        if vdata: await message.answer_video(BufferedInputFile(vdata,"nexum.mp4"),caption="🎬")
        else:
            img=await gen_image(prompt,"realistic")
            if img: await message.answer_photo(BufferedInputFile(img,"nexum.jpg"),caption="🎬 Видео недоступно, фото:")
            else: await message.answer("🎬 Видео генерация недоступна")
        return

    # МУЗЫКА
    if "%%MUSIC%%" in response:
        prompt=response.split("%%MUSIC%%")[1].split("%%")[0].strip()
        await message.answer(f"🎵 Выбери стиль для: {prompt[:40]}", reply_markup=kb_music(prompt))
        return

    # ВЕБ-ПОИСК
    if "%%WEB%%" in response:
        q=response.split("%%WEB%%")[1].split("%%")[0].strip()
        m2=await message.answer("🔍 Ищу...")
        results=await web_search(q)
        try: await m2.delete()
        except: pass
        if results:
            msgs=[{"role":"system","content":build_sys(uid,chat_id,message.chat.type)},
                  {"role":"user","content":f"Результаты поиска '{q}':\n\n{results}\n\nОтветь точно и коротко."}]
            ans=await ai_gen(msgs,max_tokens=1000,task="analysis")
            await send_long(message,strip_md(ans))
        else: await message.answer("Поиск не дал результатов 😕")
        return

    # URL
    if "%%URL%%" in response:
        url=response.split("%%URL%%")[1].split("%%")[0].strip()
        await message.answer("🔗 Читаю страницу...")
        content=await read_url(url)
        if content:
            msgs=[{"role":"system","content":build_sys(uid,chat_id,message.chat.type)},
                  {"role":"user","content":f"Сайт {url}:\n{content[:4000]}\n\nКратко суть."}]
            ans=await ai_gen(msgs,max_tokens=1000)
            await send_long(message,strip_md(ans))
        else: await message.answer("Не смог прочитать сайт 😕")
        return

    # ПОГОДА
    if "%%WTR%%" in response:
        loc=response.split("%%WTR%%")[1].split("%%")[0].strip()
        w=await get_weather(loc)
        await message.answer(f"🌤 Погода в {loc}:\n\n{w}" if w else f"Не нашёл погоду для {loc}")
        return

    # СКАЧАТЬ
    if "%%DL%%" in response:
        pts=response.split("%%DL%%")[1].split("%%")
        url=pts[0].strip()
        await message.answer("📥 Выбери формат:", reply_markup=kb_dl(url))
        return

    # КУРС
    if "%%RATE%%" in response:
        pts=response.split("%%RATE%%")[1].split("%%")
        if len(pts)>=2:
            r=await get_rate(pts[0].strip(),pts[1].strip())
            await message.answer(f"💱 {r}" if r else "Не смог получить курс")
        return

    # КАЛЬКУЛЯТОР
    if "%%CALC%%" in response:
        expr=response.split("%%CALC%%")[1].split("%%")[0].strip()
        allowed=set("0123456789+-*/().,%^ ")
        if all(c in allowed for c in expr):
            try: await message.answer(f"🧮 {expr} = {eval(expr.replace('^','**'))}")
            except: await message.answer("Не смог посчитать")
        return

    # НАПОМИНАНИЕ
    if "%%REMIND%%" in response:
        pts=response.split("%%REMIND%%")[1].split("%%")
        if len(pts)>=2:
            try:
                mins=int(pts[0].strip()); txt=pts[1].strip()
                run_at=datetime.now()+timedelta(minutes=mins)
                scheduler.add_job(remind_job,trigger=DateTrigger(run_date=run_at),args=[chat_id,txt])
                await message.answer(f"⏰ Напомню через {mins} мин:\n{txt}")
            except: await message.answer("Не понял время")
        return

    # TTS
    if "%%TTS%%" in response:
        txt=response.split("%%TTS%%")[1].split("%%")[0].strip()
        m2=await message.answer("🔊 Озвучиваю...")
        await bot.send_chat_action(chat_id,"record_voice")
        audio=await tts(txt,uid=uid)
        try: await m2.delete()
        except: pass
        if audio:
            await message.answer_voice(BufferedInputFile(audio,"nexum.mp3"),
                caption=f"🎤 {txt[:80]}{'...' if len(txt)>80 else ''}",
                reply_markup=kb_tts(txt))
        else: await message.answer(f"Не удалось озвучить.\n\n{txt}")
        return

    # ЗАПОМНИТЬ
    if "%%REMEMBER%%" in response:
        fact=response.split("%%REMEMBER%%")[1].split("%%")[0].strip()
        DB.add_memory(uid,fact,"user_stated",8)
        return

    # СТАТИСТИКА ГРУППЫ
    if "%%GRP_STATS%%" in response:
        stats=DB.get_stats(chat_id)
        if stats:
            medals=["🥇","🥈","🥉"]
            txt="📊 Статистика группы:\n\n"
            for i,s in enumerate(stats[:15],1):
                nm=s.get("name") or s.get("username") or f"User{s['uid']}"
                medal=medals[i-1] if i<=3 else f"{i}."
                txt+=f"{medal} {nm}: {s['msgs']} сообщ., {s['words']} слов\n"
            await message.answer(txt)
        else: await message.answer("Статистика пустая")
        return

    # Обычный текст
    text=strip_md(response)
    if text: await send_long(message,text)


# ══════════════════════════════════════════════════════════════════════════
# ОСНОВНОЙ ОБРАБОТЧИК
# ══════════════════════════════════════════════════════════════════════════
async def process_msg(message, text, task="general"):
    uid=message.from_user.id; chat_id=message.chat.id; chat_type=message.chat.type
    DB.ensure_user(uid,message.from_user.first_name or "",message.from_user.username or "")
    DB.extract_facts(uid,text)
    
    # URL контекст
    url_ctx=""
    urls=re.findall(r'https?://[^\s]+',text)
    if urls and any(kw in text.lower() for kw in ["расскажи","что тут","прочитай","о чём","суть"]):
        for url in urls[:1]:
            if not any(d in url for d in ["youtube","tiktok","instagram","twitter","x.com"]):
                c=await read_url(url)
                if c: url_ctx=f"\n[Сайт {url}: {c[:2000]}]"
    
    history=DB.get_history(uid,chat_id,40)
    msgs=[{"role":"system","content":build_sys(uid,chat_id,chat_type)}]
    for role,content in history[-30:]:
        msgs.append({"role":role,"content":content})
    msgs.append({"role":"user","content":text+url_ctx})
    
    await bot.send_chat_action(chat_id,"typing")
    try:
        response=await ai_gen(msgs,task=task)
        DB.add_msg(uid,chat_id,"user",text)
        DB.add_msg(uid,chat_id,"assistant",response)
        asyncio.create_task(DB.maybe_summarize(uid,chat_id))
        await process_response(message,response,uid)
    except Exception as e:
        logger.error(f"process_msg: {e}")
        await message.answer(f"⚠️ {str(e)[:200]}\n\nПопробуй снова или напиши /clear")


# ══════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════
@dp.callback_query(F.data.startswith("voice_"))
async def cb_voice(cb: CallbackQuery):
    key=cb.data[6:]; uid=cb.from_user.id
    if key=="auto": DB.set_voice(uid,"auto"); await cb.answer("🤖 Авто")
    elif key in VOICES:
        DB.set_voice(uid,key); await cb.answer(f"✅ {VOICES[key]}")
        try: await cb.message.edit_text(f"✅ Голос: {VOICES[key]}")
        except: pass
    else: await cb.answer("Неизвестный голос")

@dp.callback_query(F.data.startswith("img_"))
async def cb_img(cb: CallbackQuery):
    d=cb.data[4:]; pts=d.split("_",1)
    if len(pts)<2: await cb.answer("Ошибка"); return
    style,prompt=pts[0],pts[1]
    await cb.answer(f"🎨 {style}...")
    try: await cb.message.edit_text(f"🎨 Генерирую {style}: {prompt[:40]}...")
    except: pass
    await bot.send_chat_action(cb.message.chat.id,"upload_photo")
    img=await gen_image(prompt,style)
    if img: await cb.message.answer_photo(BufferedInputFile(img,"nexum.jpg"),caption=f"✨ {style.capitalize()}")
    else: await cb.message.answer("Не получилось 😕",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔄 Повтор",callback_data=f"img_auto_{prompt[:40]}")
    ]]))

@dp.callback_query(F.data.startswith("dl_"))
async def cb_dl(cb: CallbackQuery):
    d=cb.data[3:]; pts=d.split("_",1)
    if len(pts)<2: await cb.answer("Ошибка"); return
    fmt,url=pts[0],pts[1]
    await cb.answer(f"📥 {fmt.upper()}...")
    try: await cb.message.edit_text(f"📥 Скачиваю {fmt.upper()}...")
    except: pass
    await bot.send_chat_action(cb.message.chat.id,"upload_document")
    data,fname,err=await download(url,fmt)
    if data and fname:
        if fmt=="mp3": await cb.message.answer_audio(BufferedInputFile(data,fname),caption=f"🎵 {fname[:50]}")
        elif fmt=="mp4": await cb.message.answer_video(BufferedInputFile(data,fname),caption=f"🎬 {fname[:50]}")
        else: await cb.message.answer_document(BufferedInputFile(data,fname),caption=f"🔊 {fname[:50]}")
    else: await cb.message.answer(f"Не удалось: {err or 'ошибка'} 😕")

@dp.callback_query(F.data.startswith("tts_"))
async def cb_tts(cb: CallbackQuery):
    d=cb.data[4:]; uid=cb.from_user.id
    if d.startswith("wav_"):
        txt=d[4:]; await cb.answer("💾 WAV...")
        audio=await tts(txt,uid=uid,fmt="wav")
        if audio: await cb.message.answer_document(BufferedInputFile(audio,"nexum.wav"),caption="🔊 WAV")
        else: await cb.message.answer("Не удалось")
        return
    pts=d.split("_",2)
    if len(pts)<3: await cb.answer("Ошибка"); return
    vk=pts[0]+"_"+pts[1]; txt=pts[2]
    if vk in VOICES:
        await cb.answer(f"🎙 {VOICES[vk]}...")
        audio=await tts(txt,uid=uid,force_voice=vk)
        if audio: await cb.message.answer_voice(BufferedInputFile(audio,"nexum.mp3"),caption=f"🎤 {VOICES[vk]}")
        else: await cb.message.answer("Не удалось")
    else: await cb.answer("Неизвестный голос")

@dp.callback_query(F.data.startswith("music_"))
async def cb_music(cb: CallbackQuery):
    d=cb.data[6:]; pts=d.split("_",1)
    if len(pts)<2: await cb.answer("Ошибка"); return
    style,prompt=pts[0],pts[1]
    await cb.answer(f"🎵 Генерирую реальную музыку...")
    try: await cb.message.edit_text(f"🎵 Создаю музыку: {style}\nТема: {prompt[:40]}\n\n⏳ Подожди 30-60 секунд...")
    except: pass
    await bot.send_chat_action(cb.message.chat.id,"upload_document")
    audio_data=await gen_music(prompt,style)
    if audio_data:
        await cb.message.answer_audio(
            BufferedInputFile(audio_data,f"nexum_{style}.flac"),
            caption=f"🎵 {style.capitalize()}: {prompt[:50]}\n\nNEXUM v4.1 Music")
    else:
        # Fallback — текст песни + озвучка
        try:
            lyrics_p=f"Напиши текст песни в стиле {style} на тему: {prompt}. Куплет + Припев + Куплет. Живо, цепляет."
            lyrics=await ai_gen([{"role":"user","content":lyrics_p}],max_tokens=500,task="creative")
            clean=strip_md(lyrics)
            await cb.message.answer(f"🎵 {style}: {prompt[:40]}\n\n{clean}")
            voice_audio=await tts(clean[:900],uid=cb.from_user.id)
            if voice_audio:
                await cb.message.answer_voice(BufferedInputFile(voice_audio,"song.mp3"),
                    caption=f"🎤 Текст песни озвучен | {style}")
        except Exception as e:
            await cb.message.answer(f"Ошибка генерации: {e}")

@dp.callback_query(F.data.startswith("confirm_"))
async def cb_confirm(cb: CallbackQuery):
    aid=cb.data[8:]; action=PENDING.pop(aid,None)
    if not action:
        await cb.answer("Устарело"); 
        try: await cb.message.edit_text("❌ Устарело, повтори команду")
        except: pass
        return
    await cb.answer("✅ Выполняю...")
    try: await cb.message.edit_text("⚙️ Удаляю...")
    except: pass
    atype=action.get("type"); chat_id=action.get("chat_id")
    
    if atype=="delete_keyword":
        kw=action.get("keyword","")
        with db() as c:
            rows=c.execute("SELECT msg_id FROM group_msgs WHERE chat_id=? AND LOWER(text) LIKE ? AND msg_id IS NOT NULL",
                (chat_id,f"%{kw.lower()}%")).fetchall()
        ids=[r[0] for r in rows if r[0]]
        deleted=await delete_bulk(chat_id,ids)
        await cb.message.answer(f"✅ Удалено {deleted} сообщений со словом '{kw}'")
    
    elif atype=="clean_chat":
        with db() as c:
            rows=c.execute("SELECT msg_id FROM group_msgs WHERE chat_id=? AND msg_id IS NOT NULL ORDER BY id DESC LIMIT 500",
                (chat_id,)).fetchall()
        ids=[r[0] for r in rows if r[0]]
        deleted=await delete_bulk(chat_id,ids)
        await cb.message.answer(f"✅ Удалено {deleted} сообщений")

@dp.callback_query(F.data.startswith("cancel_"))
async def cb_cancel(cb: CallbackQuery):
    PENDING.pop(cb.data[7:],None)
    await cb.answer("❌ Отменено")
    try: await cb.message.edit_text("❌ Отменено")
    except: pass

@dp.callback_query(F.data.startswith("grp_"))
async def cb_grp(cb: CallbackQuery):
    chat_id=cb.message.chat.id; uid=cb.from_user.id; action=cb.data[4:]
    if not await is_admin(chat_id,uid):
        await cb.answer("Только для администраторов"); return
    
    if action=="stats":
        stats=DB.get_stats(chat_id)
        if stats:
            medals=["🥇","🥈","🥉"]
            txt="📊 Статистика группы:\n\n"
            for i,s in enumerate(stats[:15],1):
                nm=s.get("name") or s.get("username") or f"User{s['uid']}"
                medal=medals[i-1] if i<=3 else f"{i}."
                txt+=f"{medal} {nm}: {s['msgs']} сообщ., {s['words']} слов\n"
            await cb.message.answer(txt)
        else: await cb.message.answer("Пусто")
        await cb.answer()
    
    elif action=="analytics":
        await cb.answer("📈...")
        msgs_data=DB.get_msgs(chat_id,200)
        hours: Dict[int,int]={}
        for _,_,_,_,ts in msgs_data:
            try: h=datetime.fromisoformat(ts).hour; hours[h]=hours.get(h,0)+1
            except: pass
        peak=max(hours,key=hours.get) if hours else 0
        stats=DB.get_stats(chat_id)
        total_msgs=sum(s['msgs'] for s in stats)
        total_users=len(stats)
        txt=(f"📈 Аналитика:\n\nВсего сообщений: {total_msgs}\nАктивных: {total_users}\n"
             f"Пик активности: {peak}:00\n\nТоп участников:\n")
        for s in stats[:5]:
            nm=s.get("name") or s.get("username") or f"User{s['uid']}"
            txt+=f"• {nm}: {s['msgs']} сообщ.\n"
        await cb.message.answer(txt)
    
    elif action=="members":
        try:
            cnt=await bot.get_chat_member_count(chat_id)
            await cb.message.answer(f"👥 Участников: {cnt}")
        except: await cb.message.answer("Не смог получить")
        await cb.answer()
    
    elif action=="clean":
        aid=f"clean_{chat_id}_{int(time.time())}"
        PENDING[aid]={"type":"clean_chat","chat_id":chat_id}
        await cb.message.answer("⚠️ Удалить последние 500 сообщений?",reply_markup=kb_confirm(aid,"clean"))
        await cb.answer()
    
    else: await cb.answer()

@dp.callback_query(F.data.startswith("ch_"))
async def cb_ch(cb: CallbackQuery):
    chat_id=cb.message.chat.id; action=cb.data[3:]
    if action=="analyze":
        await cb.answer("📊 Анализирую...")
        await cb.message.answer("📊 Анализирую канал...")
        an=await analyze_channel(chat_id)
        if an:
            style_p=[{"role":"user","content":f"На основе анализа, опиши стиль постов в 3-5 предложений:\n{an}"}]
            style=await ai_gen(style_p,max_tokens=200,task="analysis")
            ch=await bot.get_chat(chat_id)
            DB.save_channel(chat_id,ch.title or "?",an,style or "")
        await send_long(cb.message,strip_md(an) if an else "Не смог проанализировать")
    elif action=="post":
        await cb.answer("📝...")
        post=await gen_post(chat_id)
        if post:
            await cb.message.answer(
                f"📝 Пост:\n\n{strip_md(post)}\n\n---\nОпубликовать?",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✅ Опубликовать",callback_data=f"pub_{chat_id}"),
                    InlineKeyboardButton(text="🔄 Другой",callback_data="ch_post"),
                ]])
            )
    elif action=="schedule":
        await cb.message.answer("/schedule ЧЧ:ММ тема\nПример: /schedule 09:00 утренние новости")
        await cb.answer()
    elif action=="style":
        ch=DB.get_channel(chat_id)
        if ch and ch.get("style"): await cb.message.answer(f"🎨 Стиль:\n\n{ch['style']}")
        else: await cb.message.answer("Нет анализа. Нажми 📊 Анализ канала")
        await cb.answer()
    else: await cb.answer()

@dp.callback_query(F.data.startswith("pub_"))
async def cb_pub(cb: CallbackQuery):
    chat_id=int(cb.data[4:])
    if not await is_admin(chat_id,cb.from_user.id):
        await cb.answer("Только для администраторов"); return
    txt=cb.message.text or ""
    if "Пост:\n\n" in txt:
        post=txt.split("Пост:\n\n")[1].split("\n\n---\n")[0]
        try:
            await bot.send_message(chat_id,post)
            await cb.answer("✅ Опубликован!")
            try: await cb.message.edit_text("✅ Пост опубликован!")
            except: pass
        except Exception as e: await cb.message.answer(f"Ошибка: {e}")
    else: await cb.answer("Текст не найден")


# ══════════════════════════════════════════════════════════════════════════
# МЕДИА УТИЛИТЫ
# ══════════════════════════════════════════════════════════════════════════
def extract_video(path):
    if not FFMPEG: return None,None
    fp=path+"_f.jpg"; ap=path+"_a.ogg"; fo=ao=False
    try:
        r=subprocess.run(["ffmpeg","-i",path,"-ss","00:00:01","-vframes","1","-q:v","2","-y",fp],
            capture_output=True,timeout=30)
        fo=r.returncode==0 and os.path.getsize(fp)>500 if os.path.exists(fp) else False
    except: pass
    try:
        r=subprocess.run(["ffmpeg","-i",path,"-vn","-acodec","libopus","-b:a","64k","-y",ap],
            capture_output=True,timeout=60)
        ao=r.returncode==0 and os.path.getsize(ap)>200 if os.path.exists(ap) else False
    except: pass
    return (fp if fo else None),(ap if ao else None)


# ══════════════════════════════════════════════════════════════════════════
# КОМАНДЫ
# ══════════════════════════════════════════════════════════════════════════
@dp.message(CommandStart())
async def cmd_start(message: Message):
    name=(message.from_user.first_name or "").strip()
    DB.ensure_user(message.from_user.id,name,message.from_user.username or "")
    await message.answer(
        f"{'Привет, '+name+'!' if name else 'Привет!'} Я NEXUM v4.1 🤖\n\n"
        "Что умею:\n"
        "💬 Общаюсь на любом языке как носитель\n"
        "🎨 Генерирую фото (10 стилей)\n"
        "🎵 Создаю реальную музыку\n"
        "🎬 Генерирую видео\n"
        "🔊 Озвучиваю (50+ голосов, WAV/MP3)\n"
        "📥 Скачиваю YouTube/TikTok/Instagram\n"
        "👁 Анализирую фото, видео, голосовые\n"
        "📊 Управляю группами и каналами\n"
        "🗑 Удаляю сообщения по ключевому слову\n"
        "🔍 Ищу актуальную информацию\n"
        "♾️ Помню тебя навсегда\n\n"
        "/help — все команды\n\n"
        "Пиши что нужно 👇"
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "NEXUM v4.1\n\n"
        "Основные:\n"
        "/start /help /voice /clear /stats /myfacts /myname\n\n"
        "Группа и канал (только для админов):\n"
        "/groupstats — статистика\n"
        "/manage — управление группой\n"
        "/channel — управление каналом\n"
        "/schedule ЧЧ:ММ тема — автопосты\n"
        "/delete слово — удалить сообщения со словом\n"
        "/post тема — написать пост\n"
        "/improve — анализ кода\n\n"
        "КАК ДОБАВИТЬ В КАНАЛ:\n"
        "Настройки канала → Администраторы → Добавить → @ainexum_bot\n"
        "Дать права: публикация, удаление сообщений\n\n"
        "В группе: @ainexum_bot или reply на мои сообщения"
    )

@dp.message(Command("voice"))
async def cmd_voice(message: Message):
    await message.answer("🎙 Выбери голос:", reply_markup=kb_voice())

@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    DB.clear_history(message.from_user.id,message.chat.id)
    await message.answer("🧹 История очищена! Память о тебе сохранена.")

@dp.message(Command("myname"))
async def cmd_myname(message: Message):
    pts=message.text.split(maxsplit=1)
    if len(pts)<2: await message.answer("/myname ТвоёИмя"); return
    name=pts[1].strip()[:30]
    DB.set_name(message.from_user.id,name)
    DB.add_memory(message.from_user.id,f"Зовут {name}","identity",10)
    await message.answer(f"Запомнил, {name}! 👊")

@dp.message(Command("myfacts"))
async def cmd_myfacts(message: Message):
    u=DB.get_user(message.from_user.id)
    mems=u.get("memory",[])
    if not mems: await message.answer("Пока ничего не знаю\nРасскажи что-нибудь!"); return
    by_cat: Dict[str,List]={}
    for m in mems: by_cat.setdefault(m["cat"],[]).append(m["fact"])
    txt="📝 Что знаю о тебе:\n\n"
    for cat,facts in by_cat.items():
        txt+=f"[{cat.upper()}]\n"+"".join(f"  • {f}\n" for f in facts[:5])+"\n"
    await message.answer(txt)

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    uid=message.from_user.id; u=DB.get_user(uid)
    if not u: await message.answer("/start"); return
    v=DB.get_voice(uid); vn=VOICES.get(v,"Авто") if v!="auto" else "Авто"
    await message.answer(
        f"📊 Профиль:\n\n"
        f"👤 {u.get('name','Без имени')}\n"
        f"💬 Сообщений: {u.get('messages',0)}\n"
        f"🧠 Фактов: {len(u.get('memory',[]))}\n"
        f"🎙 Голос: {vn}\n"
        f"📅 С: {(u.get('first_seen') or '')[:10]}"
    )

@dp.message(Command("groupstats"))
async def cmd_groupstats(message: Message):
    stats=DB.get_stats(message.chat.id)
    if not stats: await message.answer("Статистика пустая 📊"); return
    medals=["🥇","🥈","🥉"]
    txt="📊 Статистика группы:\n\n"
    for i,s in enumerate(stats[:15],1):
        nm=s.get("name") or s.get("username") or f"User{s['uid']}"
        medal=medals[i-1] if i<=3 else f"{i}."
        txt+=f"{medal} {nm}: {s['msgs']} сообщ."
        if s.get("words"): txt+=f", {s['words']} слов"
        txt+="\n"
    await message.answer(txt,reply_markup=kb_group())

@dp.message(Command("manage"))
async def cmd_manage(message: Message):
    if not await is_admin(message.chat.id,message.from_user.id):
        await message.answer("Только для администраторов"); return
    await message.answer("⚙️ Управление группой:", reply_markup=kb_group())

@dp.message(Command("channel"))
async def cmd_channel(message: Message):
    await message.answer(
        "📺 Управление каналом\n\n"
        "Как добавить бота в канал:\n"
        "1. Открой настройки канала\n"
        "2. Администраторы → Добавить\n"
        "3. Найди @ainexum_bot\n"
        "4. Дай права: публикация, изменение, удаление\n\n"
        "После добавления используй кнопки:",
        reply_markup=kb_channel()
    )

@dp.message(Command("schedule"))
async def cmd_schedule(message: Message):
    pts=message.text.split(maxsplit=2)
    if len(pts)<3: await message.answer("/schedule ЧЧ:ММ тема\nПример: /schedule 09:00 новости дня"); return
    if not await is_admin(message.chat.id,message.from_user.id):
        await message.answer("Только для администраторов"); return
    try:
        h,m=map(int,pts[1].split(":")); topic=pts[2]
        scheduler.add_job(sched_post_job,trigger=CronTrigger(hour=h,minute=m),
            args=[message.chat.id,topic],id=f"sp_{message.chat.id}_{h}_{m}",replace_existing=True)
        with db() as c:
            c.execute("INSERT INTO schedules(chat_id,hour,minute,topic)VALUES(?,?,?,?)",
                (message.chat.id,h,m,topic))
        await message.answer(f"✅ Каждый день в {pts[1]}:\n{topic}")
    except ValueError: await message.answer("Неверный формат. Используй ЧЧ:ММ")

@dp.message(Command("delete"))
async def cmd_delete(message: Message):
    if not await is_admin(message.chat.id,message.from_user.id):
        await message.answer("Только для администраторов"); return
    pts=message.text.split(maxsplit=1)
    if len(pts)<2: await message.answer("/delete ключевое_слово"); return
    kw=pts[1].strip()
    # Проверим есть ли вообще что удалять
    with db() as c:
        cnt=c.execute("SELECT COUNT(*) FROM group_msgs WHERE chat_id=? AND LOWER(text) LIKE ? AND msg_id IS NOT NULL",
            (message.chat.id,f"%{kw.lower()}%")).fetchone()[0]
    if cnt==0:
        await message.answer(f"Не нашёл сообщений со словом '{kw}' в базе.\n\nБот сохраняет сообщения только с момента запуска.")
        return
    aid=f"dk_{message.chat.id}_{int(time.time())}"
    PENDING[aid]={"type":"delete_keyword","chat_id":message.chat.id,"keyword":kw}
    await message.answer(f"⚠️ Найдено {cnt} сообщений со словом '{kw}'.\nУдалить?",
        reply_markup=kb_confirm(aid,kw))

@dp.message(Command("post"))
async def cmd_post(message: Message):
    pts=message.text.split(maxsplit=1); topic=pts[1].strip() if len(pts)>1 else ""
    await message.answer("📝 Генерирую пост...")
    post=await gen_post(message.chat.id,topic)
    if post:
        await message.answer(
            f"📝 Готово:\n\n{strip_md(post)}\n\n---\nОпубликовать?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Опубликовать",callback_data=f"pub_{message.chat.id}"),
                InlineKeyboardButton(text="🔄 Другой",callback_data="ch_post"),
            ]])
        )
    else: await message.answer("Не получилось создать пост")

@dp.message(Command("improve"))
async def cmd_improve(message: Message):
    await message.answer("🔍 Анализирую код NEXUM...")
    await bot.send_chat_action(message.chat.id,"typing")
    try:
        with open(__file__,"r",encoding="utf-8") as f: src=f.read()
        prompt=f"""Ты Python эксперт. Анализируй бот NEXUM v4.1 (первые 5000 символов):

{src[:5000]}

Дай конкретно:
1. БАГИ — что сломано прямо сейчас
2. ТОП-5 улучшений — с примерами кода
3. 3 новых функции которые реально добавить"""
        s=await ai_gen([{"role":"user","content":prompt}],max_tokens=2000,task="code")
        await send_long(message,s)
    except Exception as e: await message.answer(f"Ошибка: {e}")


# ══════════════════════════════════════════════════════════════════════════
# ХЭНДЛЕРЫ СООБЩЕНИЙ
# ══════════════════════════════════════════════════════════════════════════
@dp.message(F.text)
async def handle_text(message: Message):
    text=message.text or ""; uid=message.from_user.id
    chat_id=message.chat.id; chat_type=message.chat.type

    # Всегда сохраняем для групп
    if chat_type in("group","supergroup","channel"):
        DB.update_group(chat_id,uid,
            message.from_user.first_name or "",
            message.from_user.username or "",
            text=text, msg_id=message.message_id)

    # В группе — только если упомянули или reply
    if chat_type in("group","supergroup"):
        try:
            me=await bot.get_me(); my_id=me.id
            my_un=f"@{(me.username or '').lower()}"
            mentioned=False
            if message.entities:
                for e in message.entities:
                    if e.type=="mention" and text[e.offset:e.offset+e.length].lower()==my_un:
                        mentioned=True; break
                    elif e.type=="text_mention" and e.user and e.user.id==my_id:
                        mentioned=True; break
            if not mentioned and my_un and my_un in text.lower(): mentioned=True
            replied=(message.reply_to_message and message.reply_to_message.from_user and
                     message.reply_to_message.from_user.id==my_id)
            if not mentioned and not replied: return
            if me.username:
                text=re.sub(rf'@{me.username}\s*','',text,flags=re.IGNORECASE).strip()
            text=text or "привет"
        except Exception as e: logger.error(f"Group: {e}"); return

    # Reply на медиа
    rep=message.reply_to_message
    if rep:
        if rep.video_note:
            await handle_vn_q(message,rep.video_note,text); return
        elif rep.video:
            await handle_vid(message,rep.video.file_id,text or rep.caption or ""); return
        elif rep.photo:
            await handle_photo_q(message,rep.photo[-1],text or "Опиши фото"); return
        elif rep.voice:
            await handle_voice_q(message,rep.voice,text); return

    task="general"
    tl=text.lower()
    if any(k in tl for k in ["код","python","javascript","функция","скрипт","алгоритм"]): task="code"
    elif any(k in tl for k in ["новости","2025","2026","актуальн","текущий","цена","курс"]): task="analysis"
    elif any(k in tl for k in ["напиши стихи","рассказ","сценарий","песню","творч"]): task="creative"
    
    await process_msg(message,text,task)

@dp.message(F.voice)
async def handle_voice(message: Message):
    uid=message.from_user.id; chat_id=message.chat.id
    if message.chat.type in("group","supergroup"):
        DB.update_group(chat_id,uid,message.from_user.first_name or "",
            message.from_user.username or "",mtype="voice",msg_id=message.message_id)
    await bot.send_chat_action(chat_id,"typing")
    try:
        file=await bot.get_file(message.voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg",delete=False) as tmp:
            await bot.download_file(file.file_path,tmp.name); ap=tmp.name
        text=await stt(ap)
        try: os.unlink(ap)
        except: pass
        if not text or len(text.strip())<2:
            await message.answer("🎤 Не распознал. Попробуй ещё раз."); return
        await message.answer(f"🎤 {text}")
        await process_msg(message,text)
    except Exception as e: logger.error(f"Voice: {e}"); await message.answer("Ошибка голосового 😕")

@dp.message(F.video_note)
async def handle_vidnote(message: Message):
    uid=message.from_user.id; chat_id=message.chat.id
    if message.chat.type in("group","supergroup"):
        DB.update_group(chat_id,uid,message.from_user.first_name or "",
            message.from_user.username or "",mtype="video_note",msg_id=message.message_id)
    await bot.send_chat_action(chat_id,"typing")
    try:
        file=await bot.get_file(message.video_note.file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp4",delete=False) as tmp:
            await bot.download_file(file.file_path,tmp.name); vp=tmp.name
        vis=speech=None
        if FFMPEG:
            fp,ap=extract_video(vp)
            try: os.unlink(vp)
            except: pass
            if fp:
                with open(fp,"rb") as f: b64=base64.b64encode(f.read()).decode()
                try: os.unlink(fp)
                except: pass
                vis=await gemini_vision(b64,"Опиши видеокружок: кто, что делает, эмоции.")
            if ap:
                speech=await stt(ap)
                try: os.unlink(ap)
                except: pass
        else:
            try: os.unlink(vp)
            except: pass
        parts=[]
        if vis: parts.append(f"👁 {vis[:300]}")
        if speech: parts.append(f"🎤 {speech}")
        if parts: await message.answer("📹 "+" | ".join(parts))
        ctx="Пользователь прислал видеокружок. "
        if vis: ctx+=f"Вижу: {vis}. "
        if speech: ctx+=f"Говорит: {speech}. "
        if not vis and not speech: ctx+="Не смог проанализировать."
        await process_msg(message,ctx)
    except Exception as e: logger.error(f"VN: {e}"); await message.answer("Не смог обработать кружочек 😕")

@dp.message(F.video)
async def on_video(message: Message):
    uid=message.from_user.id; chat_id=message.chat.id
    if message.chat.type in("group","supergroup"):
        DB.update_group(chat_id,uid,message.from_user.first_name or "",
            message.from_user.username or "",mtype="video",msg_id=message.message_id)
    await handle_vid(message,message.video.file_id,message.caption or "")

async def handle_vid(message, file_id, caption=""):
    uid=message.from_user.id; chat_id=message.chat.id
    await bot.send_chat_action(chat_id,"typing")
    try:
        file=await bot.get_file(file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp4",delete=False) as tmp:
            await bot.download_file(file.file_path,tmp.name); vp=tmp.name
        vis=speech=None
        if FFMPEG:
            fp,ap=extract_video(vp)
            try: os.unlink(vp)
            except: pass
            if fp:
                with open(fp,"rb") as f: b64=base64.b64encode(f.read()).decode()
                try: os.unlink(fp)
                except: pass
                vis=await gemini_vision(b64,caption or "Опиши что видно на кадре из видео")
            if ap:
                speech=await stt(ap)
                try: os.unlink(ap)
                except: pass
        else:
            try: os.unlink(vp)
            except: pass
        parts=[]
        if vis: parts.append(f"👁 {vis[:400]}")
        if speech: parts.append(f"🎤 {speech[:300]}")
        if parts: await message.answer("📹 "+"\n\n".join(parts))
        ctx="Видео. "
        if caption: ctx+=f"Подпись: {caption}. "
        if vis: ctx+=f"На видео: {vis}. "
        if speech: ctx+=f"Говорят: {speech}. "
        if not vis and not speech: ctx+="Не смог проанализировать."
        await process_msg(message,ctx)
    except Exception as e: logger.error(f"Video: {e}"); await message.answer("Не смог обработать видео 😕")

@dp.message(F.photo)
async def handle_photo(message: Message):
    uid=message.from_user.id; chat_id=message.chat.id
    if message.chat.type in("group","supergroup"):
        DB.update_group(chat_id,uid,message.from_user.first_name or "",
            message.from_user.username or "",mtype="photo",msg_id=message.message_id)
    caption=message.caption or "Опиши подробно что на фото"
    await bot.send_chat_action(chat_id,"typing")
    try:
        photo=message.photo[-1]
        file=await bot.get_file(photo.file_id)
        with tempfile.NamedTemporaryFile(suffix=".jpg",delete=False) as tmp:
            await bot.download_file(file.file_path,tmp.name); pp=tmp.name
        with open(pp,"rb") as f: b64=base64.b64encode(f.read()).decode()
        try: os.unlink(pp)
        except: pass
        an=await gemini_vision(b64,caption)
        if an:
            DB.add_msg(uid,chat_id,"user",f"[фото] {caption}")
            DB.add_msg(uid,chat_id,"assistant",an)
            await message.answer(strip_md(an))
        else: await message.answer("Не смог проанализировать фото 😕")
    except Exception as e: logger.error(f"Photo: {e}"); await message.answer("Ошибка 😕")

@dp.message(F.document)
async def handle_doc(message: Message):
    if message.chat.type in("group","supergroup"):
        DB.update_group(message.chat.id,message.from_user.id,
            message.from_user.first_name or "",message.from_user.username or "",
            mtype="document",msg_id=message.message_id)
    await bot.send_chat_action(message.chat.id,"typing")
    try:
        file=await bot.get_file(message.document.file_id)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            await bot.download_file(file.file_path,tmp.name); fp=tmp.name
        try:
            with open(fp,"r",encoding="utf-8",errors="ignore") as f: content=f.read()[:12000]
        except: content="[Не удалось прочитать]"
        try: os.unlink(fp)
        except: pass
        fname=message.document.file_name or "файл"
        cap=message.caption or "Проанализируй этот файл"
        await process_msg(message,f"{cap}\n\nФайл '{fname}':\n{content}",task="analysis")
    except Exception as e: logger.error(f"Doc: {e}"); await message.answer("Не удалось прочитать 😕")

@dp.message(F.audio)
async def handle_audio(message: Message):
    await bot.send_chat_action(message.chat.id,"typing")
    try:
        file=await bot.get_file(message.audio.file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp3",delete=False) as tmp:
            await bot.download_file(file.file_path,tmp.name); ap=tmp.name
        text=await stt(ap)
        try: os.unlink(ap)
        except: pass
        if text: await message.answer(f"🎵 Транскрипция:\n\n{text}")
        else: await process_msg(message,f"Аудио файл. {message.caption or ''}")
    except Exception as e: logger.error(f"Audio: {e}"); await message.answer("Не смог обработать 😕")

@dp.message(F.sticker)
async def handle_sticker(message: Message):
    if message.chat.type in("group","supergroup"):
        DB.update_group(message.chat.id,message.from_user.id,
            message.from_user.first_name or "",message.from_user.username or "",
            mtype="sticker",msg_id=message.message_id)
    await process_msg(message,"[стикер] Отреагируй живо!")

@dp.message(F.location)
async def handle_loc(message: Message):
    lat=message.location.latitude; lon=message.location.longitude
    w=await get_weather(f"{lat},{lon}")
    if w: await message.answer(f"📍 Погода:\n\n{w}")
    else: await message.answer("📍 Локация получена!")

async def handle_vn_q(message, vn, q):
    file=await bot.get_file(vn.file_id)
    with tempfile.NamedTemporaryFile(suffix=".mp4",delete=False) as tmp:
        await bot.download_file(file.file_path,tmp.name); vp=tmp.name
    vis=speech=None
    if FFMPEG:
        fp,ap=extract_video(vp)
        try: os.unlink(vp)
        except: pass
        if fp:
            with open(fp,"rb") as f: b64=base64.b64encode(f.read()).decode()
            try: os.unlink(fp)
            except: pass
            vis=await gemini_vision(b64,q or "Опиши кружочек")
        if ap:
            speech=await stt(ap)
            try: os.unlink(ap)
            except: pass
    else:
        try: os.unlink(vp)
        except: pass
    ctx=f"Вопрос: {q}. Кружочек — "
    if vis: ctx+=f"видно: {vis}. "
    if speech: ctx+=f"говорит: {speech}. "
    await process_msg(message,ctx)

async def handle_photo_q(message, photo, q):
    uid=message.from_user.id; chat_id=message.chat.id
    file=await bot.get_file(photo.file_id)
    with tempfile.NamedTemporaryFile(suffix=".jpg",delete=False) as tmp:
        await bot.download_file(file.file_path,tmp.name); pp=tmp.name
    with open(pp,"rb") as f: b64=base64.b64encode(f.read()).decode()
    try: os.unlink(pp)
    except: pass
    an=await gemini_vision(b64,q)
    if an:
        DB.add_msg(uid,chat_id,"user",f"[фото+вопрос] {q}")
        DB.add_msg(uid,chat_id,"assistant",an)
        await message.answer(strip_md(an))
    else: await message.answer("Не смог 😕")

async def handle_voice_q(message, voice, q):
    await bot.send_chat_action(message.chat.id,"typing")
    file=await bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg",delete=False) as tmp:
        await bot.download_file(file.file_path,tmp.name); ap=tmp.name
    text=await stt(ap)
    try: os.unlink(ap)
    except: pass
    if text: await process_msg(message,f"{q}\n\nГолосовое: {text}")
    else: await message.answer("Не распознал речь 🎤")

@dp.my_chat_member()
async def on_added(update):
    try:
        ns=update.new_chat_member.status; chat_id=update.chat.id
        if ns in(ChatMemberStatus.MEMBER,ChatMemberStatus.ADMINISTRATOR):
            chat=await bot.get_chat(chat_id); ctype=chat.type
            if ctype=="channel":
                await bot.send_message(chat_id,
                    "Привет! Я NEXUM v4.1 в вашем канале.\n\n"
                    "Анализирую стиль канала для персонализации постов...",
                    reply_markup=kb_channel())
                asyncio.create_task(auto_analyze(chat_id,chat.title or "?"))
            elif ctype in("group","supergroup"):
                await bot.send_message(chat_id,
                    "Привет! Я NEXUM v4.1 🤖\n\n"
                    "@ainexum_bot или reply — я отвечу\n/help — команды")
    except Exception as e: logger.error(f"Added: {e}")

async def auto_analyze(chat_id, title):
    try:
        await asyncio.sleep(5)
        an=await analyze_channel(chat_id)
        if an:
            sp=[{"role":"user","content":f"Опиши стиль постов для канала '{title}' в 3-5 предложений:\n{an}"}]
            style=await ai_gen(sp,max_tokens=200,task="analysis")
            DB.save_channel(chat_id,title,an,style or "")
            logger.info(f"Channel {chat_id} analyzed")
    except Exception as e: logger.error(f"Auto analyze: {e}")


# ══════════════════════════════════════════════════════════════════════════
# ЗАПУСК
# ══════════════════════════════════════════════════════════════════════════
async def restore_schedules():
    with db() as c:
        rows=c.execute("SELECT chat_id,hour,minute,topic FROM schedules WHERE active=1").fetchall()
    for chat_id,h,m,topic in rows:
        scheduler.add_job(sched_post_job,trigger=CronTrigger(hour=h,minute=m),
            args=[chat_id,topic],id=f"sp_{chat_id}_{h}_{m}",replace_existing=True)
    logger.info(f"Restored {len(rows)} schedules")

async def main():
    init_db()
    scheduler.start()
    await restore_schedules()
    
    logger.info("="*55)
    logger.info("NEXUM v4.1 Starting...")
    logger.info(f"Gemini:   {len(GEMINI_KEYS)} keys")
    logger.info(f"Groq:     {len(GROQ_KEYS)} keys")
    logger.info(f"DeepSeek: {len(DEEPSEEK_KEYS)} keys")
    logger.info(f"Claude:   {len(CLAUDE_KEYS)} keys")
    logger.info(f"Grok:     {len(GROK_KEYS)} keys")
    logger.info(f"ffmpeg:   {'YES' if FFMPEG else 'NO'}")
    logger.info(f"yt-dlp:   {'YES' if YTDLP else 'NO'}")
    logger.info("="*55)
    
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
