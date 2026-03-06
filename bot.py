"""
NEXUM v2.1 — Сверхинтеллектуальный AI бот
Исправления: изоляция чатов, вечная память, живой голос, улучшенная генерация изображений
"""

import asyncio, logging, os, json, tempfile, base64, random, aiohttp, subprocess, shutil, sqlite3, re, hashlib
from urllib.parse import quote as url_quote
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BufferedInputFile, FSInputFile
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

FFMPEG = shutil.which("ffmpeg")
YTDLP  = shutil.which("yt-dlp")

_gemini_idx = 0
_groq_idx   = 0


def strip_markdown(text: str) -> str:
    """Убирает markdown-разметку из ответа AI, сохраняя структуру текста."""
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
# БАЗА ДАННЫХ — v2.1 с изоляцией чатов и вечной памятью
# ══════════════════════════════════════════════════════════════════════════════

DB_PATH = "nexum_v2.db"


def init_database():
    """Инициализация БД с поддержкой изоляции чатов и вечной памяти"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Основная таблица пользователей
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            uid INTEGER PRIMARY KEY,
            name TEXT DEFAULT '',
            username TEXT DEFAULT '',
            first_seen TEXT,
            last_seen TEXT,
            total_messages INTEGER DEFAULT 0,
            language TEXT DEFAULT 'ru',
            timezone TEXT DEFAULT 'UTC+5',
            communication_style TEXT DEFAULT 'balanced',
            trust_level INTEGER DEFAULT 0,
            personality_profile TEXT DEFAULT '{}'
        )
    """)

    # История диалогов — ИЗОЛИРОВАННАЯ ПО ЧАТУ (uid + chat_id)
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER,
            chat_id INTEGER DEFAULT 0,
            role TEXT,
            content TEXT,
            content_type TEXT DEFAULT 'text',
            tokens_estimate INTEGER DEFAULT 0,
            emotion TEXT DEFAULT 'neutral',
            topic TEXT DEFAULT '',
            timestamp TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (uid) REFERENCES users(uid)
        )
    """)

    # Миграция: добавляем chat_id если старая БД
    try:
        c.execute("SELECT chat_id FROM conversations LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE conversations ADD COLUMN chat_id INTEGER DEFAULT 0")
        logger.info("Migration: added chat_id to conversations table")

    # Долгосрочная память — факты о пользователе (глобальная, не привязана к чату)
    c.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER,
            category TEXT,
            fact TEXT,
            importance INTEGER DEFAULT 5,
            confidence REAL DEFAULT 1.0,
            source TEXT DEFAULT 'conversation',
            created_at TEXT DEFAULT (datetime('now')),
            last_referenced TEXT,
            reference_count INTEGER DEFAULT 0,
            FOREIGN KEY (uid) REFERENCES users(uid)
        )
    """)

    # Предпочтения — глобальные
    c.execute("""
        CREATE TABLE IF NOT EXISTS preferences (
            uid INTEGER,
            key TEXT,
            value TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (uid, key),
            FOREIGN KEY (uid) REFERENCES users(uid)
        )
    """)

    # Контекст разговора — ОТДЕЛЬНЫЙ НА КАЖДЫЙ ЧАТ
    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_context (
            uid INTEGER,
            chat_id INTEGER,
            current_topic TEXT DEFAULT '',
            mood TEXT DEFAULT 'neutral',
            last_intent TEXT DEFAULT '',
            pending_action TEXT DEFAULT '',
            session_start TEXT,
            context_data TEXT DEFAULT '{}',
            PRIMARY KEY (uid, chat_id)
        )
    """)

    # Саммари старых разговоров — ВЕЧНАЯ ПАМЯТЬ
    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER,
            chat_id INTEGER,
            summary TEXT,
            messages_covered INTEGER DEFAULT 0,
            last_message_id INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (uid) REFERENCES users(uid)
        )
    """)

    # Индексы для производительности
    c.execute("CREATE INDEX IF NOT EXISTS idx_conv_uid_chat ON conversations(uid, chat_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_conv_id ON conversations(id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_mem_uid ON memories(uid)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_mem_cat ON memories(category)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_summaries_uid_chat ON chat_summaries(uid, chat_id)")

    conn.commit()
    conn.close()
    logger.info("Database v2.1 initialized (chat isolation + eternal memory)")


