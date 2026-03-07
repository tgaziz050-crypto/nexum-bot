"""
NEXUM — Контекст среды и опасные действия.
Поддержка нескольких каналов, определение действий требующих согласования.
"""
from enum import Enum
from typing import List

class ChatContext(Enum):
    PRIVATE = "private"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"

def get_chat_context(chat_type: str) -> ChatContext:
    if chat_type == "private":
        return ChatContext.PRIVATE
    if chat_type == "channel":
        return ChatContext.CHANNEL
    if chat_type in ("group", "supergroup"):
        return ChatContext.GROUP if chat_type == "group" else ChatContext.SUPERGROUP
    return ChatContext.PRIVATE

# Действия, требующие согласования с админом (в ЛС)
DANGEROUS_ACTIONS = frozenset({
    "delete_messages",
    "delete_all_from_user",
    "clear_chat",
    "ban_user",
    "post_to_channel",
})

def is_dangerous_action(action: str) -> bool:
    return action in DANGEROUS_ACTIONS

def context_instructions(ctx: ChatContext) -> str:
    if ctx == ChatContext.PRIVATE:
        return """
ЛИЧНЫЙ ЧАТ: Развёрнутые ответы. Полноценный диалог."""
    if ctx in (ChatContext.GROUP, ChatContext.SUPERGROUP):
        return """
ГРУППА: Отвечай ЛАКОНИЧНО. 1-3 предложения. Вызов через @ или reply."""
    if ctx == ChatContext.CHANNEL:
        return """
КАНАЛ: Пиши как публикацию. Коротко и цепляюще."""
    return ""
