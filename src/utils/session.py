"""Сессия пользователя (состояние + данные в БД) и блокировки на пользователя."""
import asyncio
import weakref
from typing import Any, Dict, Optional

from database.user_db import get_user_state, save_user_state

# Блокировка на пользователя: два быстрых нажатия/сообщения не затирают друг друга.
# Слабые ссылки — записи исчезают сами, когда блокировка не используется.
_locks: "weakref.WeakValueDictionary[int, asyncio.Lock]" = weakref.WeakValueDictionary()


def user_lock(vk_id: int) -> asyncio.Lock:
    lock = _locks.get(vk_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[vk_id] = lock
    return lock


class Session:
    """Состояние диалога пользователя. state — в колонке state, всё остальное — в data."""

    __slots__ = ("vk_id", "state", "data")

    def __init__(self, vk_id: int, state: str = "main_menu", data: Optional[Dict[str, Any]] = None):
        self.vk_id = vk_id
        self.state = state
        self.data: Dict[str, Any] = data if data is not None else {}

    @classmethod
    async def load(cls, vk_id: int) -> "Session":
        row = await asyncio.to_thread(get_user_state, vk_id)
        return cls(vk_id, row["state"], row["data"])

    async def save(self, state: Optional[str] = None) -> None:
        if state is not None:
            self.state = state
        await asyncio.to_thread(save_user_state, self.vk_id, self.state, self.data)

    @property
    def user(self) -> Dict[str, Any]:
        return self.data.setdefault("user", {})

    @property
    def event_info(self) -> Dict[str, Any]:
        return self.data.setdefault("event_info", {})
