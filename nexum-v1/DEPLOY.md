# Как залить NEXUM v1 на GitHub и задеплоить на Railway

## Если репозиторий уже существует (старая версия)

```bash
# 1. Клонируй старый репозиторий (если ещё не склонирован)
git clone https://github.com/ТВОЙusername/nexum-bot.git
cd nexum-bot

# 2. Создай ветку для новой версии (чтобы не потерять старое)
git checkout -b v1

# 3. Удали старые файлы (оставь только .git)
git rm -rf .
git clean -fdx

# 4. Скопируй все файлы из папки nexum-v1/ в корень репозитория
# (на Windows: xcopy /E /I путь\nexum-v1\* .)
# (на Mac/Linux: cp -r путь/nexum-v1/* .)

# 5. Добавь всё и сделай коммит
git add .
git commit -m "feat: NEXUM v1 — multi-user platform"

# 6. Запушь ветку
git push origin v1

# 7. На GitHub сделай v1 основной веткой:
#    Settings → Branches → Default branch → v1
```

## Если создаёшь новый репозиторий

```bash
# 1. Создай репозиторий на github.com (без README)
# Назови: nexum-bot

# 2. Инициализируй локально
cd путь/к/nexum-v1
git init
git add .
git commit -m "feat: NEXUM v1 — initial release"

# 3. Подключи и запушь
git remote add origin https://github.com/ТВОЙusername/nexum-bot.git
git branch -M main
git push -u origin main
```

## Деплой на Railway

1. Зайди на railway.app
2. New Project → Deploy from GitHub repo
3. Выбери репозиторий nexum-bot
4. Railway автоматически обнаружит Dockerfile
5. Перейди в Variables и добавь все переменные из `.env.example`:
   - `BOT_TOKEN` — токен бота
   - `ADMIN_IDS` — твой Telegram ID
   - `G1`, `GR1`, `CB1` — хотя бы по одному AI ключу
6. Нажми Deploy

## Открыть порт для PC Агента (Railway)

Settings → Networking → Add TCP Proxy → порт 18790

Получишь адрес типа: `monorail.proxy.rlwy.net:XXXXX`
Этот адрес вставляй в `NEXUM_WS_URL` агента.

## Проверка деплоя

После деплоя напиши боту `/start` — должен ответить.
Напиши `/status` — покажет провайдеры и статистику.
Напиши `/id` — покажет твой Telegram ID.
