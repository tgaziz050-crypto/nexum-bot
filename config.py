import os

BOT_TOKEN = os.getenv("BOT_TOKEN")

GEMINI_KEYS = [
    os.getenv("GEMINI_1"),
    os.getenv("GEMINI_2"),
    os.getenv("GEMINI_3"),
]

GROQ_KEYS = [
    os.getenv("GROQ_1"),
    os.getenv("GROQ_2")
]