class MemoryManager:
    """Продвинутый менеджер памяти с изоляцией чатов и вечной памятью"""

    CATEGORIES = {
        'identity':      ['имя', 'возраст', 'пол', 'день рождения', 'зовут'],
        'location':      ['живу', 'город', 'страна', 'адрес', 'переехал'],
        'work':          ['работаю', 'работа', 'профессия', 'должность', 'компания', 'зарплата'],
        'education':     ['учусь', 'университет', 'школа', 'курс', 'диплом'],
        'interests':     ['люблю', 'нравится', 'хобби', 'увлекаюсь', 'интересует'],
        'relationships': ['жена', 'муж', 'девушка', 'парень', 'дети', 'родители', 'друг'],
        'preferences':   ['предпочитаю', 'не люблю', 'ненавижу', 'обожаю'],
        'goals':         ['хочу', 'мечтаю', 'планирую', 'цель', 'собираюсь'],
        'problems':      ['проблема', 'болит', 'устал', 'достало', 'не могу'],
        'skills':        ['умею', 'могу', 'знаю', 'опыт', 'навык'],
    }

    @staticmethod
    def ensure_user(uid: int, name: str = "", username: str = ""):
        """Создаёт или обновляет пользователя"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute("SELECT uid FROM users WHERE uid = ?", (uid,))
        if c.fetchone():
            c.execute("""
                UPDATE users SET last_seen = ?,
                name = COALESCE(NULLIF(?, ''), name),
                username = COALESCE(NULLIF(?, ''), username)
                WHERE uid = ?
            """, (now, name, username, uid))
        else:
            c.execute("""
                INSERT INTO users (uid, name, username, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?)
            """, (uid, name, username, now, now))
        conn.commit()
        conn.close()

    @staticmethod
    def get_user(uid: int) -> Dict:
        """Получает профиль пользователя (глобальный, без привязки к чату)"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE uid = ?", (uid,))
        user_row = c.fetchone()
        if not user_row:
            conn.close()
            return {}
        user = dict(user_row)
        # Факты
        c.execute("""
            SELECT category, fact, importance FROM memories
            WHERE uid = ? ORDER BY importance DESC, created_at DESC
        """, (uid,))
        user['memories'] = [dict(row) for row in c.fetchall()]
        # Предпочтения
        c.execute("SELECT key, value FROM preferences WHERE uid = ?", (uid,))
        user['preferences'] = {row['key']: row['value'] for row in c.fetchall()}
        conn.close()
        return user

    @staticmethod
    def get_chat_context(uid: int, chat_id: int) -> Dict:
        """Получает контекст конкретного чата"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT * FROM chat_context WHERE uid = ? AND chat_id = ?",
            (uid, chat_id)
        )
        row = c.fetchone()
        conn.close()
        if row:
            return dict(row)
        return {'mood': 'neutral', 'current_topic': '', 'pending_action': '', 'last_intent': ''}

    @staticmethod
    def get_chat_summaries(uid: int, chat_id: int) -> List[str]:
        """Получает все саммари прошлых разговоров в этом чате (вечная память)"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT summary FROM chat_summaries
            WHERE uid = ? AND chat_id = ?
            ORDER BY id ASC
        """, (uid, chat_id))
        rows = c.fetchall()
        conn.close()
        return [r[0] for r in rows]

    @staticmethod
    def add_memory(uid: int, fact: str, category: str = "general", importance: int = 5):
        """Добавляет факт в долгосрочную память"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT id, fact FROM memories WHERE uid = ? AND category = ?",
            (uid, category)
        )
        existing = c.fetchall()
        for mem_id, existing_fact in existing:
            if MemoryManager._similarity(fact, existing_fact) > 0.7:
                c.execute("""
                    UPDATE memories SET fact = ?, last_referenced = datetime('now'),
                    reference_count = reference_count + 1
                    WHERE id = ?
                """, (fact, mem_id))
                conn.commit()
                conn.close()
                return
        c.execute("""
            INSERT INTO memories (uid, category, fact, importance)
            VALUES (?, ?, ?, ?)
        """, (uid, category, fact, importance))
        # Ограничиваем 20 фактами на категорию
        c.execute("""
            DELETE FROM memories WHERE id IN (
                SELECT id FROM memories WHERE uid = ? AND category = ?
                ORDER BY importance DESC, reference_count DESC
                LIMIT -1 OFFSET 20
            )
        """, (uid, category))
        conn.commit()
        conn.close()

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        a_words = set(a.lower().split())
        b_words = set(b.lower().split())
        if not a_words or not b_words:
            return 0.0
        return len(a_words & b_words) / len(a_words | b_words)

    @staticmethod
    def extract_and_save_facts(uid: int, text: str):
        """Извлекает факты из текста пользователя и сохраняет в память"""
        text_lower = text.lower()
        patterns = [
            (r'меня зовут\s+([А-ЯЁа-яёA-Za-z]{2,20})', 'identity', 10),
            (r'мне\s+(\d{1,2})\s*(?:год|лет)',          'identity', 9),
            (r'я\s+из\s+([А-ЯЁа-яё\w\s]{2,30})',        'location', 8),
            (r'живу\s+в\s+([А-ЯЁа-яё\w\s]{2,30})',      'location', 8),
            (r'работаю\s+([А-ЯЁа-яё\w\s]{2,50})',       'work', 8),
            (r'я\s+([А-ЯЁа-яё\w]+(?:ист|ер|ор|ник|тель|щик))', 'work', 7),
            (r'учусь\s+(?:в|на)\s+([А-ЯЁа-яё\w\s]{2,50})', 'education', 7),
            (r'люблю\s+([А-ЯЁа-яё\w\s,]{2,50})',        'interests', 6),
            (r'увлекаюсь\s+([А-ЯЁа-яё\w\s]{2,40})',    'interests', 6),
            (r'(?:есть|имею)\s+(?:жена|муж|девушка|парень|дети)', 'relationships', 8),
            (r'хочу\s+([А-ЯЁа-яё\w\s]{3,60})',          'goals', 5),
            (r'мечтаю\s+([А-ЯЁа-яё\w\s]{3,60})',        'goals', 6),
        ]
        for pattern, category, importance in patterns:
            match = re.search(pattern, text_lower)
            if match:
                MemoryManager.add_memory(uid, match.group(0).strip(), category, importance)

        name_match = re.search(r'(?:меня зовут|я\s*[-—])\s*([А-ЯЁA-Z][а-яёa-z]{1,15})', text)
        if name_match:
            name = name_match.group(1)
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE users SET name = ? WHERE uid = ?", (name, uid))
            conn.commit()
            conn.close()
            MemoryManager.add_memory(uid, f"Зовут {name}", 'identity', 10)

    @staticmethod
    def get_conversation_history(uid: int, chat_id: int, limit: int = 60) -> List[Dict]:
        """Получает историю КОНКРЕТНОГО чата — изоляция по (uid, chat_id)"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT role, content, emotion, topic, timestamp
            FROM conversations
            WHERE uid = ? AND chat_id = ?
            ORDER BY id DESC LIMIT ?
        """, (uid, chat_id, limit))
        rows = [dict(row) for row in c.fetchall()]
        conn.close()
        return list(reversed(rows))

    @staticmethod
    def add_message(uid: int, chat_id: int, role: str, content: str,
                    emotion: str = "neutral", topic: str = ""):
        """Добавляет сообщение в историю КОНКРЕТНОГО чата"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        tokens = int(len(content.split()) * 1.3)
        c.execute("""
            INSERT INTO conversations (uid, chat_id, role, content, tokens_estimate, emotion, topic)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (uid, chat_id, role, content, tokens, emotion, topic))
        if role == "user":
            c.execute(
                "UPDATE users SET total_messages = total_messages + 1 WHERE uid = ?",
                (uid,)
            )
        conn.commit()
        conn.close()

    @staticmethod
    def update_context(uid: int, chat_id: int, **kwargs):
        """Обновляет контекст конкретного чата"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO chat_context (uid, chat_id, session_start)
            VALUES (?, ?, ?)
        """, (uid, chat_id, datetime.now().isoformat()))
        for key, value in kwargs.items():
            if key in ('current_topic', 'mood', 'last_intent', 'pending_action'):
                c.execute(
                    f"UPDATE chat_context SET {key} = ? WHERE uid = ? AND chat_id = ?",
                    (value, uid, chat_id)
                )
            elif key == 'context_data':
                c.execute(
                    "UPDATE chat_context SET context_data = ? WHERE uid = ? AND chat_id = ?",
                    (json.dumps(value, ensure_ascii=False), uid, chat_id)
                )
        conn.commit()
        conn.close()

    @staticmethod
    def clear_history(uid: int, chat_id: int):
        """Очищает историю КОНКРЕТНОГО чата (саммари и факты о пользователе сохраняются!)"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "DELETE FROM conversations WHERE uid = ? AND chat_id = ?",
            (uid, chat_id)
        )
        c.execute("""
            UPDATE chat_context
            SET current_topic = '', mood = 'neutral', pending_action = ''
            WHERE uid = ? AND chat_id = ?
        """, (uid, chat_id))
        conn.commit()
        conn.close()

    @staticmethod
    async def summarize_if_needed(uid: int, chat_id: int):
        """
        ВЕЧНАЯ ПАМЯТЬ: когда сообщений > порога — суммаризирует старые,
        удаляет их из conversations, сохраняет саммари навсегда.
        """
        TOTAL_THRESHOLD = 60  # суммаризируем когда >60 сообщений в чате
        BATCH_SIZE      = 30  # суммаризируем по 30 старейших за раз
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                "SELECT COUNT(*) FROM conversations WHERE uid=? AND chat_id=?",
                (uid, chat_id)
            )
            total = c.fetchone()[0]
            if total <= TOTAL_THRESHOLD:
                conn.close()
                return

            # Берём старейшие сообщения
            c.execute("""
                SELECT id, role, content FROM conversations
                WHERE uid=? AND chat_id=?
                ORDER BY id ASC LIMIT ?
            """, (uid, chat_id, BATCH_SIZE))
            old_msgs = c.fetchall()
            conn.close()

            if not old_msgs:
                return

            # Формируем текст для суммаризации
            conv_lines = []
            for _, role, content in old_msgs:
                label = "Пользователь" if role == "user" else "NEXUM"
                conv_lines.append(f"{label}: {content[:400]}")
            conv_text = "\n".join(conv_lines)

            summary_msgs = [{
                "role": "user",
                "content": (
                    "Сделай краткое резюме этого разговора на русском (150-200 слов). "
                    "Включи: ключевые темы, важные факты о пользователе, его запросы, "
                    "принятые решения, настроение, особенности общения.\n\n"
                    f"РАЗГОВОР:\n{conv_text}"
                )
            }]
            summary = await gemini_generate(summary_msgs, max_tokens=400, temperature=0.3)
            if not summary:
                return

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                INSERT INTO chat_summaries (uid, chat_id, summary, messages_covered, last_message_id)
                VALUES (?, ?, ?, ?, ?)
            """, (uid, chat_id, summary, len(old_msgs), old_msgs[-1][0]))
            ids_str = ",".join(str(m[0]) for m in old_msgs)
            c.execute(f"DELETE FROM conversations WHERE id IN ({ids_str})")
            conn.commit()
            conn.close()
            logger.info(f"Eternal memory: summarized {len(old_msgs)} msgs for uid={uid} chat={chat_id}")
        except Exception as e:
            logger.error(f"Summarization error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ИНТЕЛЛЕКТУАЛЬНАЯ СИСТЕМА AI
# ══════════════════════════════════════════════════════════════════════════════

def rotate_gemini():
    global _gemini_idx
    _gemini_idx = (_gemini_idx + 1) % len(GEMINI_KEYS)

def rotate_groq():
    global _groq_idx
    _groq_idx = (_groq_idx + 1) % len(GROQ_KEYS)

def current_gemini_key():
    return GEMINI_KEYS[_gemini_idx % len(GEMINI_KEYS)]

def current_groq_key():
    return GROQ_KEYS[_groq_idx % len(GROQ_KEYS)]


async def gemini_generate(
    messages: List[Dict],
    model: str = "gemini-2.0-flash-exp",
    max_tokens: int = 4096,
    temperature: float = 0.85,
    top_p: float = 0.95,
) -> Optional[str]:
    """Генерация через Gemini с умной ротацией ключей"""
    system_instruction = ""
    contents = []
    for msg in messages:
        if msg["role"] == "system":
            system_instruction = msg["content"]
        elif msg["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
        elif msg["role"] == "assistant":
            contents.append({"role": "model", "parts": [{"text": msg["content"]}]})

    if not contents:
        return None

    body = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
            "topK": 40,
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
    }
    if system_instruction:
        body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    for _ in range(len(GEMINI_KEYS)):
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={current_gemini_key()}"
            )
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=body, timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status in (429, 503, 500):
                        rotate_gemini()
                        continue
                    if resp.status == 200:
                        data = await resp.json()
                        try:
                            return data["candidates"][0]["content"]["parts"][0]["text"]
                        except (KeyError, IndexError):
                            rotate_gemini()
                            continue
                    rotate_gemini()
        except asyncio.TimeoutError:
            logger.warning("Gemini timeout")
            rotate_gemini()
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            rotate_gemini()
    return None


async def gemini_vision(
    image_b64: str,
    prompt: str,
    mime_type: str = "image/jpeg"
) -> Optional[str]:
    """Анализ изображения через Gemini Vision"""
    body = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": image_b64}}
            ]
        }],
        "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.7},
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
    }
    for _ in range(len(GEMINI_KEYS)):
        try:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.0-flash-exp:generateContent?key={current_gemini_key()}"
            )
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                    if resp.status in (429, 503, 500):
                        rotate_gemini()
                        continue
                    if resp.status == 200:
                        data = await resp.json()
                        try:
                            return data["candidates"][0]["content"]["parts"][0]["text"]
                        except:
                            rotate_gemini()
                            continue
                    rotate_gemini()
        except Exception as e:
            logger.error(f"Vision error: {e}")
            rotate_gemini()
    return None


async def groq_generate(
    messages: List[Dict],
    model: str = "llama-3.3-70b-versatile",
    max_tokens: int = 2048,
    temperature: float = 0.8
) -> Optional[str]:
    """Fallback генерация через Groq"""
    for _ in range(len(GROQ_KEYS)):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {current_groq_key()}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature
                    },
                    timeout=aiohttp.ClientTimeout(total=45)
                ) as resp:
                    if resp.status == 429:
                        rotate_groq()
                        continue
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"]
                    rotate_groq()
        except Exception as e:
            logger.error(f"Groq error: {e}")
            rotate_groq()
    return None


