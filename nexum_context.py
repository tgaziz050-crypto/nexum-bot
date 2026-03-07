"""
NEXUM — Управление контекстом среды.
ЛИЧНЫЙ ЧАТ | ГРУППА | СУПЕРОГРУППА | КАНАЛ
"""
from enum import Enum
from typing import Optional


class ChatContext(Enum):
    PRIVATE = "private"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"


def get_chat_context(chat_type: str) -> ChatContext:
    """Определить контекст чата по его типу."""
    if chat_type == "private":
        return ChatContext.PRIVATE
    if chat_type == "channel":
        return ChatContext.CHANNEL
    if chat_type == "group":
        return ChatContext.GROUP
    if chat_type == "supergroup":
        return ChatContext.SUPERGROUP
    return ChatContext.PRIVATE


def context_instructions(ctx: ChatContext) -> str:
    """Инструкции для AI в зависимости от контекста."""
    if ctx == ChatContext.PRIVATE:
        return (
            "\nКОНТЕКСТ: ЛИЧНЫЙ ЧАТ.\n"
            "- Развёрнутые ответы, полноценный диалог.\n"
            "- Запоминай детали о пользователе.\n"
            "- Можно использовать юмор и неформальный тон."
        )
    if ctx in (ChatContext.GROUP, ChatContext.SUPERGROUP):
        return (
            "\nКОНТЕКСТ: ГРУППА.\n"
            "- Отвечай ОЧЕНЬ кратко: 1-3 предложения максимум.\n"
            "- Без вводных слов и лирических отступлений.\n"
            "- НЕ предлагай меню или кнопки в своём тексте.\n"
            "- Прямо по существу вопроса."
        )
    if ctx == ChatContext.CHANNEL:
        return (
            "\nКОНТЕКСТ: КАНАЛ.\n"
            "- Пиши как профессиональную публикацию.\n"
            "- Цепляющий первый абзац.\n"
            "- Структурированный текст.\n"
            "- Без обращений 'ты/вы'."
        )
    return ""


def should_show_full_menu(ctx: ChatContext) -> bool:
    """Показывать полное меню только в личных чатах."""
    return ctx == ChatContext.PRIVATE


def should_respond(ctx: ChatContext, is_mentioned: bool, is_reply: bool) -> bool:
    """Нужно ли отвечать в данном контексте."""
    if ctx == ChatContext.PRIVATE:
        return True
    if ctx in (ChatContext.GROUP, ChatContext.SUPERGROUP):
        return is_mentioned or is_reply
    # В канале бот сам не отвечает на сообщения
    return False


def get_response_style(ctx: ChatContext) -> dict:
    """Параметры ответа для каждого контекста."""
    if ctx == ChatContext.PRIVATE:
        return {
            "max_tokens": 4096,
            "show_buttons": True,
            "show_menu": True,
            "typing_indicator": True,
        }
    if ctx in (ChatContext.GROUP, ChatContext.SUPERGROUP):
        return {
            "max_tokens": 800,
            "show_buttons": False,
            "show_menu": False,
            "typing_indicator": True,
        }
    if ctx == ChatContext.CHANNEL:
        return {
            "max_tokens": 2048,
            "show_buttons": False,
            "show_menu": False,
            "typing_indicator": False,
        }
    return {"max_tokens": 1000, "show_buttons": False, "show_menu": False, "typing_indicator": True}
