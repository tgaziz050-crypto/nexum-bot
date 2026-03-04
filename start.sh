#!/bin/bash
echo "========================================"
echo "        NEXUM Bot - Запуск"
echo "========================================"
echo ""

# Проверяем наличие .env
if [ ! -f .env ]; then
    echo "[!] Файл .env не найден!"
    echo "Скопируй .env.example в .env и заполни ключи."
    exit 1
fi

# Загружаем переменные
export $(cat .env | grep -v '#' | xargs)

# Устанавливаем зависимости
echo "[1/3] Устанавливаю зависимости..."
pip install -r requirements.txt -q

echo "[2/3] Проверяю настройки..."
if [ -z "$BOT_TOKEN" ]; then
    echo "[!] BOT_TOKEN не задан!"
    exit 1
fi
if [ -z "$ANTHROPIC_KEY" ]; then
    echo "[!] ANTHROPIC_KEY не задан!"
    exit 1
fi

echo "[3/3] Запускаю NEXUM..."
echo ""
echo "Бот запущен! Напиши ему в Telegram."
echo "Для остановки нажми Ctrl+C"
echo ""
python bot.py
