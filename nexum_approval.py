"""
NEXUM — Система согласования действий с администратором.
Перед постом в канал, отправкой email — запрос в личку админу.
"""
import asyncio
import logging
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass

log = logging.getLogger("NEXUM.approval")

# Ожидающие подтверждения: {approval_id: ApprovalRequest}
PENDING: Dict[str, "ApprovalRequest"] = {}

@dataclass
class ApprovalRequest:
    action: str  # post_channel, send_email, etc
    chat_id: int
    admin_uid: int
    data: Dict[str, Any]
    created_at: float

def create_approval_id() -> str:
    import time
    return f"appr_{int(time.time() * 1000)}"

def add_pending(aid: str, action: str, chat_id: int, admin_uid: int, data: dict):
    import time
    PENDING[aid] = ApprovalRequest(
        action=action,
        chat_id=chat_id,
        admin_uid=admin_uid,
        data=data,
        created_at=time.time()
    )

def get_pending(aid: str) -> Optional[ApprovalRequest]:
    return PENDING.get(aid)

def pop_pending(aid: str) -> Optional[ApprovalRequest]:
    return PENDING.pop(aid, None)
