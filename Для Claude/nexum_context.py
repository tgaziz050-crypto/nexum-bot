"""
NEXUM — Контекст среды.
ЛИЧНЫЙ ЧАТ | ГРУППА | КАНАЛ
"""
from enum import Enum

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

def context_instructions(ctx: ChatContext) -> str:
    if ctx == ChatContext.PRIVATE:
        return "\nЛИЧНЫЙ ЧАТ: Развёрнутые ответы, полноценный диалог."
    if ctx in (ChatContext.GROUP, ChatContext.SUPERGROUP):
        return "\nГРУППА: Лаконично, 1-3 предложения, без воды."
    if ctx == ChatContext.CHANNEL:
        return "\nКАНАЛ: Публикация, цепляюще, структурированно."
    return ""

def should_show_full_menu(ctx: ChatContext) -> bool:
    return ctx == ChatContext.PRIVATE
