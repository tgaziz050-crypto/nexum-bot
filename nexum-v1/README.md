# NEXUM v1

Персональная AI-платформа для Telegram с поддержкой множества пользователей, управлением ПК и мультимодельным AI роутингом.

## Возможности

- 🧠 **Персональная память** — каждый пользователь изолирован, данные не перемешиваются
- 🤖 **Multi-model AI** — Cerebras, Groq, Gemini, Grok, SambaNova, Together, OpenRouter, DeepSeek, Claude
- 🎤 **Голос** — STT через Groq Whisper, TTS через edge-tts
- 👁 **Vision** — анализ фото через Gemini/Claude/OpenRouter
- 🌐 **Поиск** — Serper → Brave → DuckDuckGo
- 💻 **PC Agent** — управление компьютером через WebSocket
- ⏰ **Напоминания** — парсинг естественного языка
- 👮 **Admin панель** — бан, статистика, рассылка

## Быстрый старт (Railway)

1. Форкни репозиторий на GitHub
2. Подключи его к Railway
3. Добавь переменные из `.env.example` в Railway → Variables
4. Готово — Railway задеплоит автоматически

## Переменные (Railway Variables)

| Переменная | Описание |
|-----------|----------|
| `BOT_TOKEN` | Токен от @BotFather |
| `ADMIN_IDS` | Твой Telegram ID (через запятую) |
| `CB1..CB5` | Ключи Cerebras |
| `GR1..GR5` | Ключи Groq |
| `G1..G5`   | Ключи Gemini |
| `OR1..OR3` | Ключи OpenRouter |
| `CL1`      | Ключ Claude |
| `PUBLIC_BOT` | `true` — открытый, `false` — только для ADMIN_IDS |

## PC Агент

```bash
# Установка зависимостей
pip install websockets pyautogui pillow psutil

# Windows (автозапуск)
# Отредактируй install_windows.bat и запусти от администратора

# Linux/Mac (systemd)
export NEXUM_WS_URL=ws://твой-сервер:18790
export NEXUM_OWNER_ID=твой_telegram_id
sudo python nexum_agent.py --install-service
```

Режимы агента (`NEXUM_MODE`):
- `SAFE` — опасные команды (удаление, установка, сеть) требуют подтверждения кнопками в Telegram
- `AUTO` — всё автоматически

## Изоляция данных

Каждый пользователь идентифицируется по `uid` (Telegram ID). Все запросы к БД строго фильтруются по `WHERE uid=?`. Данные одного пользователя физически невозможно получить с `uid` другого.

## Структура

```
src/
  ai/          — провайдеры и роутер AI
  channels/    — бот, хендлеры, форматирование
  commands/    — команды пользователей и admin
  core/        — config, db, logger, guard
  memory/      — промпты, экстрактор памяти
  nodes/       — PC агент (WebSocket)
  tools/       — поиск, STT, TTS, изображения, напоминания
  automation/  — cron задачи
```
