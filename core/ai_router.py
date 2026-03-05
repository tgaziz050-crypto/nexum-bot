import aiohttp
from config import GEMINI_KEYS, GROQ_KEYS

_gemini_index = 0
_groq_index = 0


def next_gemini():
    global _gemini_index
    key = GEMINI_KEYS[_gemini_index % len(GEMINI_KEYS)]
    _gemini_index += 1
    return key


def next_groq():
    global _groq_index
    key = GROQ_KEYS[_groq_index % len(GROQ_KEYS)]
    _groq_index += 1
    return key


async def gemini(messages, model="gemini-2.0-flash-exp"):

    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": m["content"]}]
            }
            for m in messages
        ]
    }

    key = next_gemini()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body) as r:

            if r.status != 200:
                return None

            data = await r.json()

            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except:
                return None


async def groq(messages):

    key = next_groq()

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


async def generate(messages):

    # 1️⃣ Gemini
    result = await gemini(messages)

    if result:
        return result

    # 2️⃣ fallback Groq
    result = await groq(messages)

    if result:
        return result

    return "AI сейчас перегружен."