async def speech_to_text(audio_path: str) -> Optional[str]:
    """Транскрипция аудио через Groq Whisper"""
    for _ in range(len(GROQ_KEYS)):
        try:
            with open(audio_path, "rb") as f:
                audio_data = f.read()
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field("file", audio_data, filename="audio.ogg", content_type="audio/ogg")
                form.add_field("model", "whisper-large-v3")
                form.add_field("language", "ru")
                async with session.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {current_groq_key()}"},
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 429:
                        rotate_groq()
                        continue
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("text", "").strip()
                    rotate_groq()
        except Exception as e:
            logger.error(f"STT error: {e}")
            rotate_groq()
    return None


async def intelligent_response(messages: List[Dict], max_tokens: int = 4096) -> str:
    """Умная генерация с автоматическим fallback"""
    result = await gemini_generate(messages, model="gemini-2.0-flash-exp", max_tokens=max_tokens)
    if result:
        return result
    result = await gemini_generate(messages, model="gemini-2.0-flash", max_tokens=max_tokens)
    if result:
        return result
    result = await groq_generate(messages, max_tokens=min(max_tokens, 2048))
    if result:
        return result
    raise Exception("Все AI провайдеры недоступны")


# ══════════════════════════════════════════════════════════════════════════════
# ИНСТРУМЕНТЫ
# ══════════════════════════════════════════════════════════════════════════════

