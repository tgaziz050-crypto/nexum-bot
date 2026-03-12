# NEXUM — Autonomous AI Agent Bot

> Telegram AI agent with voice, mini apps, finance, tasks, notes, habits, PC control

---

## Quick Deploy (Railway)

1. Fork: `https://github.com/thenexumai/nexum-bot`
2. Connect to Railway
3. Add Variables (see below)
4. Deploy

---

## Environment Variables

```
BOT_TOKEN=        # BotFather token
ADMIN_IDS=        # Your Telegram user ID
WEBAPP_URL=       # https://your-app.up.railway.app

# AI Keys (add as many as you have)
CB1= CB2= CB3= CB4= CB5= CB6= CB7=   # Cerebras
GR1= GR2= GR3= GR4= GR5= GR6= GR7=  # Groq (also used for voice STT)
G1=  G2=  G3=  G4=  G5=  G6=  G7=   # Gemini
GK1= GK2= GK3=                        # Grok
SN1= SN2= SN3= SN4= SN5=             # SambaNova
TO1= TO2= TO3= TO4= TO5= TO6= TO7=   # Together
OR1= OR2= OR3= OR4= OR5= OR6= OR7=   # OpenRouter
DS1= DS2= DS3= DS4= DS5= DS6=        # DeepSeek
CL1=                                  # Claude

# Search
SERPER_KEY1= SERPER_KEY2= SERPER_KEY3=
```

---

## Features

- 🧠 Persistent memory across sessions
- 🌐 Real-time web search
- 🎙 Voice messages & video notes (Groq Whisper + Gemini fallback)
- 👁 Photo & image analysis
- 💰 Finance tracker
- 📝 Notes
- ✅ Tasks
- 🎯 Habits tracker
- ⏰ Reminders & alarms
- 💻 PC Agent (remote computer control)
- 🧰 Self-developing tools
- 📱 Mini Apps (dark/light theme)

---

## Commands

```
/start    — Welcome
/help     — All commands
/apps     — Open mini apps
/status   — System status
/finance  — Finance dashboard
/tasks    — Tasks
/notes    — Notes
/habits   — Habits
/remind   — Set reminder
/search   — Web search
/tools    — Dynamic tools list
/newtool  — Create new tool
/pc_connect — Connect PC
/new      — New conversation
/memory   — What I know about you
/diagnostic — (admin) Check keys
```

---

## Architecture

```
User → Telegram → Router → Planner → Executor → Tools
                                              ↓
                                    PC Agent (WebSocket)
                                    Finance / Notes / Tasks / Habits
                                    Web Search (Serper)
                                    STT (Groq Whisper → Gemini)
                                    TTS (voice replies)
                                    Dynamic Tool Registry
```

---

## Voice / STT

Voice messages and video notes are transcribed via:
1. **Groq Whisper** (`whisper-large-v3-turbo`) — uses GR1..GR7 keys
2. **Gemini** fallback — uses G1..G7 keys
- Auto-detects language (Russian, Uzbek, English, etc.)

---

## Mini Apps

Served at `WEBAPP_URL`. Pages:
- `/hub` — App launcher
- `/` — Finance dashboard
- `/notes` — Notes
- `/tasks` — Tasks
- `/habits` — Habits

Dark/light theme follows Telegram automatically.
