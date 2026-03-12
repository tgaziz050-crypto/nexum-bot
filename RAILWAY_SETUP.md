# NEXUM — Настройка Railway

## Шаг 1: Переменные окружения в Railway Dashboard

Открой проект → Variables → добавь:

```
BOT_TOKEN=твой_токен_от_BotFather
WEBAPP_URL=https://ТУТ_ТВОЙ_ДОМЕН.up.railway.app
DB_PATH=/data/nexum.db
```

## Шаг 2: Volume для базы данных

Settings → Volumes → Add Volume:
- Mount path: `/data`

Без этого база данных сбрасывается при каждом деплое!

## Шаг 3: Домен

Settings → Networking → Generate Domain
Скопируй домен и вставь в WEBAPP_URL (без слеша в конце).

## Шаг 4: После деплоя — проверь

Напиши боту /start — должен ответить.
Нажми Mini Apps — должны открываться.

## Частые проблемы

**"Not Found"** → WEBAPP_URL в Railway Variables неправильный, или домен не настроен.

**"no such column: created_at"** → Исправлено в v10. Просто задеплой новый код.

**Бот не отвечает** → Проверь BOT_TOKEN, он должен быть без пробелов.

**Фото не анализирует** → Нужен ключ G1 (Gemini). Получи на https://aistudio.google.com

## AI ключи (все бесплатные)

| Провайдер | Переменная | Сайт |
|-----------|-----------|------|
| Cerebras (быстрый) | CB1..CB7 | cloud.cerebras.ai |
| Groq (whisper STT) | GR1..GR7 | console.groq.com |
| Gemini (фото/видео) | G1..G7 | aistudio.google.com |
| DeepSeek | DS1..DS6 | platform.deepseek.com |
| SambaNova | SN1..SN5 | cloud.sambanova.ai |
| OpenRouter | OR1..OR7 | openrouter.ai |
| Serper (поиск) | SERPER_KEY | serper.dev |
