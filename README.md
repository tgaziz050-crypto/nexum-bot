# 🤖 NEXUM — Персональный AI Ассистент

> NEXUM. Работает в Telegram. Управляет твоим ПК.  
> Помнит всё. Умеет всё. Бесплатно.

[![Python](https://img.shields.io/badge/python-3.11-blue)](https://python.org)
[![Telegram](https://img.shields.io/badge/platform-Telegram-blue)](https://telegram.org)
[![Railway](https://img.shields.io/badge/hosting-Railway-black)](https://railway.app)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## ✨ Возможности

| | |
|---|---|
| 🧠 **Умная память** | Помнит факты, проекты, людей, решения |
| 💻 **Управление ПК** | Файлы, команды, браузер, скриншоты — через Telegram |
| 🤖 **AI агенты** | Автономное выполнение сложных задач |
| ⏰ **Напоминания** | Настоящие, не теряются при перезапуске |
| 🌐 **Интернет** | Поиск, чтение сайтов, мониторинг |
| 👁 **Видение** | Анализ фото, видео, PDF, документов |
| 🎤 **Голос** | 87 голосов, 30+ языков, авто-выбор |
| 🎵 **Музыка** | Распознавание Shazam + генерация MusicGen |
| 🔄 **Самообновление** | Бот дописывает свой код через GitHub |

---

## 🚀 Способ 1 — Локально на ПК (без серверов)

### Windows — одной командой:
```
install.bat
```

### Linux / Mac — одной командой:
```bash
bash install.sh
```

Скрипт сам спросит ключи и запустит бота!

### Или вручную:
```bash
git clone https://github.com/nexumai/nexum-bot
cd nexum-bot
pip install -r requirements.txt
cp config.example.env .env
# Вставь ключи в .env
python bot.py
```

---

## ☁️ Способ 2 — Деплой на Railway (24/7)

1. Загрузи на GitHub
2. [railway.app](https://railway.app) → New Project → GitHub repo
3. Добавь переменные в Variables
4. Готово ✅

---

## 🔑 Минимальные ключи

| Ключ | Где взять | |
|---|---|---|
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) | ✅ Обязательно |
| `G1` | [aistudio.google.com](https://aistudio.google.com/apikey) | ✅ Бесплатно |
| `GR1` | [console.groq.com](https://console.groq.com) | ✅ Бесплатно |

Этих трёх хватает для полноценной работы!

---

## 🌍 Мультипользовательский режим

По умолчанию бот **открытый** — любой пользователь может им пользоваться.  
У каждого пользователя своя память, настройки и данные.

Чтобы закрыть только для себя:
```env
ADMIN_IDS=123456789    # твой Telegram ID
PUBLIC_BOT=false
```

---

## 💻 PC Агент

1. Напиши `/start` → «💻 Подключить компьютер» → «⬇️ Скачать мой агент»
2. Получишь персональный файл — уже настроен под тебя
3. Запусти: `python nexum_agent.py`

Никаких токенов вводить не нужно — всё вшито автоматически!

---

## 🛠 Команды

```
/start    — начало
/help     — полная справка
/install  — инструкция по локальной установке
/myid     — твой Telegram ID
/agent    — автономный агент
/remind   — напоминания
/code     — выполнить код
/memory   — память
```

---

## 🔄 Автозапуск

**Windows** — создай `start_nexum.bat` и добавь в автозагрузку (Win+R → `shell:startup`):
```bat
@echo off
cd C:\путь\к\nexum-bot
python bot.py
```

**Linux** — добавь в crontab (`crontab -e`):
```
@reboot cd /путь/к/nexum-bot && python3 bot.py &
```

---

## 📜 Лицензия

MIT
