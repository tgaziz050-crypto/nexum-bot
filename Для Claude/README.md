# NEXUM v6.0

## Быстрый старт

1. `pip install -r requirements.txt`
2. Установи ffmpeg (для видео/аудио):
   - Windows: https://ffmpeg.org/download.html
   - Linux: `apt install ffmpeg`
   - Mac: `brew install ffmpeg`
3. Создай `.env` с переменными (см. `config.example.env` в корне)
4. `python bot.py`

## Переменные окружения

- `BOT_TOKEN` — токен Telegram-бота
- `G1`, `G2`, … — ключи Gemini (опционально)
- `GR1`, `GR2`, … — ключи Groq
- `DS1`, … — ключи DeepSeek
- `AUDD_API_KEY` — распознавание музыки (audd.io)
- `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` — отправка email

## Возможности

| Функция | Описание |
|---------|----------|
| 💬 Чат | AI-диалог, учёт контекста |
| 🎨 Творчество | Генерация фото, текстов, кода |
| 🎵 Музыка | Генерация и распознавание (Shazam-like) |
| 🎬 Видео | Анализ и генерация |
| 🔊 Голос | TTS, распознавание речи |
| 📥 Скачивание | YouTube, TikTok, VK |
| 📧 Email | Отправка с подтверждением |
| 📊 Группа / канал | Статистика, посты, расписание |

## Деплой

Railway / Render / любой Docker-хостинг. Добавь переменные в настройках проекта.
