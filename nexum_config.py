"""
NEXUM — Secure Configuration
All keys loaded ONLY from environment variables.
Never hardcode secrets in source code!
"""
import os, sys, logging

log = logging.getLogger("NEXUM.config")

def _env(key: str, required=False, default=None):
    val = os.getenv(key, default)
    if required and not val:
        log.critical(f"MISSING REQUIRED ENV VAR: {key}")
        sys.exit(1)
    return val

def _env_list(*keys, sep=","):
    """Load multiple env vars or a comma-separated single var, return non-empty list."""
    vals = []
    for k in keys:
        v = os.getenv(k)
        if v:
            vals.extend([x.strip() for x in v.split(sep) if x.strip()])
    return vals

# ── Telegram ──────────────────────────────────────────────
BOT_TOKEN = _env("BOT_TOKEN", required=True)

# ── AI Providers ──────────────────────────────────────────
GEMINI_KEYS  = _env_list("G1","G2","G3","G4","G5","G6","G7","G8","GEMINI_KEYS")
GROQ_KEYS    = _env_list("GR1","GR2","GR3","GR4","GR5","GR6","GROQ_KEYS")
DS_KEYS      = _env_list("DS1","DS2","DS3","DS4","DS5","DS6","DEEPSEEK_KEYS")
CLAUDE_KEYS  = _env_list("CL1","CL2","CL3","CLAUDE_KEYS")
GROK_KEYS    = _env_list("GK1","GK2","GK3","GROK_KEYS")
HF_TOKEN     = _env("HF_TOKEN")      # HuggingFace (free tier ok without)
REPLICATE_KEY= _env("REPLICATE_KEY") # optional
AUDD_KEY     = _env("AUDD_KEY")      # music recognition

# ── Notion ────────────────────────────────────────────────
NOTION_TOKEN = _env("NOTION_TOKEN")
NOTION_DEFAULT_PAGE = _env("NOTION_DEFAULT_PAGE")  # parent page ID for new pages

# ── Email ─────────────────────────────────────────────────
# Per-user email is stored in DB. These are optional global fallback.
SMTP_HOST = _env("SMTP_HOST")
SMTP_PORT = int(_env("SMTP_PORT", default="587"))
SMTP_USER = _env("SMTP_USER")
SMTP_PASS = _env("SMTP_PASS")

def check_keys():
    providers = {
        "Gemini": len(GEMINI_KEYS),
        "Groq": len(GROQ_KEYS),
        "DeepSeek": len(DS_KEYS),
        "Claude": len(CLAUDE_KEYS),
        "Grok": len(GROK_KEYS),
    }
    active = {k: v for k, v in providers.items() if v > 0}
    if not active:
        log.warning("No AI provider keys found. AI features will be disabled. Add G1 (Gemini) or GR1 (Groq) to enable.")
    else:
        log.info(f"AI providers: {', '.join(f'{k}({v})' for k,v in active.items())}")
    if NOTION_TOKEN:
        log.info("Notion: connected")
    if HF_TOKEN:
        log.info("HuggingFace: authenticated")
    else:
        log.info("HuggingFace: anonymous (limited)")
