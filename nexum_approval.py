"""
NEXUM — Согласование опасных действий с администратором.
Запросы отправляются в личку админу. Подтверждение через кнопки.
"""
import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

log = logging.getLogger("NEXUM.approval")

PENDING: Dict[str, "ApprovalRequest"] = {}
APPROVAL_TIMEOUT = 3600  # 1 час

@dataclass
class ApprovalRequest:
    action: str
    chat_id: int
    user_id: int
    user_name: str
    chat_title: str
    data: Dict[str, Any]
    created_at: float = field(default_factory=time.time)

def create_approval_id() -> str:
    return f"appr_{int(time.time() * 1000)}"

def add_pending(aid: str, req: ApprovalRequest):
    PENDING[aid] = req

def get_pending(aid: str) -> Optional[ApprovalRequest]:
    r = PENDING.get(aid)
    if r and (time.time() - r.created_at) > APPROVAL_TIMEOUT:
        PENDING.pop(aid, None)
        return None
    return r

def pop_pending(aid: str) -> Optional[ApprovalRequest]:
    return PENDING.pop(aid, None)

def get_admin_ids() -> List[int]:
    import os
    s = os.getenv("ADMIN_IDS", "").strip()
    if not s:
        return []
    return [int(x.strip()) for x in s.split(",") if x.strip().isdigit()]
