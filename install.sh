#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║         NEXUM — Установка одной командой                    ║
# ║         Запуск: bash install.sh                             ║
# ╚══════════════════════════════════════════════════════════════╝

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║      🤖 NEXUM — Установка               ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

# Проверяем Python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo -e "${RED}❌ Python не найден. Установи Python 3.10+${NC}"
    echo "   Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "   Mac:           brew install python3"
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)
echo -e "${GREEN}✅ Python найден: $($PYTHON --version)${NC}"

# Проверяем pip
if ! $PYTHON -m pip --version &>/dev/null; then
    echo -e "${RED}❌ pip не найден.${NC}"
    echo "   Ubuntu/Debian: sudo apt install python3-pip"
    exit 1
fi

# Проверяем .env
if [ ! -f ".env" ]; then
    if [ -f "config.example.env" ]; then
        cp config.example.env .env
        echo -e "${YELLOW}📋 Создан файл .env из примера${NC}"
    else
        touch .env
        echo -e "${YELLOW}📋 Создан пустой файл .env${NC}"
    fi
fi

# Читаем ключи из .env если есть
source_env() {
    if [ -f ".env" ]; then
        export $(grep -v '^#' .env | grep -v '^$' | xargs) 2>/dev/null || true
    fi
}
source_env

# Запрашиваем обязательные ключи если не заданы
echo ""
echo -e "${CYAN}🔑 Настройка ключей${NC}"
echo ""

if [ -z "$BOT_TOKEN" ] || [ "$BOT_TOKEN" = "YOUR_BOT_TOKEN_HERE" ]; then
    echo "Создай бота в @BotFather → /newbot и вставь токен:"
    read -p "BOT_TOKEN: " BOT_TOKEN
    if [ -z "$BOT_TOKEN" ]; then
        echo -e "${RED}❌ BOT_TOKEN обязателен!${NC}"
        exit 1
    fi
fi

if [ -z "$G1" ] || [ "$G1" = "YOUR_GEMINI_KEY_1" ]; then
    echo ""
    echo "Получи бесплатный Gemini ключ на aistudio.google.com/apikey"
    read -p "G1 (Gemini ключ): " G1
fi

if [ -z "$GR1" ] || [ "$GR1" = "YOUR_GROQ_KEY_1" ]; then
    echo ""
    echo "Получи бесплатный Groq ключ на console.groq.com"
    read -p "GR1 (Groq ключ): " GR1
fi

# Сохраняем в .env
{
    echo "# NEXUM — автоматически создано install.sh"
    echo "BOT_TOKEN=$BOT_TOKEN"
    [ -n "$G1" ] && echo "G1=$G1"
    [ -n "$GR1" ] && echo "GR1=$GR1"
    # Добавляем остальные из старого .env
    grep -v '^#' .env 2>/dev/null | grep -v '^$' | grep -v '^BOT_TOKEN=' | grep -v '^G1=' | grep -v '^GR1=' || true
} > .env.tmp && mv .env.tmp .env

echo ""
echo -e "${CYAN}📦 Установка зависимостей...${NC}"
$PYTHON -m pip install -r requirements.txt --quiet --break-system-packages 2>/dev/null || \
$PYTHON -m pip install -r requirements.txt --quiet

echo ""
echo -e "${GREEN}✅ Всё готово!${NC}"
echo ""
echo -e "${CYAN}🚀 Запуск NEXUM:${NC}"
echo ""

# Запускаем
echo -e "${GREEN}Запускаю NEXUM...${NC}"
echo ""
export $(cat .env | grep -v '^#' | grep -v '^$' | xargs) 2>/dev/null || true
$PYTHON bot.py
