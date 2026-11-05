"""Общие правила маршрутизации сообщений."""
import asyncio
from typing import Callable

from vkbottle.bot import Message
from vkbottle.dispatch.rules import ABCRule

from database.user_db import get_user_state
from utils.vk_helpers import is_start_command


def is_private(message: Message) -> bool:
    return message.peer_id == message.from_id


class StartCommandRule(ABCRule[Message]):
    """/start, start, «Начать» — только в личных сообщениях."""

    async def check(self, message: Message) -> bool:
        return is_private(message) and is_start_command(message.text)


class StateRule(ABCRule[Message]):
    """Личное сообщение (не /start), когда состояние пользователя подходит под predicate."""

    def __init__(self, predicate: Callable[[str], bool]):
        self.predicate = predicate

    async def check(self, message: Message) -> bool:
        if not is_private(message) or is_start_command(message.text):
            return False
        row = await asyncio.to_thread(get_user_state, message.from_id)
        return self.predicate(str(row["state"]))


# Цепочка «Пуск»: состояния pusk_*
PUSK_STATE_RULE = StateRule(lambda state: state.startswith("pusk_"))

# Основная цепочка: любое состояние, кроме главного меню и «Пуска»
MAIN_STATE_RULE = StateRule(
    lambda state: state != "main_menu" and not state.startswith("pusk_")
)
