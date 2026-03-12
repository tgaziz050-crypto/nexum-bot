# NEXUM v10

## Что нового в v10
- ✅ Полный редизайн всех Mini Apps (Apple + NEXUM logo стиль: чёрно-белый минимализм)
- ✅ Авто-определение Telegram UID (через `initDataUnsafe.user.id`, не нужно вводить вручную)
- ✅ NLP-автоматизация: бот автоматически пишет в Mini Apps ("потратил 50к на еду" → записывает в финансы)
- ✅ Мультиязычность: ru/en/uz/de/zh/ar
- ✅ Мультивалютность: UZS/USD/EUR/RUB/GBP/JPY/CNY и другие с реальными курсами
- ✅ Таблица accounts (счета) — отдельные счета с балансами
- ✅ PC Agent со всеми навыками OpenClaw (см. nexum_agent.py)
- ✅ API ключи только на Railway — другим пользователям ничего вводить не нужно

## Деплой
```bash
npm install && npm run build
# Push to GitHub → Railway auto-deploys
```

## Railway Variables (уже настроены)
BOT_TOKEN, WEBAPP_URL, CB1-7, GR1-7, G1-7, GK1-3, SN1-5, TO1-7, OR1-7, DS1-6, CL1, SERPER_KEY1-3

## Mini Apps URL
- Hub: WEBAPP_URL/
- Finance: WEBAPP_URL/finance
- Notes: WEBAPP_URL/notes
- Tasks: WEBAPP_URL/tasks
- Habits: WEBAPP_URL/habits

## PC Agent
```bash
pip install websockets pyautogui pillow psutil requests pyperclip
python nexum_agent.py wss://nexum-bot-production-ae70.up.railway.app/ws
# Затем в боте: /link → ввести код
```
