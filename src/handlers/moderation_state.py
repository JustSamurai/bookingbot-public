"""Ожидающие решения модераторов: нажал «Одобрить/Отклонить» → ждём комментарий."""
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

PENDING_TTL = 15 * 60  # секунд; позже комментарий уже не принимается


@dataclass
class PendingDecision:
    ticket_number: int
    status: str
    peer_id: int                      # чат модераторов
    conversation_message_id: int      # карточка заявки, которую обновим
    created_at: float = field(default_factory=time.monotonic)

    @property
    def expired(self) -> bool:
        return time.monotonic() - self.created_at > PENDING_TTL


# Ключ: (peer_id чата, id модератора) — у каждого модератора своё ожидание.
PENDING: Dict[Tuple[int, int], PendingDecision] = {}


def get_pending(peer_id: int, moderator_id: int) -> Optional[PendingDecision]:
    key = (peer_id, moderator_id)
    pending = PENDING.get(key)
    if pending and pending.expired:
        PENDING.pop(key, None)
        return None
    return pending
