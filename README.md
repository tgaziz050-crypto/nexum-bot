# NEXUM v8 — Full OpenClaw PC Agent

## Что нового в v8: полный набор OpenClaw в PC Agent

### Команды управления агентом через бота

| Команда | Описание |
|---|---|
| `/pc` | Статус агента |
| `/link КОД` | Привязка — UID вшивается персонально |
| `/screenshot` | Скриншот экрана |
| `/screenshot x1,y1,x2,y2` | Скриншот региона |
| `/run <cmd>` | Терминальная команда |
| `/bgrun <cmd>` | Фоновый процесс |
| `/bglist` | Список фоновых процессов |
| `/bgstop <id>` | Остановить фоновый процесс |
| `/sysinfo` | CPU / RAM / Disk / Net |
| `/ps [limit]` | Топ процессов |
| `/kill <pid/имя>` | Убить процесс |
| `/files <op> <path>` | Файловая система |
| `/clipboard [read/write]` | Буфер обмена |
| `/notify Заголовок | Текст` | Системное уведомление |
| `/window [list/focus/close]` | Управление окнами |
| `/http METHOD url [body]` | HTTP-запрос |
| `/browser <url>` | Открыть URL |
| `/openapp <имя>` | Открыть приложение |
| `/mouse <action> [x y text]` | Управление мышью |
| `/keyboard <текст>` | Набрать текст |
| `/hotkey <combo>` | Нажать хоткей |
| `/network` | Сетевая информация |
| `/agentid` | Идентификация пользователя |

### Автоопределение и вшивание пользователя

При привязке (`/link КОД`) агент получает Telegram `uid` и сохраняет его
в `~/.nexum_agent.json` вместе с os_user, hostname, platform.
При следующих запусках агент автоматически регистрируется — ввод кода не нужен.

### Установка агента

```bash
pip install websockets pyautogui pillow psutil requests pyperclip plyer
python nexum_agent.py
# Свой сервер:
python nexum_agent.py wss://your-project.up.railway.app/ws
```

### Примеры

```
/run ls -la ~/Desktop
/bgrun python3 server.py
/files list ~/Documents
/files read ~/.bashrc
/files write ~/notes.txt привет
/files search ~/Projects *.py
/screenshot
/screenshot 0,0,1920,1080
/mouse click 500 300
/hotkey ctrl+shift+t
/http GET https://api.ipify.org
/notify Готово | Задача выполнена
/clipboard write текст для копирования
/kill chrome
/window list
```
