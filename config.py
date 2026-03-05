import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Gemini keys
GEMINI_KEYS = [
    os.getenv("GEMINI_1"),
    os.getenv("GEMINI_2"),
    os.getenv("GEMINI_3"),
    os.getenv("GEMINI_4"),
    os.getenv("GEMINI_5"),
    os.getenv("GEMINI_6"),
]

# Groq keys
GROQ_KEYS = [
    os.getenv("GROQ_1"),
    os.getenv("GROQ_2"),
    os.getenv("GROQ_3"),
    os.getenv("GROQ_4"),
    os.getenv("GROQ_5"),
    os.getenv("GROQ_6"),
]

OPENAI_KEY = os.getenv("OPENAI_KEY")

ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")
