import aiohttp, asyncio, json, os, logging
from typing import List, Dict, Optional
from config import GEMINI_KEYS, GROQ_KEYS, OPENAI_KEY, SAFETY_MODE

logger = logging.getLogger(__name__)

# Простая ротация ключей
_gemini_idx = 0
_groq_idx = 0

def _rotate(lst, idx):
    if not lst: return None, idx
    idx = (idx + 1) % len(lst)
    return lst[idx], idx

async def _call_gemini(messages:List[Dict], key:str, model="gemini-2.0-flash"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    contents = []
    for m in messages:
        role = "model" if m["role"]=="assistant" else "user"
        contents.append({"role": role, "parts":[{"text": m["content"]}]})
    body = {"contents": contents}
    async with aiohttp.ClientSession() as s:
        try:
            r = await s.post(url, json=body, timeout=aiohttp.ClientTimeout(total=40))
            if r.status==200:
                data = await r.json()
                return data.get("candidates",[{}])[0].get("content",{}).get("parts",[{}])[0].get("text")
            else:
                logger.warning("Gemini returned %s", r.status)
                return None
        except Exception as e:
            logger.error("Gemini error %s", e)
            return None

async def _call_groq(messages:List[Dict], key:str):
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {"model":"llama-3.3-70b-versatile","messages":messages}
    headers = {"Authorization": f"Bearer {key}", "Content-Type":"application/json"}
    async with aiohttp.ClientSession() as s:
        try:
            r = await s.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=40))
            if r.status==200:
                data = await r.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error("Groq error %s", e)
    return None

async def _call_openai(messages:List[Dict], key:str):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type":"application/json"}
    payload = {"model":"gpt-4o-mini", "messages": messages, "max_tokens": 1500}
    async with aiohttp.ClientSession() as s:
        try:
            r = await s.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=40))
            if r.status==200:
                data = await r.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error("OpenAI error %s", e)
    return None

async def generate(messages:List[Dict], max_tokens:int=1500) -> str:
    """Try providers in order, rotate keys on error. Returns string or raises."""
    global _gemini_idx, _groq_idx
    # Respect safety mode: if ON, add a short safety system instruction
    if SAFETY_MODE:
        messages = [{"role":"system","content":"Be safe: do not produce illegal instructions or doxxing."}] + messages

    # 1) try Gemini keys
    for _ in range(len(GEMINI_KEYS) or 1):
        if GEMINI_KEYS:
            key = GEMINI_KEYS[_gemini_idx % len(GEMINI_KEYS)]
            res = await _call_gemini(messages, key)
            _gemini_idx = (_gemini_idx + 1) % (len(GEMINI_KEYS) or 1)
            if res: return res

    # 2) try OpenAI if key set
    if OPENAI_KEY:
        res = await _call_openai(messages, OPENAI_KEY)
        if res: return res

    # 3) try Groq
    for _ in range(len(GROQ_KEYS) or 1):
        if GROQ_KEYS:
            key = GROQ_KEYS[_groq_idx % len(GROQ_KEYS)]
            res = await _call_groq(messages, key)
            _groq_idx = (_groq_idx + 1) % (len(GROQ_KEYS) or 1)
            if res: return res

    # fallback
    return "Извиняюсь, сейчас все провайдеры недоступны — попробуй позже."
