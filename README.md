<div align="center">

# ⚡ NEXUM

<img src="https://raw.githubusercontent.com/thenexumai/nexum-bot/main/assets/logo.png" alt="NEXUM Logo" width="160" height="160" />

### Autonomous AI Agent Platform for Telegram

*Plan · Execute · Automate · Remember*

[![Railway](https://img.shields.io/badge/Deploy-Railway-blueviolet?style=for-the-badge&logo=railway)](https://railway.app)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-blue?style=for-the-badge&logo=typescript)](https://typescriptlang.org)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram)](https://t.me/ainexum_bot)

</div>

---

## 🧠 Architecture

```
User → Telegram → Gateway → Message Router → Agent Core
                                                  ↓
                                            Task Planner
                                                  ↓
                                          Action Executor
                                                  ↓
                                          Tools & PC Agent
```

## ✨ Features

| Category | Capabilities |
|----------|-------------|
| 🤖 **AI Agent** | Intent detection, task planning, multi-step execution |
| 🎙 **Voice** | STT (Whisper) + TTS (Edge-TTS), 50+ languages |
| 👁 **Vision** | Photo analysis via Gemini |
| 💻 **PC Agent** | Mouse, keyboard, terminal, screenshots, file ops |
| 💰 **Finance** | Transactions, budgets, CBU exchange rates |
| 📝 **Notes** | Full CRUD with search and pinning |
| ✅ **Tasks** | Projects, priorities, due dates |
| 🎯 **Habits** | Daily tracking with streaks |
| 🔔 **Reminders** | Natural language parsing |
| 🧠 **Memory** | Persistent user facts across sessions |

## 🚀 Quick Start

### 1. Clone & Configure

```bash
git clone https://github.com/thenexumai/nexum-bot.git
cd nexum-bot
cp .env.example .env
```

### 2. Set Environment Variables

```env
BOT_TOKEN=your_telegram_bot_token
ADMIN_IDS=your_telegram_id
WEBAPP_URL=https://your-project.up.railway.app

# AI Keys (at least one required — all free)
GR1=groq_key
G1=gemini_key
CB1=cerebras_key
OR1=openrouter_key
```

### 3. Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app)

```bash
railway up
```

## 💻 PC Agent Setup

The PC Agent runs on your local computer and connects to NEXUM via WebSocket.

```bash
# Install
pip install websockets psutil pillow pyautogui

# Run
python nexum_agent.py wss://your-project.up.railway.app/ws
```

**Linking flow:**
1. Agent starts → displays a 6-character code
2. Send `/link CODE` to the bot
3. Agent is now connected ✅

## 🤖 Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome & overview |
| `/apps` | Open mini-apps hub |
| `/pc` | PC Agent status |
| `/link CODE` | Link PC Agent |
| `/screenshot` | Take screenshot |
| `/run CMD` | Execute terminal command |
| `/finance` | Finance dashboard |
| `/notes` | Notes manager |
| `/tasks` | Task manager |
| `/habits` | Habit tracker |
| `/remind TEXT` | Set reminder |
| `/memory` | View stored memories |
| `/forget` | Clear all memories |
| `/search QUERY` | Web search |
| `/status` | System status |
| `/admin` | Admin panel (admin only) |

## 📱 Mini Apps

Access via `/apps` or the Hub button:

- **💰 Finance** — Track income, expenses, budgets
- **📝 Notes** — Save and organize notes
- **✅ Tasks** — Manage tasks and projects
- **🎯 Habits** — Build daily habits

## 🔒 Security

- Bot token never sent to PC Agent
- All PC ↔ Server communication via WebSocket
- Sensitive actions require user confirmation
- HMAC-based mini-app token auth

## 🛠 Tech Stack

- **Runtime:** Node.js 20 + TypeScript
- **Bot:** grammY
- **DB:** SQLite (better-sqlite3)
- **AI:** Cerebras, Groq, Gemini, OpenRouter, SambaNova, Together (all free)
- **Voice:** Groq Whisper + Edge-TTS
- **PC Agent:** Python + WebSocket

---

<div align="center">

Made with ❤️ by [thenexumai](https://github.com/thenexumai)

</div>
