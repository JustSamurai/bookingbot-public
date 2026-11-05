"""CRUD-команды управления базой помещений (только в чате модераторов)."""
import asyncio
import logging
import re
from typing import Optional, Tuple

from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules import ABCRule

import config
from database.admin_crud import delete_data, insert_data, list_data, update_data
from keyboards.registry import reload_registry_async
from utils.vk_helpers import answer_long, strip_mention

logger = logging.getLogger(__name__)

admin_labeler = BotLabeler()

_COMMAND_RE = re.compile(r"^/(list|insert|update|delete|help)\b\s*(.*)$", re.I | re.S)

HELP_TEXT = (
    "⚙️ Шпаргалка по управлению всей БД:\n\n"
    "Просмотр всей карты:\n"
    "• /list — дерево всех корпусов, комнат и оборудования с их ID\n\n"
    "Добавление и связывание:\n"
    "• /insert loc Новая локация\n"
    "• /insert room ID_Корпуса | Номер кабинета\n"
    "• /insert eq ID_Кабинета | Название оборудования | Кол-во\n\n"
    "Редактирование по ID:\n"
    "• /update loc 2 Новое имя корпуса\n"
    "• /update room 5 Новое имя кабинета\n"
    "• /update eq 3 Новое название оборудования (меняется во всех кабинетах)\n"
    "• /update eq 12 3 | 5 (в кабинете 12 изменить количество оборудования 3 на 5 шт.)\n\n"
    "Удаление по ID:\n"
    "• /delete loc 2 (удалить корпус и все его комнаты)\n"
    "• /delete room 5 (удалить комнату и связи с оборудованием)\n"
    "• /delete eq 3 (удалить оборудование вообще из всей базы)\n"
    "• /delete eq 12 | 3 (удалить оборудование 3 только из кабинета 12)\n\n"
    "После любой правки списки в боте обновляются автоматически."
)

USAGE = {
    "insert": (
        "⚠️ Формат команды:\n"
        "/insert loc Название\n"
        "/insert room ID_Корпуса | Номер кабинета\n"
        "/insert eq ID_Кабинета | Название | Кол-во"
    ),
    "update": (
        "⚠️ Формат команды:\n"
        "/update loc|room|eq ID Новое значение\n"
        "/update eq ID_Кабинета ID_Оборудования | Новое_кол-во"
    ),
    "delete": (
        "⚠️ Формат команды:\n"
        "/delete loc|room|eq ID\n"
        "/delete eq ID_Кабинета | ID_Оборудования"
    ),
}


def parse_command(text: Optional[str]) -> Optional[Tuple[str, str]]:
    text = strip_mention(text)
    if text.lower() == "помощь":
        return "help", ""
    match = _COMMAND_RE.match(text)
    if not match:
        return None
    return match.group(1).lower(), match.group(2).strip()


class AdminCommandRule(ABCRule[Message]):
    """Админ-команда, написанная в чате модераторов."""

    async def check(self, message: Message) -> bool:
        return message.peer_id == config.ADMIN_PEER_ID and parse_command(message.text) is not None


@admin_labeler.message(AdminCommandRule())
async def admin_command_handler(message: Message) -> None:
    command, args = parse_command(message.text)  # правило уже гарантировало, что не None

    if command == "help":
        await message.answer(HELP_TEXT)
        return

    if command == "list":
        response = await asyncio.to_thread(list_data)

    elif command == "insert":
        match = re.match(r"^(\w+)\s+(.+)$", args, re.S)
        if not match:
            response = USAGE["insert"]
        else:
            response = await asyncio.to_thread(
                insert_data, match.group(1).lower(), match.group(2).strip()
            )

    elif command == "update":
        match = re.match(r"^(\w+)\s+(\d+)\s+(.+)$", args, re.S)
        if not match:
            response = USAGE["update"]
        else:
            response = await asyncio.to_thread(
                update_data, match.group(1).lower(), int(match.group(2)), match.group(3).strip()
            )

    else:  # delete
        match = re.match(r"^(\w+)\s+(\d+)(.*)$", args, re.S)
        if not match:
            response = USAGE["delete"]
        else:
            response = await asyncio.to_thread(
                delete_data, match.group(1).lower(), int(match.group(2)), match.group(3).strip()
            )

    # Успешная правка — сразу обновляем списки, которые видят пользователи
    if response.startswith(("✅", "🗑️")):
        await reload_registry_async()

    await answer_long(message, response)
