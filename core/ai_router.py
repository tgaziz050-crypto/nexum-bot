import aiohttp
import asyncio
from config import GEMINI_KEYS, GROQ_KEYS

_gemini_index = 0
_groq_index = 0


def get_gemini_key():
    global _gemini_index
    key = GEMINI_KEYS[_gemini_index % len(GEMINI_KEYS)]
    _gemini_index += 1
    return key


def get_groq_key():
    global _groq_index
    key = GROQ_KEYS[_groq_index % len(GROQ_KEYS)]
    _groq_index += 1
    return key


async def gemini_chat(messages):

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"

    body = {
        "contents": [
            {"role": "user", "parts": [{"text": m["content"]}]}
            for m in messages
        ]
    }

    key = get_gemini_key()

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{url}?key={key}",
            json=body,
        ) as r:

            if r.status != 200:
                return None

            data = await r.json()

            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except:
                return None


async def groq_chat(messages):

    key = get_groq_key()

    async with aiohttp.ClientSession() as session:

        async with session.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": messages
            }
        ) as r:

            if r.status != 200:
                return None

            data = await r.json()

            return data["choices"][0]["message"]["content"]


async def ai_generate(messages):

    # 1 пробуем Gemini
    result = await gemini_chat(messages)

    if result:
        return result

    # fallback Groq
    result = await groq_chat(messages)

    if result:
        return result

    return "AI сейчас перегружен."
