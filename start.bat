@echo off
echo ========================================
echo         NEXUM v2.0 - Запуск
echo ========================================
echo.

REM Устанавливаем зависимости
echo [1/2] Устанавливаю зависимости...
pip install -r requirements.txt -q

echo [2/2] Запускаю NEXUM...
echo.
echo Бот запущен! Напиши ему в Telegram.
echo Для остановки нажми Ctrl+C
echo.
python bot.py
pause
