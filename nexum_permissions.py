"""
NEXUM — Система разрешений и согласований.
Все действия в каналах/группах проходят согласование с администратором.
"""
import asyncio
import time
import logging
from typing import Optional, Dict, Any, Callable

log = logging.getLogger("NEXUM.permissions")

# Хранилище ожидающих согласований: {session_id: PendingAction}
PENDING_APPROVALS: Dict[str, "PendingAction"] = {}

# Хранилище ID администраторов (uid -> список chat_id которыми управляют)
ADMIN_REGISTRY: Dict[int, list] = {}

# Callbacks ожидающие ответа от пользователя
PERMISSION_CALLBACKS: Dict[str, Callable] = {}


class PendingAction:
    """Действие ожидающее одобрения администратора."""

    def __init__(self, action_type: str, data: Dict[str, Any], admin_uid: int,
                 target_chat_id: int, preview_text: str = ""):
        self.action_type = action_type
        self.data = data
        self.admin_uid = admin_uid
        self.target_chat_id = target_chat_id
        self.preview_text = preview_text
        self.created_at = time.time()
        self.session_id = f"{action_type}_{admin_uid}_{int(time.time())}"

    def is_expired(self) -> bool:
        """Истекло ли время ожидания (30 минут)."""
        return time.time() - self.created_at > 1800

    def to_message(self) -> str:
        """Сформировать сообщение для администратора."""
        type_labels = {
            "post": "публикацию в канал",
            "group_post": "сообщение в группу",
            "email": "отправку email",
            "delete": "удаление сообщений",
            "code_change": "изменение кода",
            "image_post": "публикацию изображения",
            "schedule": "настройку расписания",
        }
        label = type_labels.get(self.action_type, self.action_type)

        msg = f"⚠️ NEXUM запрашивает разрешение на {label}:\n\n"

        if self.preview_text:
            msg += f"Предпросмотр:\n{self.preview_text[:500]}\n\n"

        if self.action_type == "email":
            msg += f"Кому: {self.data.get('to', '?')}\n"
            msg += f"Тема: {self.data.get('subject', '?')}\n"

        msg += "\nЧто сделать?"
        return msg


def create_approval_session(action: PendingAction) -> str:
    """Создать сессию согласования."""
    PENDING_APPROVALS[action.session_id] = action
    # Очищаем устаревшие
    expired = [k for k, v in PENDING_APPROVALS.items() if v.is_expired()]
    for k in expired:
        del PENDING_APPROVALS[k]
    return action.session_id


def get_approval(session_id: str) -> Optional[PendingAction]:
    """Получить ожидающее действие по ID."""
    action = PENDING_APPROVALS.get(session_id)
    if action and action.is_expired():
        del PENDING_APPROVALS[session_id]
        return None
    return action


def resolve_approval(session_id: str) -> Optional[PendingAction]:
    """Получить и удалить действие (после обработки)."""
    return PENDING_APPROVALS.pop(session_id, None)


def register_admin(uid: int, chat_id: int):
    """Зарегистрировать администратора канала/группы."""
    if uid not in ADMIN_REGISTRY:
        ADMIN_REGISTRY[uid] = []
    if chat_id not in ADMIN_REGISTRY[uid]:
        ADMIN_REGISTRY[uid].append(chat_id)


def get_admin_chats(uid: int) -> list:
    """Получить список чатов которыми управляет пользователь."""
    return ADMIN_REGISTRY.get(uid, [])


class RateLimiter:
    """Ограничитель частоты запросов."""

    def __init__(self):
        self._counts: Dict[str, list] = {}
        self._blocked: Dict[str, float] = {}

    def check(self, key: str, max_count: int = 10, window: int = 60) -> bool:
        """
        Проверить разрешён ли запрос.
        Возвращает True если разрешён, False если заблокирован.
        """
        now = time.time()

        # Проверяем блокировку
        if key in self._blocked:
            if now < self._blocked[key]:
                return False
            else:
                del self._blocked[key]

        # Очищаем старые записи
        if key in self._counts:
            self._counts[key] = [t for t in self._counts[key] if now - t < window]
        else:
            self._counts[key] = []

        self._counts[key].append(now)

        if len(self._counts[key]) > max_count:
            # Блокируем на 5 минут
            self._blocked[key] = now + 300
            self._counts[key] = []
            return False

        return True

    def remaining_block_time(self, key: str) -> int:
        """Сколько секунд ещё заблокирован."""
        if key in self._blocked:
            remaining = self._blocked[key] - time.time()
            return max(0, int(remaining))
        return 0


# Глобальный ограничитель
rate_limiter = RateLimiter()
