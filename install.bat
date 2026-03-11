@echo off
chcp 65001 >nul
cls

echo.
echo ╔══════════════════════════════════════════╗
echo ║      NEXUM — Установка (Windows)        ║
echo ╚══════════════════════════════════════════╝
echo.

:: Проверяем Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден!
    echo    Скачай с: python.org/downloads
    echo    При установке отметь "Add Python to PATH"!
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYVER=%%i
echo ✅ %PYVER% найден

:: Создаём .env если нет
if not exist ".env" (
    if exist "config.example.env" (
        copy config.example.env .env >nul
        echo 📋 Создан файл .env из примера
    ) else (
        echo. > .env
        echo 📋 Создан пустой .env файл
    )
)

echo.
echo 🔑 Настройка ключей
echo.

:: Читаем BOT_TOKEN из .env
set BOT_TOKEN=
for /f "tokens=1,2 delims==" %%a in (.env) do (
    if "%%a"=="BOT_TOKEN" set BOT_TOKEN=%%b
)

if "%BOT_TOKEN%"=="" (
    echo Создай бота в @BotFather → /newbot и вставь токен:
    set /p BOT_TOKEN=BOT_TOKEN: 
)
if "%BOT_TOKEN%"=="YOUR_BOT_TOKEN_HERE" (
    set BOT_TOKEN=
    echo Создай бота в @BotFather → /newbot и вставь токен:
    set /p BOT_TOKEN=BOT_TOKEN: 
)
if "%BOT_TOKEN%"=="" (
    echo ❌ BOT_TOKEN обязателен!
    pause
    exit /b 1
)

:: Читаем G1 из .env
set G1=
for /f "tokens=1,2 delims==" %%a in (.env) do (
    if "%%a"=="G1" set G1=%%b
)
if "%G1%"=="" (
    echo.
    echo Получи бесплатный Gemini ключ: aistudio.google.com/apikey
    set /p G1=G1 (Gemini ключ): 
)

:: Читаем GR1 из .env
set GR1=
for /f "tokens=1,2 delims==" %%a in (.env) do (
    if "%%a"=="GR1" set GR1=%%b
)
if "%GR1%"=="" (
    echo.
    echo Получи бесплатный Groq ключ: console.groq.com
    set /p GR1=GR1 (Groq ключ): 
)

:: Сохраняем в .env
(
    echo # NEXUM — создано install.bat
    echo BOT_TOKEN=%BOT_TOKEN%
    if not "%G1%"=="" echo G1=%G1%
    if not "%GR1%"=="" echo GR1=%GR1%
) > .env.tmp
move /y .env.tmp .env >nul

echo.
echo 📦 Установка зависимостей...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ⚠️  Попытка с --break-system-packages...
    python -m pip install -r requirements.txt --quiet --break-system-packages
)

echo.
echo ✅ Всё готово!
echo.
echo 🚀 Запускаю NEXUM...
echo.

:: Устанавливаем переменные окружения
for /f "tokens=1,2 delims==" %%a in (.env) do (
    if not "%%a:~0,1%"=="#" set %%a=%%b
)

python bot.py

pause
