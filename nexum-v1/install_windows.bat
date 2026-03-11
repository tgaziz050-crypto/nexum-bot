@echo off
:: NEXUM Agent — Установка автозапуска на Windows
:: Запусти от имени администратора!

setlocal

:: ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
:: НАСТРОЙ ЭТИ ПЕРЕМЕННЫЕ:
set NEXUM_WS_URL=ws://ТВОЙ_RAILWAY_URL:18790
set NEXUM_OWNER_ID=ТВОЙ_TELEGRAM_ID
set NEXUM_MODE=SAFE
:: ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set SCRIPT_DIR=%~dp0
set PYTHON_PATH=python
set AGENT_SCRIPT=%SCRIPT_DIR%nexum_agent.py
set TASK_NAME=NexumAgent

echo.
echo  NEXUM PC Agent — Установка автозапуска
echo  =========================================

:: Проверяем Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ОШИБКА: Python не найден. Установи python.org
    pause
    exit /b 1
)
echo  [OK] Python найден

:: Устанавливаем зависимости
echo  Устанавливаем зависимости...
pip install websockets pyautogui pillow psutil --quiet
echo  [OK] Зависимости установлены

:: Удаляем старое задание если есть
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

:: Создаём XML для Task Scheduler
set XML_FILE=%TEMP%\nexum_task.xml
(
echo ^<?xml version="1.0" encoding="UTF-16"?^>
echo ^<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"^>
echo   ^<Triggers^>
echo     ^<LogonTrigger^>
echo       ^<Enabled^>true^</Enabled^>
echo     ^</LogonTrigger^>
echo   ^</Triggers^>
echo   ^<Principals^>
echo     ^<Principal id="Author"^>
echo       ^<LogonType^>InteractiveToken^</LogonType^>
echo       ^<RunLevel^>HighestAvailable^</RunLevel^>
echo     ^</Principal^>
echo   ^</Principals^>
echo   ^<Settings^>
echo     ^<MultipleInstancesPolicy^>IgnoreNew^</MultipleInstancesPolicy^>
echo     ^<DisallowStartIfOnBatteries^>false^</DisallowStartIfOnBatteries^>
echo     ^<StopIfGoingOnBatteries^>false^</StopIfGoingOnBatteries^>
echo     ^<ExecutionTimeLimit^>PT0S^</ExecutionTimeLimit^>
echo     ^<RestartOnFailure^>
echo       ^<Interval^>PT1M^</Interval^>
echo       ^<Count^>999^</Count^>
echo     ^</RestartOnFailure^>
echo   ^</Settings^>
echo   ^<Actions Context="Author"^>
echo     ^<Exec^>
echo       ^<Command^>pythonw.exe^</Command^>
echo       ^<Arguments^>"%AGENT_SCRIPT%"^</Arguments^>
echo       ^<WorkingDirectory^>%SCRIPT_DIR%^</WorkingDirectory^>
echo     ^</Exec^>
echo   ^</Actions^>
echo ^</Task^>
) > "%XML_FILE%"

:: Создаём задачу
schtasks /create /tn "%TASK_NAME%" /xml "%XML_FILE%" /f
if errorlevel 1 (
    echo ОШИБКА: Не удалось создать задачу. Запусти от администратора.
    pause
    exit /b 1
)

:: Устанавливаем переменные среды
setx NEXUM_WS_URL "%NEXUM_WS_URL%" /m >nul
setx NEXUM_OWNER_ID "%NEXUM_OWNER_ID%" /m >nul
setx NEXUM_MODE "%NEXUM_MODE%" /m >nul

:: Запускаем сразу
schtasks /run /tn "%TASK_NAME%"

echo.
echo  =========================================
echo  NEXUM Agent установлен и запущен!
echo  Автозапуск: при каждом входе в Windows
echo  Перезапуск: автоматически при падении
echo  Управление: Диспетчер задач → NexumAgent
echo  =========================================
echo.
pause
