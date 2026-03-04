@echo off
echo ========================================
echo         NEXUM Bot - Запуск
echo ========================================
echo.

REM Проверяем наличие .env файла
if not exist .env (
    echo [!] Файл .env не найден!
    echo Скопируй .env.example в .env и заполни ключи.
    pause
    exit
)

REM Загружаем переменные из .env
for /f "tokens=1,2 delims==" %%a in (.env) do (
    if not "%%a"=="" if not "%%b"=="" set %%a=%%b
)

REM Устанавливаем зависимости
echo [1/3] Устанавливаю зависимости...
pip install -r requirements.txt -q

echo [2/3] Проверяю настройки...
if "%BOT_TOKEN%"=="" (
    echo [!] BOT_TOKEN не задан в .env файле!
    pause
    exit
)
if "%ANTHROPIC_KEY%"=="" (
    echo [!] ANTHROPIC_KEY не задан в .env файле!
    pause
    exit
)

echo [3/3] Запускаю NEXUM...
echo.
echo Бот запущен! Напиши ему в Telegram.
echo Для остановки нажми Ctrl+C
echo.
python bot.py
pause
