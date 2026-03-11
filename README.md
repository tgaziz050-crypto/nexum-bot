# NEXUM v5 — Autonomous AI Agent Platform

> Transform your Telegram into a powerful AI agent that plans, executes, and automates.

---

## 🏗 Architecture

```
User
 ↓
Telegram Bot
 ↓
Gateway (grammy)
 ↓
Message Router (intent detection)
 ↓
Agent Core
 ↓
┌─────────────┬──────────────┐
│   Planner   │   Executor   │
│  (plans)    │  (runs tools)│
└─────────────┴──────────────┘
 ↓
Tools System
┌────────┬────────────┬────────┬──────────┐
│ Search │ Web/Browser│ Notes  │ Finance  │
│  STT   │    TTS     │ Tasks  │ Habits   │
│ Vision │  Reminder  │ Alarm  │ Memory   │
└────────┴────────────┴────────┴──────────┘
 ↓
PC Agent (WebSocket — secure linking)
```

---

## ✨ What's New in v5

### 🔐 Secure PC Agent Linking
- Agent generates a **6-char code** on startup
- User sends `/link ABCDEF` to the bot
- Server pairs `uid ↔ device_id` — **bot token never exposed**

### 🗺 Task Planner
- Detects complex multi-step requests automatically
- Breaks them into concrete steps
- Executes using available tools
- Asks confirmation for sensitive actions

### 🧠 Improved Memory
- Fast regex extraction for immediate facts
- Deep AI extraction for complex context
- Long-term memory bank with importance ranking

### 📱 5 Mini-Apps
- **Hub** — launcher for all apps
- **Finance** — CBU rates, budgets, transactions
- **Notes** — color-coded, pinnable, searchable
- **Tasks** — projects, priorities, completion
- **Habits** — daily tracker with streaks

---

## 🚀 Deploy on Railway

### Required Variables
```env
BOT_TOKEN=your_telegram_bot_token
ADMIN_IDS=your_telegram_user_id
WEBAPP_URL=https://your-project.up.railway.app
```

### AI Keys (add at least one free option)
```env
CB1=cerebras_key     # free, very fast
GR1=groq_key         # free
G1=gemini_key        # free tier
GK1=grok_key
DS1=deepseek_key
OR1=openrouter_key   # free models available
CL1=claude_key
```

### Optional: Web Search
```env
SERPER_KEY1=serper.dev key
BRAVE_KEY1=brave search key
```

---

## 💻 PC Agent Setup

```bash
# 1. Download nexum_agent.py from repo

# 2. Install deps
pip install websockets psutil pillow

# 3. Run (point to your Railway URL)
python nexum_agent.py wss://your-project.up.railway.app/ws

# 4. Agent shows code: ABCDEF
# 5. Send to bot: /link ABCDEF
```

Agent capabilities:
- `/screenshot` — capture screen
- `/run command` — execute terminal command
- `/sysinfo` — system information
- Browser, filesystem, task automation

---

## 📱 Bot Commands

```
/start      — Welcome
/apps       — All mini-apps
/help       — Full command list
/new        — New conversation
/memory     — View memory
/status     — System status
/brief      — Day digest

/finance    — Finance overview
/notes      — Notes app
/tasks      — Tasks
/habits     — Habit tracker
/remind     — Set reminder
/search     — Web search

/link CODE  — Link PC agent
/pc         — PC agent status
/pc_connect — Setup guide
/screenshot — PC screenshot
/run CMD    — Run on PC
/sysinfo    — PC system info
```

---

## 🛠 Tech Stack

- **Runtime**: Node.js 20 + TypeScript
- **Bot**: Grammy v1.30
- **DB**: SQLite (better-sqlite3)
- **Voice**: Groq Whisper STT + Edge-TTS (50+ languages)
- **Vision**: Gemini / OpenRouter / Claude
- **PC Agent**: Python + WebSocket
- **Deploy**: Railway / Docker

---

## 📁 Project Structure

```
nexum-v5/
├── src/
│   ├── core/          # Config, DB, Logger, Heartbeat
│   ├── agent/         # AI Engine, Memory, Planner, Executor, Router, PC Agent Server
│   ├── telegram/      # Bot, Handler, Commands, Send, Format, Reactions
│   ├── tools/         # STT, TTS, Search, Vision, Notes, Tasks, Habits, Finance, Reminder, Alarm
│   ├── apps/          # Mini-app HTML + Express server
│   ├── scheduler/     # Cron jobs, daily digest
│   ├── admin/         # Admin dashboard
│   └── index.ts       # Entry point
├── nexum_agent.py     # PC Agent (Python)
└── README.md
```

---

<div align="center">
NEXUM v5 · <a href="https://t.me/ainexum_bot">@ainexum_bot</a>
</div>
