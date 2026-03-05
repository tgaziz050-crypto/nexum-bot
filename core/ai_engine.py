import aiohttp
from config import GEMINI_KEYS, GROQ_KEYS


class AIEngine:

    gemini_index = 0
    groq_index = 0

    @staticmethod
    def next_gemini():

        key = GEMINI_KEYS[AIEngine.gemini_index]

        AIEngine.gemini_index += 1

        if AIEngine.gemini_index >= len(GEMINI_KEYS):
            AIEngine.gemini_index = 0

        return key

    @staticmethod
    def next_groq():

        key = GROQ_KEYS[AIEngine.groq_index]

        AIEngine.groq_index += 1

        if AIEngine.groq_index >= len(GROQ_KEYS):
            AIEngine.groq_index = 0

        return key

    @staticmethod
    async def gemini(messages):

        for _ in range(len(GEMINI_KEYS)):

            key = AIEngine.next_gemini()

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"

            body = {
                "contents": [
                    {"parts": [{"text": m["content"]}]}
                    for m in messages
                ]
            }

            try:

                async with aiohttp.ClientSession() as session:

                    async with session.post(url, json=body) as r:

                        if r.status == 200:

                            data = await r.json()

                            return data["candidates"][0]["content"]["parts"][0]["text"]

            except:
                continue

        return None

    @staticmethod
    async def groq(messages):

        for _ in range(len(GROQ_KEYS)):

            key = AIEngine.next_groq()

            try:

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

                        if r.status == 200:

                            data = await r.json()

                            return data["choices"][0]["message"]["content"]

            except:
                continue

        return None

    @staticmethod
    async def generate(messages):

        r = await AIEngine.gemini(messages)

        if r:
            return r

        r = await AIEngine.groq(messages)

        if r:
            return r

        return "AI перегружен."