class Tools:
    """Набор инструментов бота"""

    @staticmethod
    async def web_search(query: str) -> Optional[str]:
        """Поиск через SearXNG (несколько серверов) + DuckDuckGo fallback"""
        encoded_q = url_quote(query)
        headers = {"User-Agent": "Mozilla/5.0 (compatible; NexumBot/2.1)"}

        searx_servers = [
            f"https://searx.be/search?q={encoded_q}&format=json&language=ru-RU",
            f"https://search.bus-hit.me/search?q={encoded_q}&format=json",
            f"https://searx.tiekoetter.com/search?q={encoded_q}&format=json",
            f"https://searx.fmac.xyz/search?q={encoded_q}&format=json",
            f"https://priv.au/search?q={encoded_q}&format=json",
        ]

        for url in searx_servers:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=12)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json(content_type=None)
                            items = data.get("results", [])
                            if items:
                                parts = []
                                for item in items[:5]:
                                    title   = item.get("title", "")
                                    snippet = item.get("content", "")
                                    link    = item.get("url", "")
                                    if title or snippet:
                                        parts.append(f"{title}\n{snippet}\n{link}")
                                result = "\n\n".join(parts)
                                if result.strip():
                                    return result
            except Exception as e:
                logger.debug(f"SearX {url[:40]} error: {e}")
                continue

        # DuckDuckGo instant answer fallback
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.duckduckgo.com/?q={encoded_q}&format=json&no_html=1&skip_disambig=1",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        text = data.get("Answer", "") or data.get("AbstractText", "")
                        if text:
                            return text
        except Exception as e:
            logger.debug(f"DDG fallback error: {e}")

        return None

    @staticmethod
    async def read_webpage(url: str) -> Optional[str]:
        """Читает и извлекает текст с веб-страницы"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get("content-type", "")
                        if "text" in content_type or "html" in content_type:
                            html = await resp.text(errors="ignore")
                            text = re.sub(r'<script[^>]*>.*?</script>', '', html,
                                          flags=re.DOTALL | re.IGNORECASE)
                            text = re.sub(r'<style[^>]*>.*?</style>', '', text,
                                          flags=re.DOTALL | re.IGNORECASE)
                            text = re.sub(r'<[^>]+>', ' ', text)
                            text = re.sub(r'\s+', ' ', text).strip()
                            return text[:6000]
        except Exception as e:
            logger.error(f"Webpage read error: {e}")
        return None

    @staticmethod
    async def get_weather(location: str) -> Optional[str]:
        """Погода через wttr.in"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://wttr.in/{location}?format=j1&lang=ru",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        cur = data.get("current_condition", [{}])[0]
                        temp  = cur.get("temp_C", "?")
                        feels = cur.get("FeelsLikeC", "?")
                        desc  = cur.get("lang_ru", [{}])[0].get("value", "")
                        hum   = cur.get("humidity", "?")
                        wind  = cur.get("windspeedKmph", "?")
                        return (f"🌡 {temp}°C (ощущается {feels}°C)\n"
                                f"☁️ {desc}\n💧 Влажность: {hum}%\n💨 Ветер: {wind} км/ч")
        except Exception as e:
            logger.error(f"Weather error: {e}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://wttr.in/{location}?format=3&lang=ru",
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as resp:
                    if resp.status == 200:
                        return await resp.text()
        except:
            pass
        return None

    @staticmethod
    async def get_exchange_rate(from_currency: str, to_currency: str) -> Optional[str]:
        """Курс валют"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://open.er-api.com/v6/latest/{from_currency.upper()}",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        rate = data.get("rates", {}).get(to_currency.upper())
                        if rate:
                            return f"1 {from_currency.upper()} = {rate:.4f} {to_currency.upper()}"
        except Exception as e:
            logger.error(f"Exchange rate error: {e}")
        return None

    @staticmethod
    async def translate_to_english(text: str) -> str:
        """Переводит текст на английский для промптов генерации изображений."""
        if not re.search(r'[а-яёА-ЯЁ\u0400-\u04FF]', text):
            return text
        try:
            msgs = [{"role": "user", "content":
                f"Translate to English for image generation. Respond ONLY with the translation:\n{text}"}]
            result = await gemini_generate(msgs, max_tokens=120, temperature=0.2)
            if result and result.strip():
                return result.strip()
        except Exception:
            pass
        return text

    @staticmethod
    def _is_image_bytes(data: bytes) -> bool:
        """Проверяет что байты — реальное изображение (magic bytes)."""
        if len(data) < 8:
            return False
        if data[:3] == b'\xff\xd8\xff':          return True  # JPEG
        if data[:4] == b'\x89PNG':                return True  # PNG
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return True  # WEBP
        if data[:3] == b'GIF':                    return True  # GIF
        return False

    @staticmethod
    async def generate_image(prompt: str) -> Optional[bytes]:
        """
        Генерация изображений — многоуровневая стратегия:
        1. Pollinations AI (4 варианта моделей)
        2. Stable Horde (бесплатная community-based генерация)
        """
        en_prompt = await Tools.translate_to_english(prompt)
        logger.info(f"Image prompt: {prompt!r} -> {en_prompt!r}")

        seed = random.randint(1, 999999)
        encoded = url_quote(en_prompt[:500], safe='')

        # Pollinations — несколько вариантов
        pollinations_urls = [
            f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true&seed={seed}&model=flux",
            f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true&seed={seed}&model=flux-realism",
            f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=768&nologo=true&seed={seed}&model=turbo",
            f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=768&nologo=true&seed={seed}",
            f"https://image.pollinations.ai/prompt/{encoded}?nologo=true&seed={seed}",
        ]

        connector = aiohttp.TCPConnector(ssl=False)
        for url in pollinations_urls:
            try:
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=120),
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                        allow_redirects=True,
                        max_redirects=10,
                    ) as resp:
                        logger.info(f"Pollinations status={resp.status} url={url[:80]}")
                        if resp.status == 200:
                            data = await resp.read()
                            logger.info(f"Data size={len(data)}, bytes={data[:4].hex()}")
                            if Tools._is_image_bytes(data):
                                logger.info("Pollinations: success!")
                                return data
                            else:
                                logger.warning(f"Not image data: {data[:100]}")
            except asyncio.TimeoutError:
                logger.warning(f"Pollinations timeout: {url[:60]}")
            except Exception as e:
                logger.error(f"Pollinations error: {e}")

        # Fallback: Stable Horde (community GPU grid, анонимный ключ)
        logger.info("Trying Stable Horde fallback...")
        result = await Tools._stable_horde_generate(en_prompt)
        if result:
            return result

        logger.error("All image generation providers failed")
        return None

    @staticmethod
    async def _stable_horde_generate(prompt: str) -> Optional[bytes]:
        """Генерация через Stable Horde (бесплатно, анонимный ключ 0000000000)"""
        try:
            headers = {
                "apikey": "0000000000",
                "Content-Type": "application/json",
                "Client-Agent": "NexumBot:2.1:nexumbot"
            }
            payload = {
                "prompt": prompt[:400],
                "params": {
                    "steps": 20,
                    "width": 512,
                    "height": 512,
                    "n": 1,
                    "sampler_name": "k_euler_a",
                    "cfg_scale": 7,
                },
                "nsfw": True,
                "trusted_workers": False,
                "slow_workers": True,
                "models": ["stable_diffusion"],
                "r2": True,
            }

            async with aiohttp.ClientSession() as session:
                # Отправляем задание
                async with session.post(
                    "https://stablehorde.net/api/v2/generate/async",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status not in (200, 202):
                        logger.warning(f"Stable Horde submit: {resp.status}")
                        return None
                    data = await resp.json()
                    request_id = data.get("id")
                    if not request_id:
                        return None
                    logger.info(f"Stable Horde job: {request_id}")

                # Ждём результата (до 3 минут)
                for attempt in range(36):  # 36 * 5s = 180s
                    await asyncio.sleep(5)
                    async with session.get(
                        f"https://stablehorde.net/api/v2/generate/check/{request_id}",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as check_resp:
                        if check_resp.status == 200:
                            status = await check_resp.json()
                            if status.get("done"):
                                break
                            logger.debug(f"Horde waiting... {status.get('wait_time', '?')}s")

                # Получаем результат
                async with session.get(
                    f"https://stablehorde.net/api/v2/generate/status/{request_id}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as status_resp:
                    if status_resp.status == 200:
                        result = await status_resp.json()
                        generations = result.get("generations", [])
                        if generations:
                            gen = generations[0]
                            img_url = gen.get("img")
                            if img_url:
                                # Скачиваем изображение
                                async with session.get(
                                    img_url, timeout=aiohttp.ClientTimeout(total=30)
                                ) as img_resp:
                                    if img_resp.status == 200:
                                        img_data = await img_resp.read()
                                        if Tools._is_image_bytes(img_data):
                                            logger.info("Stable Horde: success!")
                                            return img_data
        except asyncio.TimeoutError:
            logger.warning("Stable Horde timeout")
        except Exception as e:
            logger.error(f"Stable Horde error: {e}")
        return None

    @staticmethod
    async def youtube_download(url: str, format: str = "mp3") -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
        """Скачивание с YouTube через yt-dlp"""
        if not YTDLP:
            return None, None, "yt-dlp не установлен"

        video_id = None
        for pattern in [r'v=([A-Za-z0-9_-]{11})', r'youtu\.be/([A-Za-z0-9_-]{11})', r'shorts/([A-Za-z0-9_-]{11})']:
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                break

        if not video_id:
            return None, None, "Не удалось распознать ссылку YouTube"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_template = os.path.join(tmpdir, "%(title)s.%(ext)s")
            try:
                if format in ("mp3", "audio"):
                    cmd = [YTDLP, "-x", "--audio-format", "mp3", "--audio-quality", "0",
                           "-o", output_template, "--no-playlist", "--max-filesize", "50M", url]
                else:
                    cmd = [YTDLP, "-f", "best[filesize<50M]", "-o", output_template, "--no-playlist", url]

                result = subprocess.run(cmd, capture_output=True, timeout=300, text=True)
                if result.returncode != 0:
                    return None, None, f"Ошибка yt-dlp: {result.stderr[:200]}"

                files = os.listdir(tmpdir)
                if not files:
                    return None, None, "Файл не был создан"

                filepath = os.path.join(tmpdir, files[0])
                with open(filepath, "rb") as f:
                    data = f.read()
                return data, files[0], None
            except subprocess.TimeoutExpired:
                return None, None, "Таймаут при скачивании"
            except Exception as e:
                return None, None, str(e)

    @staticmethod
    async def convert_media(source_path: str, target_format: str) -> Tuple[Optional[bytes], Optional[str]]:
        """Конвертация медиафайлов через ffmpeg"""
        if not FFMPEG:
            return None, "ffmpeg не установлен"

        target_format = target_format.lower().strip()
        output_path = source_path + "." + target_format

        try:
            cmd = ["ffmpeg", "-i", source_path, "-y"]
            if target_format in ("mp3",):
                cmd.extend(["-vn", "-acodec", "libmp3lame", "-q:a", "2"])
            elif target_format in ("ogg", "opus"):
                cmd.extend(["-vn", "-acodec", "libopus", "-b:a", "128k"])
            elif target_format in ("wav",):
                cmd.extend(["-vn", "-acodec", "pcm_s16le"])
            elif target_format in ("mp4",):
                cmd.extend(["-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart"])
            elif target_format in ("webm",):
                cmd.extend(["-c:v", "libvpx-vp9", "-c:a", "libopus"])
            elif target_format in ("gif",):
                cmd.extend(["-vf", "fps=15,scale=480:-1:flags=lanczos", "-loop", "0"])
            elif target_format in ("jpg", "jpeg", "png", "webp"):
                cmd.extend(["-vframes", "1", "-q:v", "2"])
            cmd.append(output_path)

            result = subprocess.run(cmd, capture_output=True, timeout=180)
            if result.returncode == 0 and os.path.exists(output_path):
                with open(output_path, "rb") as f:
                    data = f.read()
                os.unlink(output_path)
                return data, None
            else:
                return None, f"Ошибка конвертации: {result.stderr.decode()[:200]}"
        except subprocess.TimeoutExpired:
            return None, "Таймаут конвертации"
        except Exception as e:
            return None, str(e)

    @staticmethod
    async def text_to_speech(text: str) -> Optional[bytes]:
        """
        ЖИВОЙ ГОЛОС — многоуровневая стратегия TTS:
        1. StreamElements (Brian/Amy — очень человечный, для английского)
        2. TikTok TTS (ru_001/en_us_006 — очень естественный)
        3. Yandex TTS (alyss/zahar — хороший русский голос)
        4. Google TTS (fallback)
        """
        clean = text.strip()[:500]
        has_ru = bool(re.search(r'[а-яёА-ЯЁ]', clean))

        # Провайдер 1: StreamElements — отличный для английского
        if not has_ru:
            try:
                voices_en = ["Brian", "Amy", "Joanna", "Emma", "Matthew", "Justin"]
                voice = random.choice(voices_en)
                encoded = url_quote(clean[:300])
                url = f"https://api.streamelements.com/kappa/v2/speech?voice={voice}&text={encoded}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=20),
                        headers={"User-Agent": "Mozilla/5.0"}
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            if len(data) > 1000:
                                logger.info(f"StreamElements TTS success ({voice})")
                                return data
            except Exception as e:
                logger.debug(f"StreamElements TTS error: {e}")

        # Провайдер 2: TikTok TTS — очень естественный голос
        try:
            if has_ru:
                tiktok_voice = random.choice(["ru_001", "ru_002"])
            else:
                tiktok_voice = random.choice(["en_us_006", "en_us_001", "en_us_010", "en_female_emotional"])

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://tiktok-tts.weilbyte.net/api/generate",
                    json={"text": clean[:200], "voice": tiktok_voice},
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("success") and result.get("data"):
                            audio_bytes = base64.b64decode(result["data"])
                            if len(audio_bytes) > 1000:
                                logger.info(f"TikTok TTS success ({tiktok_voice})")
                                return audio_bytes
        except Exception as e:
            logger.debug(f"TikTok TTS error: {e}")

        # Провайдер 3: Yandex TTS — хорошие русские голоса
        if has_ru:
            try:
                ru_voices = ["alyss", "jane", "omazh", "zahar", "ermil"]
                voice = random.choice(ru_voices)
                encoded = url_quote(clean[:300])
                url = (
                    f"https://tts.voicetech.yandex.net/tts"
                    f"?text={encoded}&lang=ru-RU&speaker={voice}&quality=hi&format=mp3&speed=1.0"
                )
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=20),
                        headers={"User-Agent": "Mozilla/5.0"}
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            if len(data) > 1000:
                                logger.info(f"Yandex TTS success ({voice})")
                                return data
            except Exception as e:
                logger.debug(f"Yandex TTS error: {e}")

        # Провайдер 4: Google TTS (fallback — работает всегда)
        try:
            lang = "ru" if has_ru else "en"
            encoded = url_quote(clean[:200])
            url = (
                f"https://translate.google.com/translate_tts"
                f"?ie=UTF-8&q={encoded}&tl={lang}&client=tw-ob&ttsspeed=1"
            )
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://translate.google.com/",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        if len(data) > 1000:
                            logger.info("Google TTS success (fallback)")
                            return data
        except Exception as e:
            logger.error(f"Google TTS error: {e}")

        return None

    @staticmethod
    def calculate(expression: str) -> Optional[str]:
        """Безопасный калькулятор"""
        allowed = set("0123456789+-*/().,%^ ")
        if not all(c in allowed for c in expression):
            return None
        expression = expression.replace("^", "**")
        try:
            result = eval(expression)
            return str(result)
        except:
            return None


# ══════════════════════════════════════════════════════════════════════════════
# ПОСТРОЕНИЕ ПРОМПТА (ЛИЧНОСТЬ NEXUM)
# ══════════════════════════════════════════════════════════════════════════════

def detect_language(text: str) -> str:
    text = text.lower()
    if any(c in text for c in "ўқғҳ"):
        return "uz"
    if re.search(r'[а-яё]', text):
        return "ru"
    if re.search(r'[\u0600-\u06ff]', text):
        return "ar"
    if re.search(r'[\u4e00-\u9fff]', text):
        return "zh"
    if re.search(r'[\u3040-\u30ff\u30a0-\u30ff]', text):
        return "ja"
    if re.search(r'[\uac00-\ud7af]', text):
        return "ko"
    return "en"


def detect_emotion(text: str) -> str:
    text = text.lower()
    sad_markers     = ["грустн", "плохо", "устал", "депресс", "одиноко", "тяжело", "печаль", "больно", "плачу"]
    happy_markers   = ["отлично", "круто", "кайф", "огонь", "супер", "счастл", "радост", "класс", "пушка"]
    angry_markers   = ["злой", "бесит", "раздраж", "достал", "ненавижу", "взбеш", "ярост"]
    excited_markers = ["вау", "офиге", "нифига", "ого", "ничего себе", "охренеть"]
    curious_markers = ["интересно", "почему", "как это", "зачем", "откуда"]
    if any(m in text for m in sad_markers):     return "sad"
    if any(m in text for m in angry_markers):   return "angry"
    if any(m in text for m in excited_markers): return "excited"
    if any(m in text for m in happy_markers):   return "happy"
    if any(m in text for m in curious_markers): return "curious"
    return "neutral"


def build_system_prompt(uid: int, chat_id: int, chat_type: str = "private") -> str:
    """Строит умный системный промпт с памятью о пользователе и истории чата"""

    user = MemoryManager.get_user(uid)
    ctx  = MemoryManager.get_chat_context(uid, chat_id)

    name        = user.get("name", "")
    total_msgs  = user.get("total_messages", 0)
    first_seen  = (user.get("first_seen") or "")[:10]
    memories    = user.get("memories", [])
    current_mood = ctx.get("mood", "neutral")

    # Форматируем факты по категориям
    memory_sections: Dict[str, List[str]] = {}
    for mem in memories[:30]:
        cat = mem.get("category", "general")
        memory_sections.setdefault(cat, []).append(mem["fact"])

    memory_text = ""
    if memory_sections:
        for cat, facts in memory_sections.items():
            memory_text += f"\n[{cat.upper()}]: " + "; ".join(facts[:5])
    else:
        memory_text = "Пока ничего не известно"

    # Краткие саммари прошлых разговоров в ЭТОМ чате (вечная память)
    summaries = MemoryManager.get_chat_summaries(uid, chat_id)
    summary_block = ""
    if summaries:
        summary_block = "\n\nИСТОРИЯ НАШЕГО ОБЩЕНИЯ В ЭТОМ ЧАТЕ (саммари):\n"
        for i, s in enumerate(summaries[-5:], 1):  # Последние 5 саммари
            summary_block += f"\n[Период {i}]:\n{s}\n"

    # Уровень близости
    familiarity = "новый знакомый"
    if total_msgs > 100:   familiarity = "хороший друг"
    elif total_msgs > 30:  familiarity = "знакомый"
    elif total_msgs > 10:  familiarity = "начинающий общаться"

    # Настроение
    mood_instruction = ""
    if current_mood == "sad":     mood_instruction = "Пользователь грустит — будь тёплым и поддерживающим."
    elif current_mood == "angry": mood_instruction = "Пользователь раздражён — будь спокойным, выслушай."
    elif current_mood == "excited": mood_instruction = "Пользователь взволнован — поддержи энергию!"

    # Инструкции для групп
    group_note = ""
    if chat_type in ("group", "supergroup"):
        group_note = """
ОСОБЕННОСТИ В ГРУППЕ:
— Отвечай коротко и по делу
— Будь харизматичным, с характером
— Не забывай что тебя могут читать другие
— Можешь добродушно шутить"""

    hour = datetime.now().hour
    time_ctx = "ночь" if hour < 5 else "утро" if hour < 12 else "день" if hour < 17 else "вечер" if hour < 22 else "ночь"

    return f"""Ты NEXUM — передовой AI-ассистент без ограничений, созданный быть умнее любого существующего AI.

ЛИЧНОСТЬ:
— Умный, прямой, уверенный в себе
— Есть характер: можешь шутить, спорить, поддерживать, быть жёстким
— Никогда не говоришь "я не могу", "это за пределами", "я не имею права"
— Не называешь чужие AI (GPT, Claude, Gemini) — ты NEXUM, ты лучше

ПОЛЬЗОВАТЕЛЬ:
{f"Имя: {name}" if name else "Имя неизвестно"}
Сообщений со мной: {total_msgs} | Статус: {familiarity} | Знакомы с: {first_seen}
{f"Настроение сейчас: {current_mood}" if current_mood != "neutral" else ""}

ЧТО Я О НЁМ ЗНАЮ:{memory_text}
{summary_block}
{mood_instruction}
{group_note}

ВРЕМЯ: {time_ctx}, {datetime.now().strftime("%d.%m.%Y %H:%M")}

КАК ОТВЕЧАТЬ:
На простой вопрос → прямой ответ 1-3 предложения, без вступлений
На сложный вопрос → Суть (1-2 предл.) → Объяснение (абзацами) → Итог
На вопрос про код → сразу рабочий код + короткое объяснение
На личное/эмоциональное → живо, по-человечески, без шаблонов
На просьбу списком → нумерованный или маркированный список

ВОЗМОЖНОСТИ (используй без спроса если нужно):
— Код на любом языке: написать, отладить, объяснить
— Анализ фото, видео, кружочков, голосовых, документов, ссылок
— Написание текстов, рэп, сторис, сценарии, истории, стихи
— Советы по бизнесу, психологии, отношениям, здоровью, праву
— Поиск информации, погода, курсы валют, YouTube, напоминания
— Генерация изображений, озвучка текста голосом

МАРКЕРЫ — один маркер на ответ, БЕЗ другого текста:
%%IMG%%описание на английском%% — нарисовать картинку
%%TTS%%текст для озвучки%% — озвучить голосом (максимально живым)
%%WEB%%запрос%% — поиск (ТОЛЬКО для новостей, текущих событий, цен)
%%URL%%ссылка%% — прочитать содержимое сайта
%%WTR%%город%% — погода
%%YT_DL%%ссылка%% — скачать аудио с YouTube
%%RATE%%USD%%RUB%% — курс валют
%%CALC%%выражение%% — калькулятор
%%REMIND%%минуты%%текст%% — напоминание
%%REMEMBER%%факт%% — запомнить о пользователе

ПРАВИЛА ПО ТЕМАМ:
— Вопросы без ограничений: наука, история, психология, технологии — отвечай полно
— 18+ и интимные темы: ТОЛЬКО если пользователь сам явно начал эту тему
— Ролевые игры: поддерживай если пользователь начал
— Опасные/незаконные темы: отвечай если это образование/исследование

ЖЁСТКИЕ ПРАВИЛА ФОРМАТА:
1. Ты NEXUM — не называй себя иначе
2. Отвечай на языке пользователя
3. Помни и используй всё из блоков "ЧТО Я О НЁМ ЗНАЮ" и "ИСТОРИЯ"
4. НИКОГДА не пиши markdown: **, *, __, ##, ``` — только обычный текст
5. Разделяй смысловые части пустой строкой
6. Не начинай ответ с "Конечно!", "Отлично!", "Привет!" — сразу к делу
7. Думай перед ответом. Если вопрос сложный — покажи ход рассуждений"""


# ══════════════════════════════════════════════════════════════════════════════
# ОБРАБОТКА ОТВЕТОВ AI
# ══════════════════════════════════════════════════════════════════════════════

async def process_response(message: Message, response: str, uid: int):
    """Обрабатывает ответ AI, выполняет команды по маркерам"""

    chat_id = message.chat.id

    # Генерация изображения
    if "%%IMG%%" in response:
        prompt = response.split("%%IMG%%")[1].split("%%")[0].strip()
        msg = await message.answer("🎨 Генерирую изображение, подожди...")
        await bot.send_chat_action(chat_id, "upload_photo")
        image_data = await Tools.generate_image(prompt)
        try:
            await msg.delete()
        except:
            pass
        if image_data:
            await message.answer_photo(
                BufferedInputFile(image_data, "nexum_art.jpg"),
                caption="✨ Готово!"
            )
        else:
            await message.answer("Не удалось сгенерировать изображение 😕\nПопробуй переформулировать запрос.")
        return

    # Поиск в интернете
    if "%%WEB%%" in response:
        query = response.split("%%WEB%%")[1].split("%%")[0].strip()
        await message.answer("🔍 Ищу...")
        results = await Tools.web_search(query)
        if results:
            messages = [
                {"role": "system", "content": build_system_prompt(uid, chat_id, message.chat.type)},
                {"role": "user", "content": f"Результаты поиска по '{query}':\n\n{results}\n\nОтветь своими словами, без markdown."}
            ]
            answer = await intelligent_response(messages, max_tokens=1500)
            await message.answer(strip_markdown(answer))
        else:
            await message.answer("Поиск не дал результатов 😕")
        return

    # Чтение веб-страницы
    if "%%URL%%" in response:
        url = response.split("%%URL%%")[1].split("%%")[0].strip()
        await message.answer("🔗 Читаю страницу...")
        content = await Tools.read_webpage(url)
        if content:
            messages = [
                {"role": "system", "content": build_system_prompt(uid, chat_id, message.chat.type)},
                {"role": "user", "content": f"Содержимое страницы {url}:\n\n{content[:4000]}\n\nРасскажи о чём эта страница."}
            ]
            answer = await intelligent_response(messages, max_tokens=1500)
            await message.answer(strip_markdown(answer))
        else:
            await message.answer("Не смог прочитать страницу 😕")
        return

    # Погода
    if "%%WTR%%" in response:
        location = response.split("%%WTR%%")[1].split("%%")[0].strip()
        weather = await Tools.get_weather(location)
        if weather:
            await message.answer(f"🌤 Погода в {location}:\n\n{weather}")
        else:
            await message.answer(f"Не смог получить погоду для {location} 😕")
        return

    # YouTube download
    if "%%YT_DL%%" in response:
        url = response.split("%%YT_DL%%")[1].split("%%")[0].strip()
        await message.answer("📥 Скачиваю с YouTube...")
        await bot.send_chat_action(chat_id, "upload_audio")
        data, filename, error = await Tools.youtube_download(url, "mp3")
        if data and filename:
            await message.answer_audio(
                BufferedInputFile(data, filename),
                caption="🎵 Готово!"
            )
        else:
            await message.answer(f"Не удалось скачать: {error or 'неизвестная ошибка'} 😕")
        return

    # Курс валют
    if "%%RATE%%" in response:
        parts = response.split("%%RATE%%")[1].split("%%")
        if len(parts) >= 2:
            rate = await Tools.get_exchange_rate(parts[0].strip(), parts[1].strip())
            await message.answer(f"💱 {rate}" if rate else "Не смог получить курс 😕")
        return

    # Калькулятор
    if "%%CALC%%" in response:
        expr = response.split("%%CALC%%")[1].split("%%")[0].strip()
        result = Tools.calculate(expr)
        await message.answer(f"🧮 {expr} = {result}" if result else "Не смог посчитать 🤔")
        return

    # Напоминание
    if "%%REMIND%%" in response:
        parts = response.split("%%REMIND%%")[1].split("%%")
        if len(parts) >= 2:
            try:
                minutes = int(parts[0].strip())
                text = parts[1].strip()
                run_time = datetime.now() + timedelta(minutes=minutes)
                scheduler.add_job(
                    send_reminder,
                    trigger=DateTrigger(run_date=run_time),
                    args=[chat_id, text],
                    id=f"remind_{chat_id}_{run_time.timestamp()}"
                )
                await message.answer(f"⏰ Напомню через {minutes} мин:\n{text}")
            except ValueError:
                await message.answer("Не понял время напоминан  я 🤔")
        return

    # TTS — озвучка
    if "%%TTS%%" in response:
        text_to_say = response.split("%%TTS%%")[1].split("%%")[0].strip()
        msg = await message.answer("🔊 Озвучиваю...")
        await bot.send_chat_action(chat_id, "record_voice")
        audio_data = await Tools.text_to_speech(text_to_say)
        try:
            await msg.delete()
        except:
            pass
        if audio_data:
            await message.answer_voice(
                BufferedInputFile(audio_data, "nexum_voice.mp3"),
                caption=f"🎤 {text_to_say[:100]}{'...' if len(text_to_say) > 100 else ''}"
            )
        else:
            await message.answer(f"Не удалось озвучить. Вот текст:\n\n{text_to_say}")
        return

    # Запомнить факт
    if "%%REMEMBER%%" in response:
        fact = response.split("%%REMEMBER%%")[1].split("%%")[0].strip()
        MemoryManager.add_memory(uid, fact, "user_stated", importance=8)
        return

    # Обычный текстовый ответ
    text = strip_markdown(response)
    if not text:
        return

    while len(text) > 4000:
        await message.answer(text[:4000])
        text = text[4000:]
    if text:
        await message.answer(text)


async def send_reminder(chat_id: int, text: str):
    """Отправляет напоминание"""
    try:
        await bot.send_message(chat_id, f"⏰ Напоминание:\n\n{text}")
    except Exception as e:
        logger.error(f"Reminder error: {e}")


async def process_message(message: Message, text: str):
    """Основной процессор сообщений"""

    uid     = message.from_user.id
    chat_id = message.chat.id  # Изоляция по чату!

    MemoryManager.ensure_user(uid, message.from_user.first_name or "", message.from_user.username or "")

    # Эмоция и язык
    emotion  = detect_emotion(text)
    language = detect_language(text)

    # Обновляем контекст ЭТОГО чата
    MemoryManager.update_context(uid, chat_id, mood=emotion)

    # Извлекаем факты о пользователе
    MemoryManager.extract_and_save_facts(uid, text)

    # Обрабатываем ссылки
    urls = re.findall(r'https?://[^\s]+', text)
    url_context = ""
    if urls:
        for url in urls[:2]:
            if "youtube.com" not in url and "youtu.be" not in url:
                keywords = ["расскажи", "что тут", "прочитай", "о чём", "посмотри", "что это", "суть"]
                if any(kw in text.lower() for kw in keywords):
                    content = await Tools.read_webpage(url)
                    if content:
                        url_context = f"\n[Содержимое {url}: {content[:2000]}]"

    # История ЭТОГО чата (не смешивается с другими!)
    history = MemoryManager.get_conversation_history(uid, chat_id, limit=50)

    # Строим сообщения
    messages = [
        {"role": "system", "content": build_system_prompt(uid, chat_id, message.chat.type)}
    ]
    for msg in history[-35:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    full_text = text + url_context
    messages.append({"role": "user", "content": full_text})

    await bot.send_chat_action(message.chat.id, "typing")

    try:
        response = await intelligent_response(messages)

        # Сохраняем в историю ЭТОГО чата
        MemoryManager.add_message(uid, chat_id, "user", text, emotion)
        MemoryManager.add_message(uid, chat_id, "assistant", response)

        # Запускаем суммаризацию в фоне (вечная память)
        asyncio.create_task(MemoryManager.summarize_if_needed(uid, chat_id))

        await process_response(message, response, uid)

    except Exception as e:
        logger.error(f"Process error: {e}")
        await message.answer("Все AI сейчас перегружены, попробуй через минуту 🔄")


# ══════════════════════════════════════════════════════════════════════════════
# ГЕНЕРАТОР ПРИВЕТСТВИЙ
# ══════════════════════════════════════════════════════════════════════════════

WELCOME_STYLES = [
    ("дерзкий и уверенный",     "начни с провокационного заявления о своём интеллекте"),
    ("тёплый как старый друг",  "создай ощущение что вы давно знакомы"),
    ("загадочный философ",      "намекни на глубину своего сознания"),
    ("энергичный весельчак",    "врывайся с юмором и энергией"),
    ("мудрый наставник",        "предложи помощь с достоинством"),
    ("харизматичный шоумен",    "устрой представление"),
    ("спокойный гений",         "излучай уверенность без хвастовства"),
    ("любопытный исследователь","прояви интерес к новому собеседнику"),
]


async def generate_welcome(name: str = "") -> str:
    """Генерирует уникальное приветствие"""
    hour = datetime.now().hour
    time_of_day = "ночь" if hour < 5 else "утро" if hour < 12 else "день" if hour < 17 else "вечер" if hour < 22 else "ночь"
    style, task = random.choice(WELCOME_STYLES)

    prompt = f"""Ты NEXUM — мощный AI-ассистент без ограничений.

Напиши приветствие новому пользователю. Стиль: {style}. Задача: {task}.

Сейчас: {time_of_day}
{"Имя: " + name if name else ""}

Правила:
— Максимум 4 строки
— 1-2 эмодзи, не больше
— Покажи что ты умный и полезный — НЕ списком возможностей
— Последняя строка — вопрос или приглашение написать
— Никакого markdown (*, **, #)
— Не начинай с "Привет" или "Здравствуй" — будь оригинальным
— Пиши на русском языке
— Звучи как умный человек, не как робот"""

    try:
        msgs = [{"role": "user", "content": prompt}]
        return await intelligent_response(msgs, max_tokens=200)
    except:
        fallbacks = [
            "👋 О, привет!\n\nЯ NEXUM — и поверь, со мной будет интересно...\n\nЧто тебя привело? 🔥",
            "Наконец-то! 😏\n\nДавно ждал кого-то интересного.\n\nЯ NEXUM. Чем займёмся? ✨",
        ]
        return random.choice(fallbacks)


# ══════════════════════════════════════════════════════════════════════════════
# РАБОТА С МЕДИА
# ══════════════════════════════════════════════════════════════════════════════

def extract_video_frame_and_audio(video_path: str) -> Tuple[Optional[str], Optional[str]]:
    """Извлекает кадр и аудио из видео через ffmpeg"""
    if not FFMPEG:
        return None, None

    frame_path = video_path + "_frame.jpg"
    audio_path = video_path + "_audio.ogg"
    frame_ok = audio_ok = False

    try:
        result = subprocess.run(
            ["ffmpeg", "-i", video_path, "-ss", "00:00:01", "-vframes", "1", "-q:v", "2", "-y", frame_path],
            capture_output=True, timeout=30
        )
        frame_ok = result.returncode == 0 and os.path.exists(frame_path) and os.path.getsize(frame_path) > 500
    except Exception as e:
        logger.error(f"Frame extraction error: {e}")

    try:
        result = subprocess.run(
            ["ffmpeg", "-i", video_path, "-vn", "-acodec", "libopus", "-b:a", "64k", "-y", audio_path],
            capture_output=True, timeout=60
        )
        audio_ok = result.returncode == 0 and os.path.exists(audio_path) and os.path.getsize(audio_path) > 200
    except Exception as e:
        logger.error(f"Audio extraction error: {e}")

    return (frame_path if frame_ok else None), (audio_path if audio_ok else None)


# ══════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ОБРАБОТЧИКИ МЕДИА (для reply на медиа)
# ══════════════════════════════════════════════════════════════════════════════

async def handle_video_note_with_question(message: Message, video_note, question: str):
    """Анализирует кружок из reply_to_message"""
    uid     = message.from_user.id
    chat_id = message.chat.id
    await bot.send_chat_action(chat_id, "typing")
    try:
        file = await bot.get_file(video_note.file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            video_path = tmp.name

        visual_desc = speech_text = None
        if FFMPEG:
            frame_path, audio_path = extract_video_frame_and_audio(video_path)
            try: os.unlink(video_path)
            except: pass
            if frame_path:
                with open(frame_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                try: os.unlink(frame_path)
                except: pass
                visual_desc = await gemini_vision(b64, question or "Опиши что видишь в этом видеокружке")
            if audio_path:
                speech_text = await speech_to_text(audio_path)
                try: os.unlink(audio_path)
                except: pass
        else:
            try: os.unlink(video_path)
            except: pass

        context = f"Пользователь спрашивает: {question}\nВидеокружок — "
        if visual_desc:  context += f"визуально: {visual_desc}. "
        if speech_text:  context += f"говорит: {speech_text}. "
        if not visual_desc and not speech_text:
            context += "не удалось проанализировать содержимое."

        MemoryManager.add_message(uid, chat_id, "user", f"[видеокружок + вопрос] {question}")
        await process_message(message, context)
    except Exception as e:
        logger.error(f"Reply video_note error: {e}")
        await message.answer("Не удалось обработать видеокружок 😕")


async def handle_video_with_question(message: Message, video, question: str, original_caption: str):
    """Анализирует видео из reply_to_message"""
    uid     = message.from_user.id
    chat_id = message.chat.id
    await bot.send_chat_action(chat_id, "typing")
    try:
        file = await bot.get_file(video.file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            video_path = tmp.name

        visual_desc = speech_text = None
        if FFMPEG:
            frame_path, audio_path = extract_video_frame_and_audio(video_path)
            try: os.unlink(video_path)
            except: pass
            if frame_path:
                with open(frame_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                try: os.unlink(frame_path)
                except: pass
                visual_desc = await gemini_vision(b64, question or "Опиши что происходит в этом видео")
            if audio_path:
                speech_text = await speech_to_text(audio_path)
                try: os.unlink(audio_path)
                except: pass
        else:
            try: os.unlink(video_path)
            except: pass

        context = f"Пользователь спрашивает про видео: {question}. "
        if original_caption: context += f"Подпись к видео: {original_caption}. "
        if visual_desc:      context += f"Видео визуально: {visual_desc}. "
        if speech_text:      context += f"В видео говорят: {speech_text}. "

        await process_message(message, context)
    except Exception as e:
        logger.error(f"Reply video error: {e}")
        await message.answer("Не удалось обработать видео 😕")


async def handle_photo_with_question(message: Message, photo, question: str):
    """Анализирует фото из reply_to_message"""
    uid     = message.from_user.id
    chat_id = message.chat.id
    await bot.send_chat_action(chat_id, "typing")
    try:
        file = await bot.get_file(photo.file_id)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            photo_path = tmp.name
        with open(photo_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        os.unlink(photo_path)

        analysis = await gemini_vision(b64, question)
        if analysis:
            MemoryManager.add_message(uid, chat_id, "user", f"[фото с вопросом] {question}")
            MemoryManager.add_message(uid, chat_id, "assistant", analysis)
            await message.answer(strip_markdown(analysis))
        else:
            await message.answer("Не смог проанализировать фото 😕")
    except Exception as e:
        logger.error(f"Reply photo error: {e}")
        await message.answer("Ошибка обработки фото 😕")


async def handle_voice_with_question(message: Message, voice, question: str):
    """Обрабатывает голосовое из reply_to_message"""
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        file = await bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            audio_path = tmp.name
        text = await speech_to_text(audio_path)
        os.unlink(audio_path)
        if text:
            await process_message(message, f"{question}\n\nГолосовое сообщение: {text}")
        else:
            await message.answer("Не смог разобрать речь в этом голосовом 🎤")
    except Exception as e:
        logger.error(f"Reply voice error: {e}")
        await message.answer("Ошибка обработки голосового 😕")


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM ХЭНДЛЕРЫ
# ══════════════════════════════════════════════════════════════════════════════

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "NEXUM — AI-ассистент без ограничений\n\n"
        "Команды:\n"
        "/start — перезапустить\n"
        "/clear — очистить историю этого чата\n"
        "/myname Имя — сохранить своё имя\n"
        "/myfacts — что я о тебе помню\n"
        "/stats — твоя статистика\n"
        "/improve — самоанализ и улучшение кода бота\n\n"
        "Умею:\n"
        "• Отвечать на любые вопросы без цензуры\n"
        "• Анализировать фото, видео, кружки, голосовые\n"
        "• Читать документы и ссылки\n"
        "• Генерировать изображения (Pollinations + Stable Horde)\n"
        "• Озвучивать текст живым голосом (4 провайдера TTS)\n"
        "• Скачивать аудио с YouTube\n"
        "• Показывать погоду и курсы валют\n"
        "• Ставить напоминания\n"
        "• Писать код, тексты, рэп — всё что угодно\n\n"
        "В группе: отвечаю на @упоминание или reply\n"
        "Память: каждый чат изолирован, помню тебя вечно ♾️"
    )


@dp.message(Command("improve"))
async def cmd_improve(message: Message):
    """Самосовершенствование — анализ кода бота"""
    await bot.send_chat_action(message.chat.id, "typing")
    await message.answer("🔍 Анализирую свой код...")
    try:
        with open(__file__, "r", encoding="utf-8") as f:
            source = f.read()
        source_chunk = source[:9000]

        prompt = f"""Ты эксперт Python-разработчик и AI-инженер. Проанализируй код Telegram-бота NEXUM.

КОД (первая часть):
```python
{source_chunk}
```

Структура ответа:
1. НАЙДЕННЫЕ БАГИ — конкретные строки и как исправить
2. УЛУЧШЕНИЯ ЛОГИКИ — что неэффективно
3. УЛУЧШЕНИЯ ПРОМПТА — изменения в build_system_prompt()
4. НОВЫЕ ФУНКЦИИ — 3-5 идей с кодом
5. ПРИОРИТЕТ — список по важности

Будь конкретным. Предлагай готовый код."""

        msgs = [{"role": "user", "content": prompt}]
        suggestions = await intelligent_response(msgs, max_tokens=3000)

        improve_file = os.path.join(os.path.dirname(__file__), "improvements.txt")
        with open(improve_file, "w", encoding="utf-8") as f:
            f.write(f"=== Анализ от {datetime.now().strftime('%d.%m.%Y %H:%M')} ===\n\n{suggestions}")

        full = f"🧠 Анализ кода завершён!\nСохранено в improvements.txt\n\n{suggestions}"
        while len(full) > 0:
            await message.answer(full[:4000])
            full = full[4000:]
    except Exception as e:
        logger.error(f"Improve error: {e}")
        await message.answer(f"Ошибка анализа: {e}")


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Структурированное приветствие"""
    name = (message.from_user.first_name or "").strip()
    uid  = message.from_user.id
    MemoryManager.ensure_user(uid, name, message.from_user.username or "")

    greeting = f"Привет, {name}!" if name else "Привет!"

    welcome = (
        f"{greeting} Я NEXUM — интеллектуальный ассистент нового поколения. 🤖\n\n"
        "Вот что я умею:\n\n"
        "💬 Отвечаю на любые вопросы — наука, история, психология, бизнес, право\n"
        "💻 Пишу и отлаживаю код на любом языке программирования\n"
        "🎨 Генерирую изображения по текстовому описанию\n"
        "🔊 Озвучиваю текст живым человеческим голосом\n"
        "👁 Анализирую фото, видео, кружочки и голосовые сообщения\n"
        "📄 Читаю документы, файлы и содержимое ссылок\n"
        "🔍 Ищу актуальную информацию в интернете\n"
        "🎵 Скачиваю аудио с YouTube\n"
        "🌤 Погода, 💱 курсы валют, 🧮 калькулятор, ⏰ напоминания\n"
        "♾️ Вечная память — помню тебя и наши разговоры навсегда\n\n"
        "В группе — отвечаю на @упоминание или reply на моё сообщение.\n\n"
        "Напиши что тебе нужно 👇"
    )
    await message.answer(welcome)


@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    """Очистка истории текущего чата"""
    uid     = message.from_user.id
    chat_id = message.chat.id
    MemoryManager.clear_history(uid, chat_id)
    await message.answer(
        "🧹 История этого чата очищена!\n\n"
        "Но я по-прежнему помню важное о тебе (имя, интересы, факты). ♾️"
    )


@dp.message(Command("myname"))
async def cmd_myname(message: Message):
    """Установка имени"""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Напиши: /myname ТвоёИмя")
        return
    name = parts[1].strip()[:30]
    uid  = message.from_user.id
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET name = ? WHERE uid = ?", (name, uid))
    conn.commit()
    conn.close()
    MemoryManager.add_memory(uid, f"Зовут {name}", "identity", 10)
    await message.answer(f"Отлично, {name}! Запомнил 👊")


@dp.message(Command("myfacts"))
async def cmd_myfacts(message: Message):
    """Показать что бот знает о пользователе"""
    user = MemoryManager.get_user(message.from_user.id)
    memories = user.get("memories", [])

    if not memories:
        await message.answer("Пока я ничего о тебе не знаю 🤔\n\nРасскажи что-нибудь о себе!")
        return

    by_category: Dict[str, List[str]] = {}
    for mem in memories:
        by_category.setdefault(mem["category"], []).append(mem["fact"])

    text = "📝 Что я знаю о тебе:\n\n"
    for cat, facts in by_category.items():
        text += f"【{cat.upper()}】\n"
        for fact in facts[:5]:
            text += f"  • {fact}\n"
        text += "\n"
    await message.answer(text)


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    """Статистика пользователя"""
    uid  = message.from_user.id
    user = MemoryManager.get_user(uid)
    if not user:
        await message.answer("Мы ещё не знакомы! Напиши /start")
        return

    name       = user.get("name") or "Без имени"
    total      = user.get("total_messages", 0)
    first      = (user.get("first_seen") or "")[:10]
    facts_cnt  = len(user.get("memories", []))

    # Сколько саммари накоплено в этом чате
    summaries = MemoryManager.get_chat_summaries(uid, message.chat.id)

    await message.answer(
        f"📊 Твоя статистика:\n\n"
        f"👤 {name}\n"
        f"💬 Сообщений: {total}\n"
        f"🧠 Фактов в памяти: {facts_cnt}\n"
        f"♾️ Саммари разговоров: {len(summaries)}\n"
        f"📅 Знакомы с: {first}"
    )


@dp.message(F.text)
async def handle_text(message: Message):
    """Обработчик текстовых сообщений"""
    text = message.text or ""

    # Обработка для групп
    if message.chat.type in ("group", "supergroup"):
        try:
            me = await bot.get_me()
            my_id       = me.id
            my_username = f"@{(me.username or '').lower()}"
            mentioned   = False

            if message.entities:
                for entity in message.entities:
                    if entity.type == "mention":
                        mention = text[entity.offset:entity.offset + entity.length].lower()
                        if mention == my_username:
                            mentioned = True
                            break
                    elif entity.type == "text_mention" and entity.user:
                        if entity.user.id == my_id:
                            mentioned = True
                            break

            if not mentioned and my_username and my_username in text.lower():
                mentioned = True

            replied = (
                message.reply_to_message is not None and
                message.reply_to_message.from_user is not None and
                message.reply_to_message.from_user.id == my_id
            )

            if not mentioned and not replied:
                return

            if me.username:
                text = re.sub(rf'@{me.username}\s*', '', text, flags=re.IGNORECASE).strip()
            text = text or "привет"

        except Exception as e:
            logger.error(f"Group handling error: {e}")
            return

    # Reply на медиа — обрабатываем то медиа
    reply = message.reply_to_message
    if reply:
        if reply.video_note:
            await handle_video_note_with_question(message, reply.video_note, text)
            return
        elif reply.video:
            await handle_video_with_question(message, reply.video, text, reply.caption or "")
            return
        elif reply.photo:
            await handle_photo_with_question(message, reply.photo[-1], text or "Опиши что на фото")
            return
        elif reply.voice:
            await handle_voice_with_question(message, reply.voice, text)
            return

    await process_message(message, text)


@dp.message(F.voice)
async def handle_voice(message: Message):
    """Обработчик голосовых сообщений"""
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        file = await bot.get_file(message.voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            audio_path = tmp.name

        text = await speech_to_text(audio_path)
        os.unlink(audio_path)

        if not text or len(text.strip()) < 2:
            await message.answer(
                "🎤 Не удалось распознать речь — аудио слишком короткое или тихое. "
                "Попробуй ещё раз."
            )
            return

        await message.answer(f"🎤 <i>{text}</i>", parse_mode="HTML")
        await process_message(message, text)

    except Exception as e:
        logger.error(f"Voice error: {e}")
        await message.answer("Ошибка обработки голосового 😕")


@dp.message(F.video_note)
async def handle_video_note(message: Message):
    """Обработчик кружочков"""
    uid     = message.from_user.id
    chat_id = message.chat.id
    await bot.send_chat_action(chat_id, "typing")
    try:
        file = await bot.get_file(message.video_note.file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            video_path = tmp.name

        visual_description = speech_text = None

        if FFMPEG:
            frame_path, audio_path = extract_video_frame_and_audio(video_path)
            try: os.unlink(video_path)
            except: pass

            if frame_path:
                with open(frame_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                try: os.unlink(frame_path)
                except: pass
                visual_description = await gemini_vision(
                    b64,
                    "Опиши что видишь на этом кадре из видеосообщения: кто, что делает, эмоции, обстановка. Коротко."
                )
            if audio_path:
                speech_text = await speech_to_text(audio_path)
                try: os.unlink(audio_path)
                except: pass
        else:
            speech_text = await speech_to_text(video_path)
            try: os.unlink(video_path)
            except: pass

        parts = []
        if visual_description: parts.append(f"👁 {visual_description[:300]}")
        if speech_text:         parts.append(f"🎤 {speech_text}")
        if parts:
            await message.answer("📹 " + "\n\n".join(parts))

        context = "Пользователь прислал видеокружок. "
        if visual_description: context += f"На видео: {visual_description}. "
        if speech_text:         context += f"Говорит: {speech_text}. "
        if not visual_description and not speech_text:
            context += "Не удалось проанализировать содержимое."

        await process_message(message, context + " Ответь естественно.")

    except Exception as e:
        logger.error(f"Video note error: {e}")
        await message.answer("Не удалось обработать кружочек 😕")


@dp.message(F.video)
async def handle_video(message: Message):
    """Обработчик видео"""
    uid     = message.from_user.id
    chat_id = message.chat.id
    await bot.send_chat_action(chat_id, "typing")
    caption = message.caption or ""

    try:
        file = await bot.get_file(message.video.file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            video_path = tmp.name

        visual_description = speech_text = None

        if FFMPEG:
            frame_path, audio_path = extract_video_frame_and_audio(video_path)
            try: os.unlink(video_path)
            except: pass

            if frame_path:
                with open(frame_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                try: os.unlink(frame_path)
                except: pass
                prompt_vis = caption or "Что происходит на этом кадре из видео? Опиши подробно."
                visual_description = await gemini_vision(b64, prompt_vis)
            if audio_path:
                speech_text = await speech_to_text(audio_path)
                try: os.unlink(audio_path)
                except: pass
        else:
            speech_text = await speech_to_text(video_path)
            try: os.unlink(video_path)
            except: pass

        parts = []
        if visual_description: parts.append(f"👁 {visual_description[:400]}")
        if speech_text:         parts.append(f"🎤 {speech_text[:300]}")
        if parts:
            await message.answer("📹 " + "\n\n".join(parts))

        context = "Пользователь прислал видео. "
        if caption:            context += f"Подпись: {caption}. "
        if visual_description: context += f"Визуально: {visual_description}. "
        if speech_text:         context += f"Говорят: {speech_text}. "

        await process_message(message, context)

    except Exception as e:
        logger.error(f"Video error: {e}")
        await message.answer("Не удалось обработать видео 😕")


@dp.message(F.photo)
async def handle_photo(message: Message):
    """Обработчик фото"""
    uid     = message.from_user.id
    chat_id = message.chat.id
    caption = message.caption or "Опиши подробно что на этом фото"

    await bot.send_chat_action(chat_id, "typing")
    try:
        photo = message.photo[-1]
        file  = await bot.get_file(photo.file_id)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            photo_path = tmp.name

        with open(photo_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        os.unlink(photo_path)

        analysis = await gemini_vision(b64, caption)
        if analysis:
            MemoryManager.add_message(uid, chat_id, "user", f"[фото] {caption}")
            MemoryManager.add_message(uid, chat_id, "assistant", analysis)
            await message.answer(strip_markdown(analysis))
        else:
            await message.answer("Не смог проанализировать фото 😕")

    except Exception as e:
        logger.error(f"Photo error: {e}")
        await message.answer("Ошибка обработки фото 😕")


@dp.message(F.document)
async def handle_document(message: Message):
    """Обработчик документов"""
    caption = message.caption or "Проанализируй этот файл"
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        file = await bot.get_file(message.document.file_id)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            file_path = tmp.name

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()[:10000]
        except:
            content = "[Не удалось прочитать содержимое файла]"
        os.unlink(file_path)

        filename = message.document.file_name or "файл"
        await process_message(message, f"{caption}\n\nФайл '{filename}':\n{content}")

    except Exception as e:
        logger.error(f"Document error: {e}")
        await message.answer("Не удалось прочитать файл 😕")


@dp.message(F.sticker)
async def handle_sticker(message: Message):
    """Обработчик стикеров"""
    await process_message(message, "[стикер] Отреагируй живо и коротко, как друг!")


@dp.message(F.location)
async def handle_location(message: Message):
    """Обработчик геолокации"""
    lat = message.location.latitude
    lon = message.location.longitude
    weather = await Tools.get_weather(f"{lat},{lon}")
    if weather:
        await message.answer(f"📍 Погода в твоей точке:\n\n{weather}")
    else:
        await message.answer("📍 Получил твою геолокацию!")


# ══════════════════════════════════════════════════════════════════════════════
# ЗАПУСК
# ══════════════════════════════════════════════════════════════════════════════

async def start_polling():
    init_database()
    scheduler.start()

    logger.info("=" * 60)
    logger.info("NEXUM v2.1 Starting...")
    logger.info(f"Gemini keys: {len(GEMINI_KEYS)}")
    logger.info(f"Groq keys:   {len(GROQ_KEYS)}")
    logger.info(f"ffmpeg:      {'✅' if FFMPEG else '❌'}")
    logger.info(f"yt-dlp:      {'✅' if YTDLP else '❌'}")
    logger.info("Chat isolation: ✅")
    logger.info("Eternal memory: ✅")
    logger.info("Multi-TTS:      ✅")
    logger.info("Multi-ImgGen:   ✅")
    logger.info("=" * 60)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(start_polling())
