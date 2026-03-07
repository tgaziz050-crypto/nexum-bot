"""
NEXUM — Email-менеджер.
Поддерживает: SMTP/TLS, IMAP, расписание, шаблоны.
"""
import asyncio
import smtplib
import imaplib
import email as email_lib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, Dict, List, Any

log = logging.getLogger("NEXUM.email")

# Конфигурации популярных почтовых сервисов
EMAIL_PROVIDERS = {
    "gmail.com": {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "name": "Gmail",
        "app_password_url": "myaccount.google.com/apppasswords",
        "hint": "Нужен App Password (не основной пароль). Включи 2FA, затем создай App Password.",
    },
    "mail.ru": {
        "smtp_host": "smtp.mail.ru",
        "smtp_port": 587,
        "imap_host": "imap.mail.ru",
        "imap_port": 993,
        "name": "Mail.ru",
        "hint": "Включи доступ по паролю в настройках Mail.ru",
    },
    "yandex.ru": {
        "smtp_host": "smtp.yandex.ru",
        "smtp_port": 587,
        "imap_host": "imap.yandex.ru",
        "imap_port": 993,
        "name": "Яндекс Почта",
        "hint": "В настройках Яндекс.Почты включи IMAP и создай пароль для внешних приложений.",
    },
    "outlook.com": {
        "smtp_host": "smtp-mail.outlook.com",
        "smtp_port": 587,
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "name": "Outlook",
        "hint": "Используй пароль от аккаунта Microsoft.",
    },
    "hotmail.com": {
        "smtp_host": "smtp-mail.outlook.com",
        "smtp_port": 587,
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "name": "Hotmail",
        "hint": "Используй пароль от аккаунта Microsoft.",
    },
    "yahoo.com": {
        "smtp_host": "smtp.mail.yahoo.com",
        "smtp_port": 587,
        "imap_host": "imap.mail.yahoo.com",
        "imap_port": 993,
        "name": "Yahoo",
        "hint": "Нужен App Password Yahoo.",
    },
}

# Глобальное хранилище конфигов пользователей (uid -> config)
# В продакшне лучше хранить в зашифрованной БД
USER_EMAIL_CONFIGS: Dict[int, Dict] = {}


def get_email_provider(email_addr: str) -> Optional[Dict]:
    """Определить провайдер по email-адресу."""
    if "@" not in email_addr:
        return None
    domain = email_addr.split("@")[1].lower()
    return EMAIL_PROVIDERS.get(domain)


def save_user_email_config(uid: int, email_addr: str, password: str, smtp_host: str = "",
                           smtp_port: int = 587, imap_host: str = "", imap_port: int = 993):
    """Сохранить конфиг email пользователя."""
    USER_EMAIL_CONFIGS[uid] = {
        "email": email_addr,
        "password": password,  # В продакшне — шифровать!
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "imap_host": imap_host,
        "imap_port": imap_port,
    }


def get_user_email_config(uid: int) -> Optional[Dict]:
    """Получить конфиг email пользователя."""
    # Сначала смотрим личный конфиг
    if uid in USER_EMAIL_CONFIGS:
        return USER_EMAIL_CONFIGS[uid]
    # Потом .env
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    if smtp_host and smtp_user and smtp_pass:
        return {
            "email": smtp_user,
            "password": smtp_pass,
            "smtp_host": smtp_host,
            "smtp_port": int(os.getenv("SMTP_PORT", "587")),
            "imap_host": os.getenv("IMAP_HOST", ""),
            "imap_port": int(os.getenv("IMAP_PORT", "993")),
        }
    return None


