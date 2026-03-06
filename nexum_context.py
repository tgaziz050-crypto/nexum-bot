"""
NEXUM — Контекст среды.
Ясно различает: ЛИЧНЫЙ ЧАТ | ГРУППА | КАНАЛ
"""
from enum import Enum
from typing import Optional, Tuple

class ChatContext(Enum):
    PRIVATE = "private"       # Личный чат с пользователем
    GROUP = "group"           # Группа или супергруппа
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"       # Канал

def get_chat_context(chat_type: str) -> ChatContext:
    """Определяет тип среды, где находится бот."""
    if chat_type == "private":
        return ChatContext.PRIVATE
    if chat_type == "channel":
        return ChatContext.CHANNEL
    if chat_type in ("group", "supergroup"):
        return ChatContext.GROUP if chat_type == "group" else ChatContext.SUPERGROUP
    return ChatContext.PRIVATE

def context_instructions(ctx: ChatContext) -> str:
    """Инструкции для AI в зависимости от среды."""
    if ctx == ChatContext.PRIVATE:
        return """
ЛИЧНЫЙ ЧАТ: Здесь ты можешь давать развёрнутые ответы. Пользователь общается напрямую с тобой.
Можешь предлагать действия, уточнять, вести полноценный диалог."""
    
    if ctx in (ChatContext.GROUP, ChatContext.SUPERGROUP):
        return """
ГРУППА: Тебя вызывают через @упоминание или reply. Отвечай ЛАКОНИЧНО — в группе шумно.
1-3 предложения. Без воды. С характером. Не повторяй вопрос пользователя."""
    
    if ctx == ChatContext.CHANNEL:
        return """
КАНАЛ: Публичное пространство. Пиши как публикацию — коротко, цепляюще, структурированно.
Посты требуют согласования с администратором перед публикацией."""
    
    return ""

def needs_admin_approval(ctx: ChatContext, action: str) -> bool:
    """Нужно ли согласование с админом перед действием."""
    if action in ("post_channel", "send_email", "publish"):
        return ctx in (ChatContext.CHANNEL, ChatContext.GROUP, ChatContext.SUPERGROUP)
    return False

def should_show_full_menu(ctx: ChatContext) -> bool:
    """Показывать полное меню с кнопками только в личке."""
    return ctx == ChatContext.PRIVATE

def response_style(ctx: ChatContext) -> str:
    """Стиль ответа в зависимости от контекста."""
    if ctx == ChatContext.PRIVATE:
        return "full"  # Полные ответы
    if ctx in (ChatContext.GROUP, ChatContext.SUPERGROUP):
        return "short"  # Короткие
    if ctx == ChatContext.CHANNEL:
        return "post"  # Как пост
    return "full"
