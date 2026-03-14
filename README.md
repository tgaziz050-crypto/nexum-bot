# NEXUM v11 — Autonomous AI Agent Platform

Полноценная AI-экосистема в Telegram.

## Архитектура

```
User → Telegram → NEXUM Bot → NEXUM Core → Task Planner → Tools → Executor → NEXUM Agent
```

## Компоненты

- **NEXUM Bot** — Telegram бот (TypeScript + grammy)
- **NEXUM Agent** — локальный PC-агент (Python)
- **Mini Apps** — встроенные web-приложения (Finance, Notes, Tasks, Habits, Sites, Tools)
- **Mission Control** — локальный admin-дашборд (NextJS, отдельный проект)

## Быстрый старт (Railway)

1. Создай новый проект на Railway
2. Подключи этот репозиторий
3. Добавь переменные из `.env.example`
4. Deploy

## Локальный запуск

```bash
npm install
cp .env.example .env
# Заполни .env
npm run dev
```

## PC Agent

```bash
pip install websockets pyautogui pillow psutil requests pyperclip plyer
python nexum_agent.py
# Или с Railway URL:
python nexum_agent.py wss://your-bot.up.railway.app/ws
```

После запуска агент покажет **код привязки** — отправь его боту командой `/link КОД`.  
После привязки uid вшивается в `~/.nexum_agent.json` — при следующем запуске привязка автоматическая.

## AI Провайдеры (приоритет)

1. Cerebras — `CB1..CB10` (fastest, Llama 3.3 70B)
2. Groq — `GR1..GR10` (fast, Llama 3.3 70B + Whisper STT)
3. Gemini — `G1..G10` (vision)
4. Grok — `GK1..GK10`
5. OpenRouter — `OR1..OR10`
6. DeepSeek — `DS1..DS10`
7. SambaNova — `SN1..SN10`
8. Together — `TO1..TO10`
9. Claude — `CL1..CL10`

Пользователи могут добавить свои ключи: `/setkey groq sk-...`

## Команды бота

| Команда | Описание |
|---------|---------|
| `/start` | Приветствие |
| `/help` | Список команд |
| `/apps` | Mini Apps |
| `/website [запрос]` | Создать сайт |
| `/newtool [описание]` | Создать инструмент |
| `/tools` | Мои инструменты |
| `/notes` | Заметки |
| `/tasks` | Задачи |
| `/habits` | Привычки |
| `/finance` | Финансы |
| `/search [запрос]` | Поиск в интернете |
| `/remind [текст]` | Напоминание |
| `/memory` | Что я знаю о тебе |
| `/forget` | Очистить память |
| `/clear` | Очистить историю |
| `/voice` | Голосовой режим |
| `/voices` | Выбор голоса |
| `/setkey [провайдер] [ключ]` | Добавить API ключ |
| `/mykeys` | Мои ключи |
| `/status` | Статистика |
| `/pc` | Статус PC Agent |
| `/link [код]` | Привязать агент |
| `/screenshot` | Скриншот экрана |
| `/run [команда]` | Выполнить команду |
| `/bgrun [команда]` | Фоновый процесс |
| `/bglist` | Фоновые процессы |
| `/sysinfo` | Системная информация |
| `/ps` | Процессы |
| `/kill [имя/pid]` | Убить процесс |
| `/files [op] [path]` | Файловая система |
| `/clipboard` | Буфер обмена |
| `/notify [title\|msg]` | Уведомление |
| `/window [op]` | Управление окнами |
| `/http [METHOD] [url]` | HTTP запрос |
| `/browser [url]` | Открыть браузер |
| `/openapp [имя]` | Открыть приложение |
| `/mouse [action] [x] [y]` | Мышь |
| `/keyboard [текст]` | Набрать текст |
| `/hotkey [combo]` | Горячие клавиши |
| `/network` | Сетевая информация |

## Admin команды

| Команда | Описание |
|---------|---------|
| `/admin` | Панель администратора |
| `/users` | Список пользователей |
| `/broadcast [текст]` | Рассылка всем |

## Языки

Поддерживается автоопределение языка: ru, en, uz, de, fr, es, ar, zh, ja, ko, tr, hi, uk, kk, pl, it, pt, nl, fa и др.