async def send_email(uid: int, to_addr: str, subject: str, body: str,
                     html: bool = False) -> tuple:
    """
    Отправить email от имени пользователя.
    Возвращает (success: bool, message: str)
    """
    config = get_user_email_config(uid)
    if not config:
        return False, (
            "Email не настроен.\n\n"
            "Скажи мне: 'Настрой мою почту' и я помогу подключить Gmail/Яндекс/Mail.ru"
        )

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config["email"]
        msg["To"] = to_addr

        if html:
            msg.attach(MIMEText(body, "html", "utf-8"))
        else:
            msg.attach(MIMEText(body, "plain", "utf-8"))

        loop = asyncio.get_event_loop()

        def _send():
            with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(config["email"], config["password"])
                server.send_message(msg)

        await loop.run_in_executor(None, _send)
        log.info(f"Email sent: {config['email']} -> {to_addr}")
        return True, f"Письмо отправлено на {to_addr}"

    except smtplib.SMTPAuthenticationError:
        return False, (
            "Ошибка аутентификации.\n\n"
            "Для Gmail нужен App Password (не основной пароль).\n"
            "Для Яндекс/Mail.ru включи SMTP-доступ в настройках."
        )
    except Exception as e:
        log.error(f"Send email: {e}")
        return False, f"Ошибка отправки: {str(e)[:200]}"


async def read_emails(uid: int, folder: str = "INBOX", count: int = 5) -> tuple:
    """
    Прочитать последние письма.
    Возвращает (success: bool, data: list | error_str)
    """
    config = get_user_email_config(uid)
    if not config:
        return False, "Email не настроен."
    if not config.get("imap_host"):
        return False, "IMAP не настроен."

    try:
        loop = asyncio.get_event_loop()

        def _read():
            mail = imaplib.IMAP4_SSL(config["imap_host"], config["imap_port"])
            mail.login(config["email"], config["password"])
            mail.select(folder)

            _, data = mail.search(None, "ALL")
            ids = data[0].split()
            latest_ids = ids[-count:] if len(ids) >= count else ids

            messages = []
            for msg_id in reversed(latest_ids):
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)

                subject = str(email_lib.header.make_header(
                    email_lib.header.decode_header(msg["Subject"] or "")))
                from_addr = str(email_lib.header.make_header(
                    email_lib.header.decode_header(msg["From"] or "")))
                date = msg["Date"] or ""

                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            try:
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")[:500]
                            except:
                                pass
                            break
                else:
                    try:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")[:500]
                    except:
                        pass

                messages.append({
                    "subject": subject[:100],
                    "from": from_addr[:100],
                    "date": date[:50],
                    "body": body,
                })
            mail.logout()
            return messages

        messages = await loop.run_in_executor(None, _read)
        return True, messages

    except imaplib.IMAP4.error as e:
        return False, f"IMAP ошибка: {str(e)[:200]}"
    except Exception as e:
        log.error(f"Read emails: {e}")
        return False, f"Ошибка: {str(e)[:200]}"


def format_emails_list(messages: list) -> str:
    """Форматировать список писем для Telegram."""
    if not messages:
        return "Писем нет."
    result = f"Последние {len(messages)} писем:\n\n"
    for i, msg in enumerate(messages, 1):
        result += (
            f"{i}. От: {msg['from']}\n"
            f"   Тема: {msg['subject']}\n"
            f"   Дата: {msg['date']}\n"
            f"   {msg['body'][:100]}...\n\n"
        )
    return result


def get_setup_instructions(email_addr: str) -> str:
    """Получить инструкции по настройке для конкретного провайдера."""
    provider = get_email_provider(email_addr)
    if not provider:
        return (
            "Неизвестный провайдер.\n\n"
            "Укажи SMTP данные вручную:\n"
            "• SMTP хост\n• Порт (обычно 587)\n• Логин\n• Пароль"
        )
    return (
        f"Настройка {provider['name']}:\n\n"
        f"{provider['hint']}\n\n"
        f"Данные подключения:\n"
        f"SMTP: {provider['smtp_host']}:{provider['smtp_port']}\n"
        f"IMAP: {provider['imap_host']}:{provider['imap_port']}"
    )
