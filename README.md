# NEXUM — Personal AI Assistant for Telegram

<div align="center">
  <img src="https://i.imgur.com/placeholder.png" alt="NEXUM Logo" width="80">
  <h3>Your intelligent Telegram bot with 4 built-in mini-apps</h3>
</div>

---

## ✨ What NEXUM can do

### 🤖 AI Chat
- Multi-provider fallback: **Cerebras → Groq → Gemini → Grok → SambaNova → DeepSeek → Claude**
- 🌐 Web search (Serper / Brave API)
- 🧠 Long-term memory about you
- 🎤 Voice messages & video circles (STT + TTS)
- 👁 Image analysis (Vision AI)
- 😄 Smart emoji reactions

### 📱 Mini-Apps (Apple-style design)
| App | Description |
|-----|-------------|
| 💰 **Finance** | Balance, transactions, budgets, CBU currency rates |
| 📝 **Notes** | Color-coded notes with search & pinning |
| ✅ **Tasks** | Projects, priorities, completion tracking |
| 🎯 **Habits** | Daily habits with streaks |

### ⚙️ Productivity Tools
- ⏰ Smart reminders — natural language (`"через 30 минут"`, `"завтра в 10"`)
- 🔔 Alarm with snooze
- 💸 Auto-detect finance transactions from chat
- 📝 Auto-save notes from chat (`"запиши..."`)
- 📋 Auto-create tasks from chat
- ☀️ Daily digest at 9:00 AM
- 💻 **PC Agent** — control your computer from Telegram

---

## 🚀 Deploy on Railway

### 1. Fork & connect to Railway
```
https://railway.app → New Project → Deploy from GitHub
```

### 2. Required environment variables
```env
BOT_TOKEN=your_telegram_bot_token
ADMIN_IDS=your_telegram_user_id
WEBAPP_URL=https://your-project.up.railway.app
```

### 3. AI Provider keys (add at least one)
```env
# Cerebras (free, fast)
CB1=your_cerebras_key

# Groq (free)
GR1=your_groq_key

# Google Gemini (free tier)
G1=your_gemini_key

# xAI Grok
GK1=your_grok_key

# DeepSeek
DS1=your_deepseek_key

# Anthropic Claude
CL1=your_claude_key

# OpenRouter (free models)
OR1=your_openrouter_key
```

### 4. Optional: Web search
```env
SERPER_KEY1=your_serper_key   # serper.dev
BRAVE_KEY1=your_brave_key     # search.brave.com
```

### 5. Configure mini-apps in BotFather
1. Open **@BotFather** → `/mybots` → select NEXUM
2. **Bot Settings** → **Configure Mini App**
3. Set URL: `https://your-project.up.railway.app/hub`
4. **Menu Button** → set same URL

---

## 💻 PC Agent Setup

Install on your computer to give NEXUM access:

```bash
pip install websockets pyautogui pillow psutil apscheduler requests
python nexum_agent.py
```

Available commands after connecting:
- `/screenshot` — take screenshot
- `/run command` — execute terminal command  
- `/sysinfo` — system information

---

## 🛠 Tech Stack

- **Runtime**: Node.js + TypeScript
- **Bot**: Grammy (Telegram Bot Framework)
- **Database**: SQLite (better-sqlite3)
- **Deploy**: Railway / Docker
- **Mini-Apps**: Vanilla HTML/CSS/JS (Telegram WebApp API)

---

## 📁 Project Structure

```
src/
├── ai/           # AI engine (multi-provider fallback)
├── channels/     # Bot message handlers
├── commands/     # Telegram commands
├── core/         # Config, DB, logger, heartbeat
├── finance/      # Finance module
├── memory/       # Long-term memory system
├── nodes/        # PC Agent WebSocket server
├── tools/        # Notes, Tasks, Habits, Reminders, Alarms
├── automation/   # Schedulers
└── webapp/       # Mini-apps (Finance, Notes, Tasks, Habits, Hub)
```

---

## 🤖 Bot Commands

```
/start    — Welcome & mini-apps
/apps     — Open all mini-apps
/help     — Full command list
/new      — Start new conversation
/memory   — View my memory
/status   — My status
/brief    — Daily digest

/finance  — Finance overview
/notes    — My notes
/tasks    — My tasks
/habits   — Habit tracker
/remind   — Set reminder
/search   — Web search

/node_connect  — Connect PC Agent
/screenshot    — PC screenshot
/run           — Run command on PC
```

---

<div align="center">
  Made with ❤️ | <a href="https://t.me/ainexum_bot">@ainexum_bot</a>
</div>
