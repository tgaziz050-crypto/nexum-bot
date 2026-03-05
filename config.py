import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

GEMINI_KEYS = [k for k in [
    os.getenv("GEMINI_1"),
    os.getenv("GEMINI_2"),
] if k]

GROQ_KEYS = [k for k in [
    os.getenv("GROQ_1"),
    os.getenv("GROQ_2"),
] if k]

OPENAI_KEY = os.getenv("OPENAI_KEY")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

SAFETY_MODE = os.getenv("SAFETY_MODE", "on").lower() == "on"
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID")) if os.getenv("ADMIN_USER_ID") else None
