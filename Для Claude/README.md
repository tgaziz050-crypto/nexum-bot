# NEXUM v1.0 — AI Telegram Bot

Модель: nexum v1.0. Имя: NEXUM.

## Быстрый старт

1. `pip install -r requirements.txt`
2. Установи ffmpeg и yt-dlp
3. Скопируй `config.example.env` в `.env`, заполни `BOT_TOKEN`
4. `python bot.py`

## Переменные (.env)

- `BOT_TOKEN` — обязательно
- `G1`, `GR1`, `DS1` — AI (нужен хотя бы один)
- `AUDD_API_KEY` — распознавание музыки
- `NOTION_API_KEY`, `NOTION_DATABASE_ID` — Notion
- `ADMIN_IDS` — ID админов (согласование опасных действий)

## Возможности

Управление через естественный язык — без кнопок:

- Генерация изображений, видео, инструментальной музыки
- Создание страниц в Notion
- Несколько каналов
- Поиск, погода, TTS, скачивание
